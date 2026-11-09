# Lista de aceptación del PDF

Fuente: `Laboratorio_1_PD_26.pdf`, cuatro páginas, leído desde Downloads. Lista inicial; marcar como cumplido solo con evidencia ejecutada.

- [x] Cinco fuentes originales presentes; sin uso de archivos de competencia excluidos (p. 1).
- [x] Contexto del agente y estructura inicial de código/configuración/DAGs/pruebas (p. 2).
- [x] Referencia DVC de originales y remoto configurado; hashes locales verificados. Conexión remota desde WSL pendiente (p. 2).
- [ ] Pronóstico diario por tienda/familia con horizonte definido e incertidumbre (p. 1).
- [ ] Pedido con costos configurables versionados y límites por ausencia de inventario (p. 1).
- [ ] Seguimiento de publicaciones frente a reales según se conocen (p. 1).
- [ ] Carga histórica completa y bandeja por fecha/fuente, tratada como externa e inmutable. Recorrido de demostración implementado y probado; ampliación de historia pendiente (p. 2).
- [ ] Disponibilidad temporal explícita, demoras y correcciones sin fuga de información (p. 2).
- [ ] GitHub, ramas/PR, protección de rama principal y pytest en Actions en cada PR (p. 2).
- [ ] Entradas, procesados, modelos y pronósticos publicados versionados con DVC y remoto (p. 2).
- [ ] Reproducción ejecutada de un pronóstico pasado con versiones de código/datos (p. 2 y 4).
- [ ] Airflow 3 en Compose: ingesta/validación, preparación, pronóstico/pedido y seguimiento (p. 2).
- [ ] Idempotencia, rechazo de datos inválidos y tratamiento explícito de ausencias esperables (p. 2).
- [ ] Backfill y reprocesamiento de correcciones, módulos probados y DAGs delgados (p. 3).
- [ ] Baseline y ML que lo mejore, validación temporal idéntica (p. 3).
- [ ] Métricas técnicas y de costo, criterio explícito de sustitución (p. 3).
- [ ] README completo y decisiones justificadas sobre disponibilidad, validación y correcciones (p. 3).
- [ ] Ejecución sobre período no publicado sin intervención manual (p. 3).
- [ ] Evidencia de UI Airflow, comparación de modelos y seguimiento (p. 4).
- [ ] Repositorio accesible al equipo docente y tag `entrega-lab1` tras verificación final (p. 3–4).

Acciones externas pendientes de autorización: definir/crear el remoto GitHub, publicar, configurar protecciones y acceso docente. Acceso a Google Drive desde el entorno de ejecución pendiente; no se ha modificado ni reenviado el remoto existente.

Avance de la etapa 3: entorno Linux de herramientas con pytest, referencias DVC locales de bandeja/registro y pipeline de snapshot. Restauración desde caché y recálculo verificados. Esto no completa aún los criterios de modelos/pronósticos, remoto ni replay de una publicación. Evidencia local: `reports/generated/dvc_local_replay.json`; instrucciones en `ENTORNO_DVC.md`.

Avance de la etapa 4: baseline de cuantiles por tienda/familia, modelo y pronóstico de demostración en DVC local, validación conjunta y 23 pruebas. Horizonte de siete días implementado como propuesta provisional. Todavía faltan ML/comparación temporal, costos/pedidos, seguimiento, registro de publicaciones, publicación remota y evidencias finales. Rama local creada e identidad de autor confirmada para registrar el punto de control local.

Avance de la etapa 5: evaluación de desarrollo con cuatro cortes sin fuga temporal, contexto/casos congelados para compartir con ML, 49,896 casos puntuados y métricas técnicas por corte/globales. Pasaron 37 pruebas; hay casos de correcciones, reales pendientes y equivalencia del replay. Cobertura observada 57.3212 % frente al 80 % nominal: calibración pendiente de mejora. Modelos, pronósticos, reales preparados y métricas están en DVC local. Siguen pendientes el ML que mejore al baseline, costos/métrica de negocio y el resto de requisitos operativos/remotos.
