# Ficha — lmfm12_mnv3s_bloques (generada por `src/ml/entrenar.py` el 02/11/2026)

| | |
|---|---|
| Ficheros | `modelo.tflite` (md5 `d13a509ef778e222a2581f5c38b2d4fd`), `modelo.json` (clases, preprocesado, umbral) |
| Arquitectura | MobileNetV3Small (ImageNet) + Dropout 0,2 + Dense 12 softmax; 5 épocas con la base congelada + 4 de ajuste fino (Adam 1e-05, parada temprana sobre val; usado) |
| Entrada | 224×224×3, 0–255, `Code/ml/preprocesado.a_cuadrado` (completa a cuadrado con el color del borde, sin deformar) |
| Datos | `/Users/alex/Nube /nube/investigacion/doctorado/Planktoscope/datasets_publicos/LMFM-12/particion_bloques` — train 5289, val 1080, test 593 |
| Fuga | excluidas por copia en train: 430 de val y 163 de test |

## Números (TFLite, lo que se despliega)

| Partición | n | Exactitud (IC95 %) | Exactitud balanceada (IC95 %) |
|---|---|---|---|
| val | 1080 | 0.780 (0.754–0.806) | 0.776 (0.754–0.796) |
| **test** | **593** | **0.777** (0.744–0.808) | **0.792** (0.762–0.820) |

- Clases con menor recall en test: Scenedesmus bijuga (0.46, n=52), Scenedesmus acutus (0.51, n=63), Planctonema lauterbornii (0.62, n=61).
- Umbral de confianza (95 % de recall en val): 0.374. En test conserva el 96.6 %, con una exactitud de 0.792.
- Inferencia en el Mac: 3.0 ms por imagen. En la Raspberry está sin medir.
- Detalle: `metricas.json`, `confusion_test.png`, `predicciones_test.csv`.

## Lo que estos números NO dicen (rellenar a mano)

- ¿Las particiones son por sesión/espécimen o aleatorias? Si son aleatorias, el test puede estar inflado.
- ¿Las imágenes son de nuestro PlanktoScope? Si no, esto no es el rendimiento en el equipo.
- Comportamiento ante clases ajenas: sin evaluar si el test no las incluye.
