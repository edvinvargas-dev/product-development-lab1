"""Verifica restauración y recálculo de la evaluación local de desarrollo.

Ejecutar desde la raíz: python -m scripts.verify_evaluation, dentro de tools.
Conserva una copia del resultado previo; no retira contexto ni bandejas.
"""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def tree(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            with path.open("rb") as handle:
                result[str(path.relative_to(root))] = hashlib.file_digest(handle, "sha256").hexdigest()
    return result


def main():
    context = Path("data/evaluation/dev-context-v1")
    output = Path("data/evaluation/baseline-dev-v1")
    if not (context / "manifest.json").is_file() or not (output / "metrics.json").is_file():
        raise RuntimeError("Ejecuta primero dvc repro baseline_backtest")
    before, context_before = tree(output), tree(context)
    report_before = json.loads((output / "metrics.json").read_text())
    if report_before["actual_pending_cases"] or report_before["forecast_unavailable_cases"]:
        raise RuntimeError("La demostración real no tiene todos los casos disponibles")
    commands = []

    def run(*args):
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        commands.append({"command": list(args), "returncode": result.returncode, "output": result.stdout})
        if result.returncode:
            raise RuntimeError(result.stdout)
        print("OK:", " ".join(args), flush=True)
        return result.stdout

    parent = Path("data/verification")
    parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="evaluation-", dir=parent)) / "previous"
    output.rename(backup)
    try:
        run("dvc", "checkout", "dvc.yaml:baseline_backtest")
    except Exception:
        if not output.exists():
            backup.rename(output)
        raise
    if tree(output) != before:
        raise RuntimeError("Restauración diferente de la versión previa")
    run("python", "-m", "src.evaluation", "baseline", "--context", str(context),
        "--config", "config/baseline.json", "--output", str(output))
    if tree(output) != before or tree(context) != context_before:
        raise RuntimeError("Recálculo diferente o contexto modificado")
    status = json.loads(run("dvc", "status", "--json"))
    if status:
        raise RuntimeError("Hay cambios DVC pendientes")
    evidence = {"restored_identical": True, "recomputed_identical": True, "context_unchanged": True,
                "output_sha256": before, "context_manifest_sha256": report_before["context_manifest_sha256"],
                "expected_cases": report_before["expected_cases"],
                "scored_cases": report_before["pooled"]["scored_cases"], "metrics": report_before["pooled"],
                "backup": str(backup), "commands": commands, "dvc_status": status}
    path = Path("reports/generated/evaluation_verified.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Evidencia:", path)


if __name__ == "__main__":
    main()
