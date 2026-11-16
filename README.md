# Modular PlanktoScope — repo de ingeniería

Repo de la parte técnica del proyecto (mecánica, electrónica, software, clasificador). El manuscrito **no** está aquí:
vive en `publication plan/Modular-Planktoscope` (lo lleva Daniela). Instrucciones para agentes: `AGENTS.md`.

## Por dónde empezar (p. ej. para redactar un informe)

1. `ESTADO.md` — qué se ha comprobado, con fecha y evidencia (secciones A1–A7), último estado conocido del equipo (B) y
   verificaciones pendientes con el equipo encendido (C). **Ojo:** la cabecera dice «última actualización 27/09/2026»
   pero las secciones A4c–A4l recogen trabajo hasta el 02/11/2026; fíate de la fecha de cada sección, no de la cabecera.
   Las marcadas «sin probar en el equipo» no están verificadas.
2. `DECISIONES.md` — cada opción descartada, con fecha y motivo. Lo que no está ahí no está decidido.
3. `modelos/*/FICHA.md` — qué es cada modelo, cómo se entrenó/auditó y con qué métricas.
4. `datos/PROTOCOLO_DATASET.md` y `datos/FUENTES.md` — cómo se construye el dataset propio y de dónde sale el conjunto original.

## Mapa de carpetas

| Carpeta | Qué hay | Origen |
|---|---|---|
| `Code/` | App Flask que corre en la Raspberry: `app.py`, `templates/`, `static/`, `ml/` (clasificador y detector que usa la app), `requirements.txt` | propio |
| `src/ml/` | Scripts de datos y entrenamiento: `prepara_dataset.py`, `particionar.py`, `entrenar.py`, `evaluar_modelo.py`, `calibrar_umbral.py` | propio |
| `modelos/` | Modelos entrenados (`.tflite`, `.keras`/`.h5`), métricas, matrices de confusión y `FICHA.md` de cada uno | propio |
| `datos/` | Protocolo del dataset, fuentes y licencias, `sesiones.csv` (una fila por sesión de captura) | propio |
| `pruebas/` | Tests de la app en el Mac con `RPi.GPIO` y `picamera2` simulados; se lanzan con `pruebas/correr.sh` | propio |
| `diagnostico/` | Scripts para auditar el equipo (`estado_equipo.sh`) y duplicados del dataset (`auditoria_duplicados.py`) | propio |
| `sistema/` | Servicio systemd (`modular-planktoscope.service`) y `arreglar_entorno.sh` (entorno único de Python) | propio |
| `prueba de foco/` | Servidor web para ver la cámara de la Pi desde el navegador y medir el foco por zonas (`camara_web.py`, `buscar_raspi.sh`, su `README.md`) | propio |
| `imagenes_prueba_locales/` | 3 fotos de prueba (no son de este equipo) y los resultados de analizarlas | propio |
| `hardware/` | Carcasas del PlanktoScope original (v2.1, v2.5), HAT en KiCad (`v2.5/hat/`) y BOMs. No incluye CAD de los cubos UC2 ni del soporte del capilar (ver `ESTADO.md` A6) | upstream |
| `.github/` | Flujos de CI y plantillas de issues del PlanktoScope original | upstream |

## Cosas a tener en cuenta

- `Code/config.json` y `Code/focus_state.json` son estado del equipo: están en `.gitignore` y viven en la Raspberry.
- Versionados aunque no deberían estarlo (ver `ESTADO.md` A1): `Code/samples/` (38 ficheros, con vídeos),
  `Code/planktoscope-env/` (restos de un venv) y `hardware/v2.5/hat/~Planktoscope-Hat.kicad_pro.lck`. Sin tocar: quitarlos
  del índice es decisión de Alex.
- `modelos/plankton_mobilenet_v1` es en realidad MobileNetV2 (explicado en su `FICHA.md`).
- El repo pesa ~870 MB: unos 670 MB son `.git` y ~130 MB `hardware/`.
- Ramas: `main` (la actual) y `origin/newface`.
