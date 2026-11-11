"""Árboles de cuantiles residuales; la mediana sigue siendo la del baseline."""

import csv
import hashlib
import json
import math
import pickle
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path

from src.deliveries import json_bytes, sha256, timestamp
from src.features import CATEGORICAL_INDICES, FEATURES, History

INDEX_COLUMNS = ["origin", "target_date", "store_nbr", "family", "label", "label_available_at", "latest_feature_available_at"]


def validate_config(config):
    if config["median_strategy"] != "baseline" or config["early_stopping"] is not False or config["threads"] != 1:
        raise ValueError("El candidato exige mediana baseline, un hilo y sin validación aleatoria")
    for name in ["horizon_days", "minimum_training_history_days", "training_origin_stride_days", "training_origin_lookback_days",
                 "max_iter", "max_leaf_nodes", "min_samples_leaf"]:
        if type(config[name]) is not int or config[name] < 1:
            raise ValueError(f"Parámetro entero positivo requerido: {name}")
    if config["minimum_scale"] <= 0 or not 0 < config["scale_floor_fraction"] <= 1 or config["learning_rate"] <= 0:
        raise ValueError("Escala/tasa de aprendizaje inválida")
    qs = config["quantiles"]
    if len(qs) < 3 or qs != sorted(set(qs)) or 0.5 not in qs or not all(0 < q < 1 for q in qs):
        raise ValueError("Cuantiles del candidato inválidos")


def training_data(history, baseline_config, config):
    import numpy as np

    features, response, weights, index = [], [], [], []
    if not history.labels:
        return np.empty((0, len(FEATURES))), np.empty(0), np.empty(0), index
    earliest = min(key[0] for key in history.labels)
    first = max(earliest + timedelta(days=config["minimum_training_history_days"]),
                history.cutoff.date() - timedelta(days=config["training_origin_lookback_days"]))
    for offset in range(0, max(0, (history.cutoff.date()-first).days), config["training_origin_stride_days"]):
        day = first + timedelta(days=offset)
        origin = history.cutoff + timedelta(days=(day-history.cutoff.date()).days)
        for store, family in sorted(history.sales):
            for horizon in range(1, config["horizon_days"]+1):
                target = day + timedelta(days=horizon)
                label_key = target, store, family
                if label_key not in history.labels:
                    continue
                feature = history.feature(origin, target, store, family, baseline_config, config)
                if feature is None:
                    continue
                label = history.labels[label_key]
                known_at = history.availability["train", target.isoformat()]
                if known_at > history.cutoff or target >= history.cutoff.date():
                    raise ValueError("Etiqueta no conocida al ajustar")
                features.append(feature["vector"])
                response.append((label-feature["center"])/feature["scale"])
                weights.append(feature["scale"])
                index.append({"origin": origin.isoformat(), "target_date": target.isoformat(), "store_nbr": store,
                              "family": family, "label": label, "label_available_at": known_at.isoformat(),
                              "latest_feature_available_at": feature["latest_feature_available_at"]})
    return np.asarray(features, dtype=np.float64).reshape(-1, len(FEATURES)), np.asarray(response), np.asarray(weights), index


def identifier(metadata):
    return hashlib.sha256(json_bytes({k: v for k, v in metadata.items() if k != "model_id"})).hexdigest()


