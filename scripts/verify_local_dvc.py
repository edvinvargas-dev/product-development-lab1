"""Evidencia local del snapshot: omisión, restauración y recálculo con DVC.

Solo se retira temporalmente la salida derivada de snapshot_demo. Se conserva
una copia en data/verification/; jamás se retiran originales ni la bandeja.
Ejecutar desde la raíz usando la imagen de herramientas.
"""

import hashlib
import json
import platform
import subprocess
import tempfile
from importlib.metadata import version
from pathlib import Path


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def tree(path):
    return {str(p.relative_to(path)): digest(p) for p in sorted(Path(path).rglob("*")) if p.is_file()}


def require_equal(actual, expected, label):
    if actual != expected:
        raise RuntimeError(f"Verificación fallida: {label}")


def main():
    output = Path("data/processed/dvc-demo/2017-08-01")
    inbox = Path("data/scenarios/conservador-demo-v1/inbox")
    ledger = Path("data/ingestion/conservador-demo-v1.json")
    protected = {"originals": tree(Path("dataOriginal")), "inbox": tree(inbox),
                 "ledger": digest(ledger), "dvc_config": digest(Path(".dvc/config")),
                 "original_reference": digest(Path("dataOriginal.dvc"))}
    commands = []

    def run(*args):
        result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        commands.append({"command": list(args), "returncode": result.returncode, "output": result.stdout})
        if result.returncode:
            raise RuntimeError(f"Falló {args}:\n{result.stdout}")
        print("OK:", " ".join(args), flush=True)
        return result.stdout

    run("dvc", "repro", "snapshot_demo")
    expected = tree(output)
    require_equal(expected, tree(Path("data/processed/demo/2017-08-01")), "comparación con etapa 2")
    lock_before = digest(Path("dvc.lock"))
    backup_parent = Path("data/verification")
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="snapshot-", dir=backup_parent)) / "previous"
    output.rename(backup)
    print("Copia previa conservada en", backup, flush=True)
    try:
        run("dvc", "checkout", "dvc.yaml:snapshot_demo")
    except Exception:
        if not output.exists():
            backup.rename(output)
        raise
    require_equal(tree(output), expected, "restauración desde caché")
    run("dvc", "repro", "--force", "--no-run-cache", "snapshot_demo")
    require_equal(tree(output), expected, "recálculo desde entradas congeladas")
    require_equal(digest(Path("dvc.lock")), lock_before, "dvc.lock estable")
    after = {"originals": tree(Path("dataOriginal")), "inbox": tree(inbox),
             "ledger": digest(ledger), "dvc_config": digest(Path(".dvc/config")),
             "original_reference": digest(Path("dataOriginal.dvc"))}
    require_equal(after, protected, "entradas y configuración intactas")
    status = json.loads(run("dvc", "status", "--json"))
    require_equal(status, {}, "DVC actualizado")
    evidence = {"python": platform.python_version(), "versions": {k: version(k) for k in
                ["dvc", "dvc-gdrive", "pytest", "pyOpenSSL", "cryptography", "asyncssh"]},
                "snapshot_sha256": expected, "backup_path": str(backup), "commands": commands,
                "restored_identical": True, "recomputed_identical": True,
                "protected_inputs_unchanged": True, "dvc_status": status,
                "scope": "Snapshot local; todavía no es un pronóstico ni un replay desde Google Drive."}
    target = Path("reports/generated/dvc_local_replay.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Evidencia guardada en", target)


if __name__ == "__main__":
    main()
