# Lista de aceptación del PDF

Fuente: `Laboratorio_1_PD_26.pdf`, cuatro páginas, leído desde Downloads. Lista inicial; marcar como cumplido solo con evidencia ejecutada.

- [x] Cinco fuentes originales presentes; sin uso de archivos de competencia excluidos (p. 1).
- [x] Contexto del agente y estructura inicial de código/configuración/DAGs/pruebas (p. 2).
- [x] Referencia DVC de originales y remoto configurado; hashes locales verificados. Conexión remota desde WSL pendiente (p. 2).
- [ ] Pronóstico diario por tienda/familia con horizonte definido e incertidumbre (p. 1).
- [ ] Pedido con costos configurables versionados y límites por ausencia de inventario (p. 1).
- [ ] Seguimiento de publicaciones frente a reales según se conocen (p. 1).
- [ ] Carga histórica inicial y bandeja por fecha/fuente, tratada como externa e inmutable. Recorrido de demostración implementado y probado; integración operativa parametrizable pendiente. El PDF no exige cargar toda la historia original en cada ejecución (p. 2).
- [ ] Disponibilidad temporal explícita, demoras y correcciones sin fuga de información (p. 2).
- [ ] GitHub, ramas/PR, protección de rama principal y pytest en Actions en cada PR (p. 2).
- [ ] Entradas, procesados, modelos y pronósticos publicados versionados con DVC y remoto (p. 2).
- [ ] Reproducción ejecutada de un pronóstico pasado con versiones de código/datos (p. 2 y 4).
- [ ] Airflow 3 en Compose: ingesta/validación, preparación, pronóstico/pedido y seguimiento (p. 2).
- [ ] Idempotencia, rechazo de datos inválidos y tratamiento explícito de ausencias esperables (p. 2).
- [ ] Backfill y reprocesamiento de correcciones, módulos probados y DAGs delgados (p. 3).
- [x] Baseline y ML híbrido que mejora pinball con validación temporal idéntica de desarrollo; calibración/holdout y negocio pendientes (p. 3).
- [ ] Métricas técnicas y de costo, criterio explícito de sustitución (p. 3).
- [ ] README completo y decisiones justificadas sobre disponibilidad, validación y correcciones (p. 3).
- [ ] Ejecución sobre período no publicado sin intervención manual (p. 3).
- [ ] Evidencia de UI Airflow, comparación de modelos y seguimiento (p. 4).
- [ ] Repositorio accesible al equipo docente y tag `entrega-lab1` tras verificación final (p. 3–4).

Acciones externas pendientes de autorización: definir/crear el remoto GitHub, publicar, configurar protecciones y acceso docente. Acceso a Google Drive desde el entorno de ejecución pendiente; no se ha modificado ni reenviado el remoto existente.

Avance de la etapa 3: entorno Linux de herramientas con pytest, referencias DVC locales de bandeja/registro y pipeline de snapshot. Restauración desde caché y recálculo verificados. Esto no completa aún los criterios de modelos/pronósticos, remoto ni replay de una publicación. Evidencia local: `reports/generated/dvc_local_replay.json`; instrucciones en `ENTORNO_DVC.md`.

Avance de la etapa 4: baseline de cuantiles por tienda/familia, modelo y pronóstico de demostración en DVC local, validación conjunta y 23 pruebas. Horizonte de siete días implementado como propuesta provisional. Todavía faltan ML/comparación temporal, costos/pedidos, seguimiento, registro de publicaciones, publicación remota y evidencias finales. Rama local creada e identidad de autor confirmada para registrar el punto de control local.

Avance de la etapa 5: evaluación de desarrollo con cuatro cortes sin fuga temporal, contexto/casos congelados para compartir con ML, 49,896 casos puntuados y métricas técnicas por corte/globales. Pasaron 37 pruebas; hay casos de correcciones, reales pendientes y equivalencia del replay. Cobertura observada 57.3212 % frente al 80 % nominal: calibración pendiente de mejora. Modelos, pronósticos, reales preparados y métricas están en DVC local. Siguen pendientes el ML que mejore al baseline, costos/métrica de negocio y el resto de requisitos operativos/remotos.

Avance de la etapa 6: criterio registrado antes del entrenamiento (`2f765f6`), ML para q10/q90 con mediana baseline y 33 variables de las cinco fuentes/calendario. Mismos 49,896 casos; pinball mejora 5.1189 % y gana tres de cuatro cortes, sin alterar MAE. Cobertura 64.2296 % todavía insuficiente para la tolerancia operativa. Pasaron 43 pruebas y se reprodujeron los cuatro pronósticos desde modelos DVC; se auditaron 368,874 ejemplos temporales. No hay promoción operativa: faltan calibración/holdout y costo de negocio, además de pedidos, seguimiento, Airflow, CI/remoto y evidencia final.

## Alcance obligatorio frente a decisiones del proyecto

Se volvió a leer el PDF original de cuatro páginas al revisar el alcance con el usuario. El documento exige incertidumbre, baseline/ML con mejora, validación temporal idéntica, métricas técnicas/de negocio y criterio explícito de sustitución. No impone este algoritmo, una mejora mínima del 5 %, ganar tres cortes, cobertura exacta del 80 %, tolerancia de 0.10 ni otro holdout interno separado: son decisiones técnicas que añadimos y deben justificarse como tales. La evaluación docente en un período no publicado sí es un requisito, distinto de ese holdout interno.

La mejora demostrada del híbrido es en pinball; MAE/WAPE de la mediana permanecen iguales por diseño. Falta la comparación de negocio. No se presenta el pase técnico como cumplimiento del producto completo.

Prioridad tras esta revisión: completar costos configurables/pedido, publicaciones y seguimiento, Airflow 3/Compose, CI/GitHub/remoto y evidencias de reconstrucción/ejecución. La calibración adicional y el holdout interno no deben desplazar estos requisitos pendientes. Las políticas previas se conservan como registro del experimento; no se rebajan retrospectivamente para fingir una promoción.

Avance de la etapa 7: mecanismo de objetivos diarios derivados de costos, excepciones por familia, cantidades sin stock ficticio y métrica asimétrica proxy. El ejemplo 9:1 tiene 12,474 objetivos y comparación sobre 49,896 casos/modelo; 53 pruebas pasan. La configuración activa sigue pendiente de valores/elección del usuario, por eso no se marca aún como entrega operativa completa de pedidos/costos. Faltan registro de publicaciones, seguimiento, Airflow/CI/remoto y evidencias finales. Ver `PEDIDOS_Y_COSTOS.md`.

Actualización de costos: el usuario confirmó que no dispone de costos reales y se comprobó que no están en los CSV. Se adoptó el supuesto académico relativo 9:1 en la configuración activa, con procedencia ilustrativa explícita; no se trata de costos observados. La generación de objetivos y la métrica `business_configured` usan el mismo archivo. El inventario no es un requisito de entrada adicional: el producto declara objetivos diarios, sin pedido neto. La integración operativa/publicaciones sigue pendiente.