def fit_ml(snapshot, baseline_config, config, output):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from threadpoolctl import threadpool_limits

    validate_config(config)
    history = History(snapshot)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any((output/name).exists() for name in ["model.pkl", "model.json", "training_index.csv"]):
        raise FileExistsError("Ajustar solo en un directorio nuevo; conservar modelos previos")
    X, y, weights, index = training_data(history, baseline_config, config)
    if len(y) < max(2, 2*config["min_samples_leaf"]):
        return None, {**history.quality, "status": "not_ready", "reason": "insufficient_supervised_history"}
    if max(map(len, history.category_maps.values()), default=0) > 255:
        raise ValueError("El candidato no admite más de 255 categorías por variable")
    fingerprint = hashlib.sha256()
    for array in [X, y, weights]:
        fingerprint.update(array.tobytes(order="C"))
    estimators = {}
    print("Ejemplos supervisados:", len(y), "variables:", len(FEATURES), flush=True)
    with threadpool_limits(limits=config["threads"]):
        for q in config["quantiles"]:
            if q == 0.5:
                continue
            estimator = HistGradientBoostingRegressor(loss="quantile", quantile=q, early_stopping=False,
                categorical_features=CATEGORICAL_INDICES, random_state=config["random_state"],
                max_iter=config["max_iter"], learning_rate=config["learning_rate"], max_leaf_nodes=config["max_leaf_nodes"],
                min_samples_leaf=config["min_samples_leaf"], l2_regularization=config["l2_regularization"])
            estimator.fit(X, y, sample_weight=weights)
            estimators[q] = estimator
            print("Cuantil ajustado:", q, flush=True)
    binary = pickle.dumps(estimators, protocol=5)
    metadata = {"schema_version": 1, "model_type": "hgb_residual_tails_v1", "cutoff": history.cutoff.isoformat(),
                "config": config, "baseline_config": baseline_config, "features": FEATURES,
                "category_maps": history.category_maps, "snapshot_manifest_sha256": sha256(Path(snapshot)/"manifest.json"),
                "training_examples": len(y), "training_fingerprint": fingerprint.hexdigest(),
                "training_date_min": min(r["target_date"] for r in index), "training_date_max": max(r["target_date"] for r in index),
                "trained_series": sorted({f"{r['store_nbr']}|{r['family']}" for r in index}),
                "versions": {name: version(name) for name in ["scikit-learn", "numpy", "scipy", "threadpoolctl"]},
                "pickle_sha256": hashlib.sha256(binary).hexdigest()}
    metadata["model_id"] = identifier(metadata)
    (output/"model.pkl").write_bytes(binary)
    (output/"model.json").write_bytes(json_bytes(metadata))
    with (output/"training_index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(index)
    return metadata, history.quality


def load_ml(path):
    path = Path(path)
    metadata = json.loads((path/"model.json").read_text())
    if metadata["schema_version"] != 1 or metadata["model_type"] != "hgb_residual_tails_v1" or identifier(metadata) != metadata["model_id"]:
        raise ValueError("Metadatos de modelo alterados/no soportados")
    if any(version(name) != expected for name, expected in metadata["versions"].items()):
        raise ValueError("El entorno no coincide con el modelo guardado")
    binary = (path/"model.pkl").read_bytes()
    if hashlib.sha256(binary).hexdigest() != metadata["pickle_sha256"]:
        raise ValueError("Modelo serializado alterado")
    # Solo artefactos propios y confiables de este proyecto, validados por DVC.
    return metadata, pickle.loads(binary)


def predict_ml(model_path, snapshot, cases):
    import numpy as np
    from threadpoolctl import threadpool_limits

    metadata, estimators = load_ml(model_path)
    if sha256(Path(snapshot)/"manifest.json") != metadata["snapshot_manifest_sha256"]:
        raise ValueError("Snapshot distinto del usado por el modelo")
    history = History(snapshot)
    config, baseline_config = metadata["config"], metadata["baseline_config"]
    trained = set(metadata["trained_series"])
    prepared, vectors, indices = [], [], []
    for row in cases:
        origin = timestamp(row["cutoff"])
        if origin != history.cutoff:
            raise ValueError("Corte distinto del modelo")
        feature = history.feature(origin, date.fromisoformat(row["target_date"]),
                                  int(row["store_nbr"]), row["family"], baseline_config, config)
        prepared.append((row, feature))
        if feature is not None and f"{row['store_nbr']}|{row['family']}" in trained:
            indices.append(len(prepared)-1)
            vectors.append(feature["vector"])
    corrections = {}
    if vectors:
        with threadpool_limits(limits=config["threads"]):
            matrix = np.asarray(vectors, dtype=np.float64)
            for q, estimator in estimators.items():
                corrections[q] = dict(zip(indices, estimator.predict(matrix).tolist()))
    for i, (row, feature) in enumerate(prepared):
        predictions = dict(feature["reference"]) if feature is not None else {}
        learned = bool(corrections) and i in corrections[next(iter(corrections))]
        if feature is not None and learned:
            center = feature["center"]
            for q in estimators:
                raw = center+feature["scale"]*corrections[q][i]
                if not math.isfinite(raw):
                    raise ValueError("Predicción ML no finita")
                estimate = max(0.0, raw)
                predictions[q] = min(estimate, center) if q < 0.5 else max(estimate, center)
            # Orden determinista si se amplían los cuantiles aprendidos.
            values = sorted(predictions.values())
            predictions = dict(zip(config["quantiles"], values))
        for q in config["quantiles"]:
            method = "baseline_median" if q == 0.5 else ("hgb_residual_tail" if learned else "baseline_fallback")
            yield {**row, "quantile": q, "prediction": predictions.get(q, ""), "model_id": metadata["model_id"],
                   "history_count": feature["history_count"] if feature else 0,
                   "method": method if feature else "insufficient_history", "status": "ok" if feature else "insufficient_history"}
