# Ficha — plankton_mobilenet_v1 (el nombre engaña: es MobileNetV2)

**Auditado el 27/09/2026** con `src/ml/evaluar_modelo.py`. Resultados en `evaluacion_2026-09-27/`.

## Qué es

| | |
|---|---|
| Ficheros | `plankton_mobilenet_v1.tflite` (md5 `6596e444cb921de26ba7ed1a0e7d09c0`), `.h5` (md5 `7e3a53e04df8b734aad3b277c6b63ecb`), `labels.json` |
| Origen | `doctorado/Planktoscope/ml_plankton/`, 14/12/2025. Scripts copiados en `entrenamiento/` |
| Arquitectura | MobileNetV2 (ImageNet, congelada) + GlobalAveragePooling + Dense 256 ReLU + Dropout 0,4 + Dense 19 softmax |
| Entrenamiento | 20 épocas fijas, Adam 1e-3, sin callbacks; aumento: rotación 20°, zoom 0,2, desplazamiento 0,1, volteo horizontal |
| Entrada | 224×224×3 float32, /255; la carga de Keras replica la escala de grises a 3 canales, interpolación *nearest* |
| TFLite | `Optimize.DEFAULT` (cuantización de pesos de rango dinámico) |
| Clases | 19 géneros de fitoplancton, mayoritariamente marinos (`labels.json`) |
| Datos | `dataset_pm/` = Kaggle `feruzz/plankton-dataset` (26/05/2022, **licencia Unknown**; imágenes de internet, de un curso y de WHOI/IFCB mezcladas). Ver `datos/FUENTES.md` |
| ¿Desplegado? | **Sí** (05/10/2026): `Code/ml/plankton.tflite` en la Raspberry tiene el mismo md5; la app usa las 19 etiquetas de `labels.json` |

## Números

| Subconjunto | n | Exactitud | Top-3 | F1 macro* |
|---|---|---|---|---|
| test original | 118 | 1,000 | 1,000 | 1,000 |
| **limpio** (test+val sin copias ni casi-copias de training) | **81** | **0,840** (IC95 % 0,75–0,90) | 0,963 | 0,772 |

\* Media sobre las clases con al menos una imagen.

- **El test original no vale:** 117 de sus 118 imágenes son copias exactas de imágenes de training. El 1,000 es memoria.
- **Construcción del subconjunto limpio:** de test y validation se descartan 126 copias exactas (md5), 3 casi-copias (dHash ≤ 5 de 64 bits) y 1 repetida. Quedan 81 imágenes, casi todas de validation.
  - Validation se usó en `model.fit` solo para monitorizar. No hubo parada temprana ni selección de modelo, así que es aceptable como test, pero hay que declararlo.
- **Cobertura por clase insuficiente.**
  - Ornithocercus, Pinnularia, Pyrodinium y Thalassionema no tienen ninguna imagen limpia: no están evaluadas.
  - Otras siete clases tienen 1 o 2 imágenes.
  - Solo Asterionellopsis (17), Cerataulina (14), Guinardia (12), Ceratium (9) y Prorocentrum (9) tienen algo de muestra. Ver `metricas.json`.
- **Confusiones principales:**
  - Guinardia → Cerataulina (3 de 12).
  - Asterionellopsis → Chaetoceros (2 de 17).
- **La confianza no separa aciertos de fallos:**
  - Media de 0,95 en aciertos frente a 0,74 en fallos.
  - Hay fallos por encima de 0,95 (Guinardia→Cerataulina 0,998; Chaetoceros→Cerataulina 0,986; Thalassiosira→Prorocentrum 0,954).
  - Un umbral de confianza no basta como rechazo.

## Lo que estos números NO dicen

1. **No es el rendimiento en el PlanktoScope.** Todas las imágenes vienen del mismo conjunto, la misma óptica y la misma preparación. El modelo no ha visto nunca una imagen de nuestro equipo (color, cámara HQ, capilar plano, 20×). 0,84 es una cota superior dentro del dominio; en nuestras imágenes no está medido.
2. **Posible fuga residual.** El umbral de dHash es heurístico. La casi-copia más cercana que se aceptó está a 6 bits, y los nombres de fichero (`<clase>_<n>`) sugieren que varias imágenes pueden salir del mismo espécimen o del mismo campo. Si lo son, 0,84 está inflado.
3. **Sin comportamiento ante taxones ajenos.** No hay clase "otro" ni evaluación con organismos fuera de las 19 clases.

## Calibración (01/11/2026, `src/ml/calibrar_umbral.py` → `calibracion_2026-11-01/`)

Medido sobre el mismo subconjunto limpio (n = 81).

- **Preprocesado de la app equivocado:** la app redimensionaba con la bicúbica por defecto de PIL, y el entrenamiento
  usó *nearest*. La exactitud era 0,74 con la de la app frente a 0,84 con la del entrenamiento.
  - Corregido en `Code/ml/classifier.py`: con el código de la app ya da 0,8395, la misma cifra que la auditoría.
- **Umbral de confianza máxima con el 95 % de recall de las clases conocidas:** 0,549.
  - Rechaza 4 imágenes: 2 de los 13 fallos y 2 aciertos.
  - La exactitud de las conservadas pasa de 0,84 a 0,857.
  - La app usa 55 % (`camara.confianza_min`).
- **Temperature scaling:** T = 1,8 baja el NLL (de 0,584 a 0,475) pero no mejora el ECE (0,104 → 0,105). No se aplica.
- **Fuera de dominio, en el equipo:** en `objetos_6.csv` (29/10/2026, preprocesado bicúbico anterior), los 6 objetos
  nítidos recibieron entre 68 % y 99 % de confianza para géneros marinos. Ninguno lo rechazaría el umbral de 55 %.
  El umbral no protege frente a lo que el modelo no conoce. Por eso la app muestra "objeto" por defecto
  (`camara.mostrar_especie = false`) y deja la clase del modelo solo en el CSV.

## Veredicto

No se puede usar como resultado del artículo. Además, las clases (marinas) no son las del estudio (especies de cultivo compradas + lago de agua dulce). Sirve como línea base del *pipeline* de entrenamiento, no como clasificador del instrumento.
