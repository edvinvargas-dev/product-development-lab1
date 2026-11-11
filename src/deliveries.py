"""Contrato de entregas y validación; no modifica la bandeja de entrada."""

import csv
import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMAS = {
    "train": ["id", "date", "store_nbr", "family", "sales", "onpromotion"],
    "stores": ["store_nbr", "city", "state", "type", "cluster"],
    "holidays_events": ["date", "type", "locale", "locale_name", "description", "transferred"],
    "oil": ["date", "dcoilwtico"],
    "transactions": ["date", "store_nbr", "transactions"],
}
KEYS = {"train": ["date", "store_nbr", "family"], "stores": ["store_nbr"],
        "oil": ["date"], "transactions": ["date", "store_nbr"],
        "holidays_events": SCHEMAS["holidays_events"]}


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("El timestamp requiere zona horaria explícita")
    return result.astimezone(timezone.utc)


def sha256(path):
    with Path(path).open("rb") as handle:
        # Compatible con Python 3.10, sin cargar archivos completos.
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def delivery_path(root, entry):
    relative = Path(entry["path"])
    path = (Path(root) / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(Path(root).resolve()):
        raise ValueError("La ruta de una entrega debe permanecer dentro de la bandeja")
    return path


def read_manifest(root):
    manifest = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1:
        raise ValueError("Versión de manifiesto no soportada")
    identifiers, revisions, paths, by_day = set(), set(), set(), {}
    for entry in manifest["deliveries"]:
        source = entry["source"]
        if source not in SCHEMAS:
            raise ValueError("Fuente desconocida")
        data_date = date.fromisoformat(entry["data_date"])
        if data_date.isoformat() != entry["data_date"]:
            raise ValueError("Fecha de entrega no canónica")
        available = timestamp(entry["available_at"])
        if source != "stores" and available.date() <= data_date:
            raise ValueError("El contrato conservador requiere disponibilidad después del día del dato")
        if source == "stores" and available.date() < data_date:
            raise ValueError("Snapshot disponible antes de su fecha")
        if type(entry["row_count"]) is not int or entry["row_count"] < 0:
            raise ValueError("Cantidad de filas inválida")
        digest = entry["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Hash SHA-256 inválido")
        revision = entry["revision"]
        if type(revision) is not int or revision < 1:
            raise ValueError("Revisión inválida")
        if entry["kind"] not in {"historical", "daily", "snapshot"}:
            raise ValueError("Tipo de entrega inválido")
        expected = f"{source}/{entry['data_date']}/r{revision}"
        if entry["delivery_id"] != expected:
            raise ValueError("Identificador de entrega inconsistente")
        key = source, entry["data_date"], revision
        path = delivery_path(root, entry)
        if expected in identifiers or key in revisions or path in paths:
            raise ValueError("Identificador, revisión o ruta duplicados")
        identifiers.add(expected); revisions.add(key); paths.add(path)
        by_day.setdefault(key[:2], []).append(entry)
    for entries in by_day.values():
        ordered = sorted(entries, key=lambda e: e["revision"])
        times = [timestamp(e["available_at"]) for e in ordered]
        if times != sorted(times) or len(set(times)) != len(times):
            raise ValueError("Las revisiones requieren disponibilidades crecientes")
    return manifest


def validate_delivery(root, entry):
    """Valida una entrega disponible completa antes de admitirla al registro."""
    path = delivery_path(root, entry)
    if sha256(path) != entry["sha256"]:
        raise ValueError(f"Hash incorrecto: {entry['delivery_id']}")
    source, seen, count = entry["source"], set(), 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != SCHEMAS[source]:
            raise ValueError(f"Esquema incorrecto: {entry['delivery_id']}")
        for row in reader:
            count += 1
            if None in row or any(v is None for v in row.values()):
                raise ValueError("Fila con columnas incompletas o adicionales")
            if any(v == "" for k, v in row.items() if k != "dcoilwtico"):
                raise ValueError("Campo obligatorio vacío")
            if "date" in row:
                date.fromisoformat(row["date"])
                if row["date"] != entry["data_date"]:
                    raise ValueError("Fecha de fila distinta de la entrega")
            for column in ["store_nbr", "cluster", "id", "onpromotion", "transactions"]:
                if column in row:
                    number = int(row[column])
                    if number < (1 if column in {"store_nbr", "cluster"} else 0):
                        raise ValueError(f"Valor inválido: {column}")
            for column in ["sales", "dcoilwtico"]:
                if column in row and row[column] != "":
                    value = float(row[column])
                    if not math.isfinite(value) or value < 0:
                        raise ValueError(f"Valor inválido: {column}")
            if source == "holidays_events" and row["transferred"] not in {"True", "False"}:
                raise ValueError("transferred debe ser True o False")
            key = tuple(row[c] for c in KEYS[source])
            if key in seen:
                raise ValueError(f"Clave duplicada en {entry['delivery_id']}")
            seen.add(key)
    if count != entry["row_count"]:
        raise ValueError("Cantidad de filas distinta del manifiesto")
    if source == "stores" and count == 0:
        raise ValueError("Snapshot de tiendas vacío")
    return count
