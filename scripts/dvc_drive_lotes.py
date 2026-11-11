"""Ejecuta DVC dividiendo las consultas de Google Drive en lotes.

pydrive2 1.21.3 arma en find() una sola consulta "'id' in parents or ..."
con todas las carpetas del remoto. Con ~190 carpetas (9 KB) Drive responde
400 Bad Request. Este envoltorio consulta por lotes; no cambia site-packages.
Uso: python scripts/dvc_drive_lotes.py <argumentos de dvc>
"""
import itertools
import sys

from pydrive2.fs import spec

LOTE = 50


def _list_ids_por_lotes(self, query_ids):
    ids = list(query_ids)
    for inicio in range(0, len(ids), LOTE):
        consulta = " or ".join(f"'{i}' in parents" for i in ids[inicio:inicio + LOTE])
        yield from self._gdrive_list(f"({consulta}) and trashed=false")


spec.GDriveFileSystem._gdrive_list_ids = _list_ids_por_lotes

if __name__ == "__main__":
    from dvc.cli import main

    sys.exit(main(sys.argv[1:]))
