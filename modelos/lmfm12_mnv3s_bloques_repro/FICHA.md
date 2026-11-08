# Ficha — lmfm12_mnv3s_bloques_repro

Generada por `src/ml/entrenar.py` el 02/11/2026. Métricas completas en `metricas.json`.


| | |
|---|---|
| Dataset | `/Users/alex/Nube /nube/investigacion/doctorado/Planktoscope/datasets_publicos/LMFM-12/particion_bloques` |
| Modelo | MobileNetV3Small (ImageNet) + Dropout 0.2 + Dense 12; cabeza 5 épocas (val 0.833), ajuste 7 épocas con lr 1e-05 (val 0.874); se usa: ajuste |
| Preprocesado | `Code/ml/preprocesado.a_cuadrado`, 224, 0-255 (ver `modelo.json`) |
| TFLite | `modelo.tflite`, md5 `c6da04c20ee4054ed69088cd738fdccf`, 1.1 MB, 2.8 ms/imagen en el Mac |

## Copias entre particiones (excluidas antes de evaluar)

- val: 430 de 1510 tenían copia exacta o casi-copia (dHash ≤ 5) en train
- test: 163 de 756

## Números (test, evaluado con el .tflite)

- **Exactitud 0.813** (IC95 % bootstrap 0.779–0.845), exactitud balanceada 0.817, n = 593
- **Umbral de confianza** 0.427 (conserva el 95 % en validación): en test conserva el 94.8% con exactitud 0.831

| Clase | train | val | test | precisión | recall |
|---|---|---|---|---|---|
| Closterium gracile | 422 | 92 | 50 | 0.875 | 0.980 |
| Coelastrum morus | 443 | 101 | 38 | 0.600 | 0.395 |
| Micrasterias crux-melitensis | 399 | 112 | 53 | 0.918 | 0.849 |
| Pediastrum duplex | 456 | 104 | 46 | 0.902 | 0.804 |
| Planctonema lauterbornii | 470 | 61 | 61 | 0.957 | 0.738 |
| Scenedesmus acutus | 462 | 108 | 63 | 0.812 | 0.413 |
| Scenedesmus bijuga | 474 | 71 | 52 | 0.667 | 0.846 |
| Selenastrum gracile | 450 | 65 | 31 | 0.966 | 0.903 |
| Spirogyra majuscula | 455 | 128 | 65 | 0.915 | 1.000 |
| Stigeoclonium sp. | 338 | 97 | 48 | 0.814 | 1.000 |
| Tetradesmus dimorphus | 464 | 104 | 65 | 0.833 | 0.923 |
| Treubaria triappendiculata | 456 | 37 | 21 | 0.435 | 0.952 |

## Lo que estos números NO dicen

- **Particiones:** son por bloques consecutivos de nombre (`src/ml/particionar.py`), no por sesión. LMFM-12 tiene una
  sola cepa por especie, así que no hay sesiones independientes. Además se excluyeron de val/test las imágenes con
  copia en train. Aun así, imágenes del mismo cultivo pueden estar a ambos lados: es una cota optimista.
- **No es el PlanktoScope:** son imágenes de microscopio a 400–1000×, y nosotros tenemos menos aumento, capilar plano y
  cámara HQ. Sirve para probar el pipeline y como punto de partida preentrenado en algas de agua dulce, no como
  rendimiento del equipo.
- **Objetos ajenos:** sin evaluar. El test solo tiene las 12 clases.
- **Reproducción de `lmfm12_mnv3s_bloques`:** mismos datos y mismas exclusiones (430 de val, 163 de test), con el
  `entrenar.py` reescrito. Exactitud en test 0,813 (IC95 % 0,779–0,845) frente a 0,777 (0,744–0,808) en el original;
  los intervalos se solapan. La diferencia probable es que el ajuste fino duró 7 épocas y no 4, y alcanzó 0,874 en val
  frente a 0,830.
