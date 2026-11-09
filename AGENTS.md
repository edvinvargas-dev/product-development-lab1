# Contexto y reglas del laboratorio

Producto de pronóstico, recomendación de abastecimiento y seguimiento con datos de Corporación Favorita. Explicar cambios en español y avanzar en etapas pequeñas verificables.

- Trabajar dentro de esta carpeta. Conservar el notebook original y los CSV de `dataOriginal/`.
- Nunca imprimir, copiar ni versionar credenciales, `.dvc/config.local`, tokens o configuración de autenticación. No recorrer `.aws/` para diagnosticar el proyecto.
- Datos, modelos y pronósticos con DVC; no agregarlos a Git. No cambiar el remoto DVC ni enviar datos sin explicar destino y efecto.
- No publicar ni hacer push sin autorización explícita con destino visible. No crear el tag de entrega antes de completar y verificar la aceptación.
- En WSL no ejecutar la `.venv` de Windows. Airflow 3 se ejecutará en contenedores Linux con Compose.
- La bandeja de entrada es externa e inmutable. Separar generador de simulación y consumidor de entregas.
- Separar fecha del dato, disponibilidad e ingesta; ninguna predicción puede usar información posterior a su corte. Correcciones con versiones, resultados publicados inmutables y replay con manifiesto explícito.
- No inventar inventarios, costos ni disponibilidad observada. Documentar los supuestos simulados.
- No borrar ceros/extremos automáticamente. DAGs delgados y lógica en `src/`, probada con datos sintéticos.
- Revisar `DECISIONES.md`, `README.md` y `docs/ACEPTACION.md` antes de extender la implementación.
- Verificación sin dependencias: `python3 -m unittest discover -s tests -v`. Las mismas pruebas se ejecutan con pytest en la imagen Linux de herramientas.
- Entorno Linux de herramientas: `docker compose -f compose.tools.yaml run --rm tools` ejecuta pytest. Construir antes con `docker compose -f compose.tools.yaml build tools`. Conservar versiones directas en `requirements/tools.in` y transitivas en `requirements/tools.lock`.
- El servicio tools no tiene red y oculta `.dvc/config.local`. Para DVC local usar `docker compose -f compose.tools.yaml run --rm tools dvc ...`. No habilitar red ni montar credenciales por comodidad.
- `scenario.dvc`, `ingestion.dvc` y `evaluation-scenario.dvc` congelan entradas. `dvc.yaml` reconstruye snapshots, baseline y evaluación de desarrollo en directorios separados. No añadir la bandeja como salida regenerable de una tarea de ingesta.
- Baseline y futuro ML deben compartir `config/evaluation.json`, el contexto/casos de `data/evaluation/dev-context-v1/`, cuantiles y reales al mismo cierre. Exigir igual completitud para comparar; no descartar casos difíciles ni convertir reales pendientes en cero.
- Los artefactos reproducibles del replay guardan horas lógicas; la hora real de ejecución no debe cambiar sus hashes. Esto no elimina la auditoría real de la ingesta operativa.
