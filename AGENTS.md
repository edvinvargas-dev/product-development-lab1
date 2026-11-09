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
- Verificación completa con ML: `docker compose -f compose.tools.yaml build ml` y `docker compose -f compose.tools.yaml run --rm ml`. Sus cinco adiciones científicas están fijadas en `docker/ml/requirements.lock`, sin actualizar `requirements/tools.lock`.
- `config/ml.json` y `config/model-selection.json` se registraron antes de entrenar el primer candidato. No modificar retroactivamente el criterio para aprobar un resultado observado; registrar nuevos experimentos/decisiones explícitos.
- El ML inicial conserva q50 y aprende q10/q90. Su pase técnico no permite promoción operativa: hacen falta holdout, cobertura suficiente y costos de negocio verificados. No inventar esas evidencias ni cambiar el baseline congelado.
- Costos activos en `config/costs.json`, inicialmente sin definir. Los números de `config/examples/costs-relative-9-1.json` son un ejemplo separado, no costos reales ni política activa. Solicitar valores/elección al usuario; no completar costos reales por inferencia.
- La recomendación actual es un objetivo diario continuo; `net_order_quantity` queda vacío porque no hay stock disponible. No asumir stock cero, empaques ni inventario entre días. No sumar cuantiles diarios para declarar un cuantil semanal.
- `src.orders` elige cantidades solo con pronóstico/costos; `src.business_evaluation` incorpora reales después. Sus déficits/excesos/costos son proxies, no merma/quiebres o pérdidas financieras observadas.
