# ESTADO — Modular PlanktoScope

> **Cabecera obligatoria. Última actualización: 27/09/2026. EL EQUIPO AÚN NO SE HA ARRANCADO.**
> La sección A es lo comprobado hoy en disco, con su evidencia. La sección B es lo último que se sabe del
> equipo por el historial, sin verificar. La sección C es lo que hay que medir con el equipo encendido y
> está vacía a propósito: no se rellena ninguna fila sin haberla ejecutado. Cuando se rellene, cambiar esta
> cabecera, poner fecha y dejar la salida del script en `diagnostico/`.

---

## A. Comprobado el 27/09/2026 sin el equipo

### A1. El código del repo no es el que corre en la Raspberry

- `Code/app.py` del repo: último commit de código el 26/12/2025 (`f9260d9`). Arranca Flask, pero importa
  `ml.classifier` y el repo **no contiene `Code/ml/` ni `Code/models/`**: con este repo la app arranca sin
  clasificador (el `try/except` lo desactiva en silencio). Tampoco están `config.json` ni `focus_state.json`.
- El índice de calidad de agua (`calculate_water_quality`, `ml/species_info.json`) no está en el repo. Se
  añadió en la Raspberry entre el 13 y el 15/01/2026 (según el historial de chat exportado). La Raspberry
  tiene por tanto código al menos tres semanas posterior al del repo, y no hay copia de él en ningún sitio
  que yo haya encontrado.
- "Download All" en el repo devuelve un `.txt` con la lista de nombres, no un zip.
- Versionado en git sin que deba estarlo: `Code/samples/` (38 ficheros, vídeos incluidos), un venv parcial
  (`Code/planktoscope-env/`, sin `lib/`) y ficheros de bloqueo de KiCad (`~*.lck`).

**Consecuencia:** hasta traer al repo el código de la tarjeta SD (lo hace el script de diagnóstico), cualquier
arreglo se haría sobre código viejo.

### A2. Clasificador: tres listas de clases incompatibles

| Dónde | Clases |
|---|---|
| `doctorado/Planktoscope/ml_plankton/plankton_mobilenet_v1.tflite` (14/12/2025, md5 `6596e444…09c0`) | **salida [1, 19]**: los 19 géneros de `labels.json` |
| `predict_litert.py` (pegado en el chat el 14/12/2025; **ya no lo usa la app**) | 5: Ceratium, Copepod, Diatom, Dinoflagellate, Other |
| `ml_plankton/predict.py` | 5, pero otras: Ceratium, Chaetoceros, Nitzschia, Noctiluca, Thalassiosira |
| `ml/species_info.json` (índice) | ~19 géneros, mayoritariamente marinos |

- Arquitectura real: **MobileNetV2** (`train.py`; el `.h5` contiene `mobilenetv2_1.00_224` + Dense 256 +
  Dense 19). El nombre del fichero y el borrador del artículo dicen "MobileNetV1".
- Entrada 224×224×3 float32, normalización /255. Entrenado con PNG en **escala de grises** de un conjunto
  público; en el equipo se clasifica **color** de la cámara HQ. El modelo no ha visto nunca una imagen
  tomada con este instrumento.
- **Confirmado el 05/10/2026 con el código traído de la Raspberry:** `Code/ml/plankton.tflite` tiene md5
  `6596e444…09c0`, así que el modelo desplegado es este. `ml/classifier.py` lee las 19 etiquetas de `ml/labels.json`,
  de modo que **los nombres que muestra la app son coherentes con el modelo**. La lista de 5 etiquetas era de un
  `predict_litert.py` anterior y ya no se usa. Diferencia menor: la app reescala con interpolación bicúbica (PIL) y el
  entrenamiento usó *nearest*.

### A3. El conjunto de test no es independiente

`python3 diagnostico/auditoria_duplicados.py .../ml_plankton/dataset_pm` (MD5 de cada imagen; se excluyen
los 57 `desktop.ini`):

| | imágenes | copias exactas de imágenes de training |
|---|---|---|
| test | 118 | **117** |
| validation | 93 | 9 |
| training | 2.872 | 468 duplicados internos → 2.404 únicas |

- Test por clase: entre 1 y 19 imágenes. Con esto no se puede estimar precisión por clase.
- Cualquier cifra calculada sobre ese test mide memoria. **Auditoría del 27/09/2026** sobre las 81 imágenes limpias: exactitud 0,84 (IC95 % 0,75–0,90), 4 clases sin evaluar; ver `modelos/plankton_mobilenet_v1/FICHA.md`.
- Solo se detectan copias exactas; recortes, reescalados o recompresiones de la misma imagen no, así que la
  fuga real puede ser mayor.
- Procedencia: Kaggle `feruzz/plankton-dataset` (26/05/2022, licencia Unknown). El test local no es el de Kaggle: se
  rehízo el 14/12/2025 copiando de training. Ver `datos/FUENTES.md`.

### A4. Congelamiento tras vídeo: hipótesis sobre el código (sin corregir; K2.2)

En las dos versiones que conozco (repo y la de 15/01/2026) la parada de vídeo llama `camera.stop_recording()`
desde un hilo aparte y **nunca vuelve a llamar `camera.start()`**. En picamera2, `stop_recording()` detiene
el codificador y también la cámara (a confirmar en la versión instalada: el script imprime su código fuente).
Con la cámara parada, `capture_buffer("lores")` —que usan `/video_feed` y `/api/capture/photo`— se queda
esperando para siempre: imagen congelada y fotos colgadas. Además `stop_recording()` se ejecuta mientras el
generador de `/video_feed` sigue pidiendo buffers, sin ningún cerrojo. Encaja con el síntoma registrado
("se congela desde la primera grabación", 02/12 y 04/12/2025). `--prueba-video` lo mide.

### A4b. La app clasifica a 640×480

`camera.create_preview_configuration(lores={"size": (640, 480)})`: la vista en vivo, las fotos (`capture_buffer("lores")`)
y los recortes que van al clasificador salen del flujo de baja resolución. El sensor IMX477 da 4056×3040, así que
el clasificador ve unas 6 veces menos detalle lineal del que da la cámara. Lo que se ve con buen enfoque en la
resolución completa no es lo que recibe el modelo.

### A4c. Arranque con motores (06/10/2026, verificado en el equipo)

En la placa montada (versión posterior a la del repo) cada EN lleva una resistencia **a GND**. Como EN es activo en
bajo, los dos drivers quedan activados desde el primer instante y **la Raspberry no arranca con los motores
conectados**. `gpio=9,13=op,dh,pu` en `config.txt` no basta, porque el firmware la aplica tarde. Procedimiento hasta la
próxima versión: **arrancar sin alimentar los motores**. La corrección (resistencia a 3,3 V) va en el próximo HAT.
Subir al repo el KiCad de la placa montada.

### A4d. Autofoco por software (29/10/2026)

La cámara HQ (IMX477) es de foco manual: libcamera no ofrece `AfMode` ni `LensPosition`. El autofoco lo hace la app
moviendo el motor de foco (stepper2) y midiendo la nitidez (varianza del laplaciano de la luminancia a 640×480).

Primera prueba en el equipo, versión 1: barrido grueso de 100 pasos y fino de 20, con nitidez a resolución completa.
- Una vez acabó en el límite inferior (−700).
- Otra acabó en −200, con el foco a mano en −205.
- La curva mostró que el pico es muy estrecho: la nitidez vale 5,8 en −200 y ~1,8 a ±20 pasos, con un fondo de ruido
  de ~1,5. Un barrido de 100 en 100 solo lo encuentra si un punto cae encima por casualidad.

Versión 2 (pasos de 50 por todo el rango, imagen a 1/4): probada 3 veces en el equipo (29/10/2026). Acabó en −200,
−190 y −190, con el foco a mano en −205. A 1/4 el pico es claro (19–25 frente a un fondo de ~1,5), con un segundo pico
menor hacia −50. A resolución completa la curva fina sale ruidosa y con dos máximos (−230 y −190/−200). A Alex no le
gustó el movimiento a tirones.

Versión 3, la actual:
- Barrido continuo, sin paradas, de todo el rango `focus_min`–`focus_max` a la velocidad normal del foco.
- Barrido continuo lento (`af_delay_fine` = 0,016 s, ~30 pasos/s) de ±`af_margin` (60) alrededor del mejor punto.
- Mide la nitidez en cada fotograma de la imagen reducida a 1/4, siempre subiendo.
- La posición es la de cuando llega el fotograma (unos pasos por detrás en el barrido lento).
- Probada en el Mac con una cámara simulada: ≤ 5 pasos del pico desde cualquier punto del rango.
- En el equipo está pendiente (C2 #22).

Versión 3 en el equipo (29/10/2026, otra muestra): el autofoco acabó en −63 y la imagen se ve enfocada.

Precisión (29/10/2026):
- El pico fino se toma como el centro de los puntos por encima de media altura, no como el máximo, porque a 1/4 la cima
  es plana y el ruido decide el máximo.
- La posición anotada es la de cuando se pide el fotograma.

### A4e. Capas de foco del capilar (29/10/2026)

En el capilar hay varios planos con objetos enfocables: en la curva de nitidez se vieron −200 y −50 en la misma muestra.

**Capture Layers** (`/api/capture/layers`) hace lo siguiente:
- Un barrido continuo de todo el rango.
- Toma como capas los picos que superan `af_layer_factor` (2) × el fondo y están separados al menos `af_layer_sep`
  (50) pasos, con un máximo de `af_layer_max` (6).
- Afina cada capa con un barrido lento de ±`af_layer_window` (25).
- Saca una foto clasificada por capa, con el mismo número y sufijo `_capa<paso>` (+ `_raw`).
- Si hay más de una capa, guarda además la imagen apilada (`_apilada`): cada píxel se toma de la capa donde esa zona
  está más nítida.

Todo es a 640×480. Probado en el Mac con una cámara simulada de dos capas (−205 y −56): las encuentra a ≤ 2 pasos y la
apilada es más nítida que cada capa.

Primera prueba en el equipo (29/10/2026): encontró 2 capas, en −741 y −618, y guardó la foto 4 con dos capas más la
apilada. El "4" del nombre es el número de foto, no el número de capas.

Repetidas entre capas (29/10/2026, sin probar en el equipo):
- Se juntan los objetos de todas las capas. Si el centro de la caja de uno cae dentro de la caja de otro de otra capa,
  se cuentan como el mismo objeto y se queda el recorte más nítido (varianza del laplaciano).
- Resultado: `objetos_<n>.csv` (capa, caja, clase, confianza, nitidez) y en la consola "N en las capas, M sin repetidas"
  más el conteo por clase.
- Las fotos anotadas de cada capa siguen mostrando todos sus objetos, y la apilada no entra en el conteo.

Capas falsas: en la simulación, la ladera de un pico ancho salía como capa. Arreglado: un punto solo cuenta como capa si
es el máximo en ±`af_layer_sep`/2, y dos capas que al afinar quedan a menos de `af_layer_sep`/2 se juntan.

Foco por zonas (29/10/2026):
- **Fallo visto en el equipo:** Capture Layers encontró una sola capa (−563). Ahí estaba enfocada una partícula grande
  y oscura, mientras que las algas del centro quedaban borrosas. Alex las enfocó a mano en −533.
- **Causa:** la nitidez de toda la imagen la domina el objeto más grande y contrastado. Además, con `af_layer_sep` = 50,
  dos planos a 30 pasos se juntaban en uno.
- **Arreglo:**
  - La nitidez se mide en 4×4 zonas. Cada zona vota por su posición más nítida, si supera 2 × su propio fondo.
  - Los votos a menos de `af_layer_sep` (ahora 20) pasos forman una capa, y cada capa se afina solo con sus zonas.
  - Auto Focus va a la capa con más zonas, es decir, donde se enfoca la mayor parte de la imagen.
- **Prueba en el Mac:** con el caso reproducido (partícula en una zona a −563, algas repartidas a −533), Auto Focus
  acaba en −532 y Capture Layers encuentra −563 y −533. Con dos mitades a −205 y −56 encuentra las dos, y con una sola
  capa encuentra una.
- En el equipo está pendiente.
- **Varias profundidades en una misma zona:** cada zona puede votar por varios picos de su curva. Cada uno tiene que ser
  el máximo en ±10 pasos, estar a 20 pasos o más de los otros y tener entre ellos un valle por debajo de media altura.
  Probado en el Mac con dos profundidades (−205 y −56) presentes en las 16 zonas: encuentra las dos. Con una sola capa
  no aparecen capas falsas.

Pendiente en el equipo:
- Comprobar si alguna "capa" es una pared del capilar (polvo o rayas en el vidrio) y no muestra: probar con el capilar
  vacío o con agua limpia.
- Comprobar en `objetos_<n>.csv`, comparando con las fotos de cada capa, que las repetidas que quita son de verdad la misma célula.

### A4f. Mejoras tomadas del PlanktoScope original (30/10/2026, sin probar en el equipo)

**Motor de foco.** Alex comprobó que ni pierde pasos ni tiene holgura, pero pidió bajar la velocidad y poner una rampa
corta. Valores nuevos: `delay` de 0,002 a 0,003 s, `ramp_steps` = 20 y `delay_start` = 0,006 s. Se cambian en el
`config.json` de la Raspberry. Corregido además un fallo: la rampa arrancaba más rápido que el crucero en el barrido fino
lento; ahora nunca empieza por debajo del crucero.

**1. Campo plano.**
- Antes de detectar, cada foto se divide entre un fondo y se reescala.
- El fondo es la foto en blanco que guarda el botón **Background** (mediana de 10 fotogramas con agua limpia, en
  `Code/fondo.png`). Si no hay foto en blanco, se estima el fondo de la propia foto con una mediana grande a 1/8.
- La clasificación sigue usando el recorte original, porque el modelo se entrenó sin esta corrección.
- No se implementa la mediana de 10 fotos de muestra ni el descarte de objetos fijos entre fotogramas: necesitan que la
  muestra se mueva entre fotos, y eso llega con la adquisición en ciclos (mejora 4, más adelante).

**2. Medidas por objeto.** `objetos_<n>.csv` (también en Capture Photo) incluye ahora área, diámetro equivalente, ejes
mayor y menor, alargamiento, circularidad, solidez, y media y desviación de tono, saturación y brillo. Son las medidas del
segmentador del PlanktoScope, en px y, si hay calibración, en µm.

**3. Tamaño en µm.**
- `config.json` → `camara.um_por_px` (0 = sin calibrar), `tamano_min_um` (3) y `tamano_max_um` (300).
- Con calibración, el detector filtra por diámetro equivalente en µm; sin ella, usa los límites de área de siempre.
- La calibración se hace en el visor de Samples: foto del portaobjetos micrométrico, **Calibrate**, clic en dos marcas y
  la distancia real. Vale para las fotos de 640×480 de la app.

**Pruebas en el Mac:**
- Cámara simulada: las medidas, el CSV, la calibración, el filtro en µm, Background y su borrado funcionan. Guardar los
  ajustes desde la web conserva la sección `camara`.
- Las pruebas de capas y autofoco siguen pasando.
- Con las tres fotos de `imagenes_prueba_locales` (no son de este equipo), el detector con campo plano estimado encuentra
  casi los mismos objetos que sin él: 65/63, 95/96 y 87/87.

**Umbrales para no clasificar lo que no se ve (30/10/2026):**
- Si la nitidez del recorte (varianza del laplaciano de la foto original) es menor que `camara.nitidez_min` (15), el
  objeto queda como `descartado`: no se clasifica, no se dibuja ni se cuenta, y sí sale en el CSV para revisar el umbral.
- Si la confianza del clasificador es menor que `camara.confianza_min` (50 %), la etiqueta es `desconocido`.
- De dónde sale el 15: en `objetos_6` los objetos reales tenían 33–66 y las manchas 2,6–13,8; en `objetos_8` (pasada
  sin nada enfocado) las dos manchas tenían 4,9 y 6,2. Las manchas tenían confianza 37–44 % y los reales 68–99 %.
- Probado en el Mac: una foto desenfocada queda con todo descartado, sin foto anotada y "No objects classified"; con
  confianza 38 % sale `desconocido` y con 88 % la especie.

Pendiente en el equipo:
- Tomar el fondo con agua limpia.
- Calibrar con el portaobjetos.
- Revisar que el campo plano no empeora la detección en las fotos reales.

### A4g. Series temporales (30/10/2026, sin probar en el equipo)

**Panel Time Series** en la franja derecha de Live View:
- Duración por tiempo total (s) o por número de muestras, intervalo (s) y espera tras bombear (5 s por defecto). Antes
  de empezar muestra cuántas muestras salen y cuánto dura.
- En cada muestra: bomba, espera y Capture Layers con conteo sin repetidas.
- Lo lleva un hilo en la Raspberry (`/api/series/start|stop|state`), así que sigue aunque se cierre el navegador. El
  panel consulta el estado cada 3 s y dibuja el conteo por clase en el tiempo con un canvas propio, sin librerías.
- Mientras dura la serie se rechazan con 409 la bomba, el foco, las capturas, Background y el LED.
- Resultado: `serie_<n>.csv` con una fila por muestra (muestra, hora, t_s, retraso_s, foto, capas, objetos,
  descartados y una columna por clase). Se reescribe tras cada muestra.
- Si el intervalo es menor que una muestra (~40 s), avisa antes de empezar y las muestras van seguidas; `retraso_s`
  lo deja anotado.

**LED y SD (30/10/2026):**
- Start enciende el LED, que se apaga entre muestras, se enciende solo durante cada muestra y se apaga al terminar o
  parar. El botón LED del panel se actualiza solo.
- En la esquina inferior de la barra lateral hay una barra con el espacio de la SD (`/api/disk`, cada 30 s): azul,
  ámbar por encima del 80 % y roja por encima del 90 %.
- Probado en el Mac: el LED queda apagado en la espera entre muestras y al final.
- Aviso de fin de serie: al terminar, el LED parpadea despacio (0,5 s encendido / 1,5 s apagado). Si la serie se cortó
  por un error, parpadea rápido (0,15 / 0,15). Con Stop no parpadea. Se apaga con el botón LED, con Start o con
  cualquier captura, bomba o movimiento de foco; el panel lo indica. Encendido directo, sin rampa PWM. Probado en el Mac
  (patrón lento, apagado con el botón, sin parpadeo con Stop, patrón rápido con error y apagado al capturar).

**Probado en el Mac con la cámara simulada:**
- Validaciones: LED apagado, valores no válidos y serie ya en marcha.
- Bloqueo de la bomba, la foto y el foco durante la serie, y desbloqueo al terminar.
- Serie de 2 muestras completa con su CSV, y parada a mitad.
- Captura del panel renderizado: el diseño y la gráfica se ven bien.

### A4h. Clasificador: preprocesado corregido y etiquetas honestas (01/11/2026)

- Medido en `modelos/plankton_mobilenet_v1/calibracion_2026-11-01/` (ver FICHA): la app perdía 10 puntos de exactitud
  por redimensionar distinto que en el entrenamiento. Corregido; con el código de la app el resultado vuelve a 0,84.
- `camara.confianza_min` pasa de 50 a 55, el umbral calibrado.
- `camara.mostrar_especie = false` por defecto:
  - La foto anotada, el conteo y la serie dicen "objeto", con el diámetro en µm si hay calibración.
  - La clase y la confianza del modelo quedan en el CSV (`clase_modelo`, `confianza_modelo`) como dato experimental.
  - Con `true` vuelve a mostrar la especie, o `desconocido` por debajo del umbral.
- Probado en el Mac con la cámara simulada.

### A4i. Recortes a resolución completa (02/11/2026, sin probar en el equipo)

- **Dos tamaños del mismo fotograma:** la cámara trabaja con `main` = 2028×1520 RGB888 (sensor completo con binning 2×2,
  forzado con `sensor.output_size`) y `lores` = 640×480. Las dos salen de la misma petición (`capture_request`), así
  que ven el mismo campo.
- **Detección:** sigue en la de 640×480.
- **Con cada foto (Capture Photo, cada capa y la apilada) se guarda además `<nombre>_full.jpg`** (2028×1520, calidad 95).
- **Recortes:** un PNG por objeto, también los `descartado` (sirven para la clase "no alga/borroso"), en
  `samples/recortes/<n><sufijo>_<i>.png`, sacado de la foto completa con un margen del 10 % (mínimo 4 px de 640). El
  CSV indica el recorte de cada objeto en la columna `recorte`. La apilada no genera recortes (serían repetidos).
- **Download All y Delete All** incluyen `recortes/`.
- **Config:** `camara.foto_completa` = [2028, 1520]; [0, 0] la desactiva. Si la cámara no acepta la configuración, la
  app vuelve sola a solo 640×480 y lo dice en la consola.
- **Calibración:** `um_por_px` sigue siendo de la imagen de 640×480. En la completa, µm/px = `um_por_px` × 640/2028.
- **Pruebas:** con cámara simulada. Las pruebas pasan a `pruebas/` (falsos de RPi.GPIO y picamera2 + 8 pruebas) y se
  corren con `pruebas/correr.sh`.

### A4j. Preparación del dataset propio (02/11/2026)

- **Download EcoTaxa** (Samples, `/download/ecotaxa`) genera un zip con todos los recortes y `ecotaxa_planktoscope.tsv`:
  cabecera, fila de tipos [t]/[f] y una fila por objeto con las medidas, la etiqueta de la app, la clase del modelo
  (columna informativa, sin anotación), `sample_id` = foto y µm/px del recorte. Probado en el Mac
  (`pruebas/test_ecotaxa.py`). Falta comprobar la importación en un proyecto real de EcoTaxa.
- **`datos/PROTOCOLO_DATASET.md`:** clases v1, captura (una sesión = un cultivo y un día; ≥ 5 sesiones y ≥ 300
  recortes por clase), metadatos en `datos/sesiones.csv`, etiquetado (EcoTaxa o carpetas), particiones **por sesión**
  y evaluación (por clase, por conteos y con objetos desconocidos del lago).

### A4k. Pipeline de entrenamiento (02/11/2026)

- **`src/ml/entrenar.py`:** dataset con `train/val/test/<clase>/` → modelo en `modelos/<nombre>/`. Pasos:
  1. Comprobación de fuga (md5 + dHash): excluye de val y test las imágenes con copia en train.
  2. Preprocesado común con la app (`Code/ml/preprocesado.a_cuadrado`: completa a cuadrado con el color del borde, sin
     deformar).
  3. MobileNetV3 Small (por defecto) o Large de ImageNet, primero con la base congelada y luego con ajuste fino y parada
     temprana. Si el ajuste no mejora la validación, se queda la fase congelada. Aumento con giros, volteos, zoom,
     brillo y contraste, y pesos por clase.
  4. TFLite con cuantización de rango dinámico.
  5. Evaluación **del TFLite**: exactitud y exactitud balanceada con IC95 % por bootstrap, métricas por clase, matriz de
     confusión y umbral de confianza al 95 % de recall en val.
  6. `FICHA.md` generada, con una sección "lo que NO dicen" para rellenar a mano.
- **`src/ml/particionar.py`:** particiones por bloques consecutivos dentro de cada clase y grupo de nombre, para cuando
  el dataset no indica sesiones. El reparto aleatorio no se usa nunca.
- **La app acepta el formato nuevo:** si existe `Code/ml/modelo.json` (+ `modelo.tflite`), `classifier.py` usa sus
  clases y su preprocesado, y clasifica el recorte de la foto completa. Si no existe, sigue el modelo antiguo como hasta
  ahora.
- **Ensayo con LMFM-12** (CC-BY-4.0, 7.555 imágenes, 12 algas verdes de agua dulce, md5 del zip
  `fdbe0e210bc806cae517f491f0d89f5f`), en `doctorado/Planktoscope/datasets_publicos/LMFM-12/`. Resultado en
  `modelos/lmfm12_mnv3s_bloques/`.
- **Incidente (02/11/2026):** una segunda ejecución de la misma tarea sobrescribió por error `src/ml/entrenar.py` y
  `Code/ml/preprocesado.py` de la primera.
  - `preprocesado.py` se restauró desde su `.pyc`, con bytecode idéntico al original.
  - `entrenar.py` no se pudo recuperar. El actual lo reimplementa con las mismas convenciones (a_cuadrado, exclusión de
    fugas, lr de ajuste 1e-5, `modelo.json`), pero sin la opción EfficientNetB0.
  - Para comprobar que reproduce el resultado, se reentrenó `lmfm12_mnv3s_bloques_repro` con los mismos datos: test
    0,813 (IC95 % 0,779–0,845) frente a 0,777 (0,744–0,808). Los intervalos se solapan; en esta ejecución el ajuste fino
    duró más.
- **Foco por zonas, corrección:** al afinar una capa se usa la mediana de sus zonas, no la media. Si la zona de un
  objeto grande había votado también por la capa de las algas, la media arrastraba el foco 12 pasos hacia el objeto.
  `pruebas/test_zonas.py` usa ahora la velocidad de motor del equipo, porque con la rápida el barrido de la simulación
  no separaba planos a 30 pasos.

### A4l. Sesiones, fondo de la serie, volumen y punto de partida LMFM-12 (02/11/2026, sin probar en el equipo)

1. **Sesión del dataset** (panel *Session*, encima de Time Series).
   - Campos: especie o cultivo, origen, dilución, edad, operador y notas.
   - *Start* guarda la sesión abierta en `samples/sesion_actual.json` (sobrevive a un reinicio) con la primera foto.
     *End* añade la fila a `samples/sesiones.csv`, con las mismas columnas que `datos/sesiones.csv`: fotos
     desde–hasta, series, µm/px y `particion` vacía.
   - Cada objeto lleva la columna `sesion` en `objetos_<n>.csv` y en las series. En EcoTaxa, `sample_id` = sesión.
   - Durante una serie no se abren ni cierran sesiones.
   - **Cambio:** *Delete All* ya no pone los contadores a 0 ni borra `sesiones.csv`. Si no, dos fotos distintas
     tendrían el mismo número y el registro de sesiones apuntaría a la equivocada.
2. **Fondo y objetos fijos en las series** (como el segmentador del PlanktoScope, que necesita que la muestra cambie
   entre fotos, y en Time Series la bomba la cambia):
   - Fondo = mediana de las últimas 10 fotos de la serie, en cuanto hay 5.
   - Un objeto en el mismo sitio en 2 de las 3 muestras anteriores queda como `fijo` (suciedad o algo pegado al
     capilar): no se cuenta y sí queda en el CSV.
   - En la simulación, la suciedad sale `fija` desde la 3.ª muestra. Desde la 6.ª, la mediana ya la absorbe y ni se
     detecta.
   - El CSV de la serie añade la columna `fijos`.
3. **Volumen y concentración.**
   - Settings → *Calibration*: grosor interior del capilar (µm) y calibración de la bomba (pasos dados y mL medidos →
     `stepper1.pasos_por_ml`).
   - Volumen por foto = (640 × µm/px) × (480 × µm/px) × grosor.
   - El CSV de la serie añade `volumen_ml`, `volumen_bombeado_ml`, `total_por_ml` y `<clase>_por_ml`.
   - Al empezar la serie, avisa si cada muestra bombea menos volumen del que fotografía, porque entonces las muestras
     se solapan.
4. **`entrenar.py --pesos-iniciales modelo.keras`:** reutiliza la base ya ajustada de otro modelo (p. ej. LMFM-12)
   con una cabeza nueva. Probado con una ejecución rápida.

**Pruebas nuevas:** `pruebas/test_sesion.py`, `test_fijos.py` y `test_volumen.py`. `correr.sh` no puede ejecutarse dos
veces a la vez, porque las dos copias comparten `/tmp/ptest`.

### A5. Conflicto de entornos (K2.1): mecanismo ya visible en el historial

El 02/12/2025, dentro del venv: `picamera2` instalado con pip → `ModuleNotFoundError: No module named
'libcamera'`. Los bindings de libcamera solo existen como paquete del sistema (apt); un venv sin acceso a
paquetes del sistema no puede usar la cámara, y `ai_edge_litert` solo estaba en el venv. En el historial
aparecen **dos venvs** distintos: `~/PlanktoScope/planktoscope-env` y `~/PlanktoScope/Code/planktoscope-env`.

### A6. Hardware en el repo

- `hardware/v2.1/case` y `hardware/v2.5/case`: carcasa del PlanktoScope original (upstream), no la versión
  modular UC2. **No hay CAD de los cubos UC2, del cubo LED, de los espaciadores (25/30/40 mm), del soporte
  del capilar ni de la bomba**, ni en el repo ni en `doctorado/`. K1.2 (CAD, 29/09) no tiene fuentes de partida.
- HAT en KiCad: `hardware/v2.5/hat/` (esquemático, PCB, gerbers; commits 05/11 y 14/11/2025). El commit
  "cambios del hardware" (02/09/2026) solo toca `.kicad_prl` y `~*.lck`: sin cambios de diseño.
- **Lo que dice el HAT diseñado** (netlist de `Planktoscope-Hat.kicad_pcb`; falta comprobar si la placa montada lleva cables añadidos a mano):
  - **Ni un condensador en toda la placa.** Pololu pide ≥ 47 µF en VMOT junto a cada driver.
  - **EN, MS1, MS2 y MS3 de los dos A4988 sin conectar.** El código conmuta EN en GPIO9/GPIO13, pero en el PCB esas
    patas no llegan a los drivers: sin un cable añadido, los motores están siempre alimentados. Con MS sin conectar,
    los drivers trabajan en paso completo, que es el modo más brusco.
  - **Una sola entrada de 5 V** (USB-C J3) alimenta la Raspberry por el conector de 40 pines y, a través de un
    elevador a 12 V (J2), los dos motores y el LED. Un pico de los motores hunde los 5 V de la Raspberry.
  - **CC1/CC2 del USB-C sin resistencias de 5,1 kΩ:** un cargador USB-C que cumpla la norma no entrega tensión; solo
    funciona con fuentes o cables "tontos".
  - Pines, que sí cuadran con el código: foco STEP 6 / DIR 5; bomba STEP 19 / DIR 26; LED 11 (NPN + IRF540N,
    lógica invertida).
- BOM: `hardware/v2.5/bom.csv` es la del upstream; `hardware/v2.6/Planktoscope V2.6 BOM.xlsx` sin revisar.
  No hay BOM de lo que está montado realmente.
- `doctorado/Planktoscope/pcb/planktoscope/plankton/` es otro diseño KiCad (con modelos 3D de ESP32, LoRa,
  A4988, DHT11). No consta si pertenece a este equipo.

### A7. Afirmaciones del borrador que no cuadran con la evidencia (para Daniela; su repo no se toca)

`publication plan/Modular-Planktoscope/process.md` dice: MobileNetV1 (es V2); conjunto de Kaggle de agua dulce
(los géneros son marinos); 19 categorías (el script de la app usaba 5 etiquetas, según el historial); inferencia < 1 s en Pi 4 (no medido;
el script lo mide); "predicciones coherentes con la inspección visual" (sin métrica). Además describe el
índice trófico, que queda fuera del alcance.

---

## B. Último estado conocido del equipo (historial dic 2025 – jul 2026) — SIN VERIFICAR

- Raspberry Pi 4 (pipeline libcamera `rpi/vc4`), kernel 6.12.57-v8+, Python 3.13, libcamera 0.5.2,
  picamera2 0.3.31 (pip, en el venv), cámara HQ IMX477. Usuario `alex`, código en `~/PlanktoScope/Code`.
- GPIO (BCM): bomba STEP 19 / DIR 26 / EN 9; enfoque STEP 6 / DIR 5 / EN 13 (límites 40–60); LED 11 con
  lógica invertida. Enable activo en bajo, motores deshabilitados en reposo.
- Arranque: en la Raspberry **no existe** `~/.config/systemd/user/modular-planktoscope.service` (comprobado el 05/10).
  Lo que sí hay es `/etc/systemd/system/modular-planktoscope.service` (copia en `sistema/`), que lanza la app con el
  Python del venv. No se sabe si está habilitado ni qué lanza hoy la app: lo dirá el diagnóstico.
- Historial: el 12/12/2025 se pasó de servicio de sistema a **servicio de usuario**
  (`~/.config/systemd/user/modular-planktoscope.service`, `ExecStartPre=sleep 15`), y después se hizo que
  lanzara la app **fuera** del venv. Un servicio de usuario solo arranca sin iniciar sesión si `Linger=yes`.
- Red: AP "PlanktoScope" en 192.168.4.1. Hubo configuración con NetworkManager y con systemd-networkd a la
  vez; hostapd no aparece en el historial. No se sabe qué mecanismo quedó activo.
- Último acceso registrado por SSH: 10/07/2026.

---

## C. Verificación con el equipo encendido — POR RELLENAR

**Antes de tocar nada:** fotografiar el equipo tal como está (conjunto, óptica y espaciador montado,
capilar, cableado del HAT, fuente) → `fotos/AAAA-MM-DD_estado-inicial/`.

Procedimiento:

1. Arranque en frío. Esperar 2 min. Conectar el Mac a la red del PlanktoScope.
2. `scp diagnostico/estado_equipo.sh alex@192.168.4.1:~`
3. `ssh alex@192.168.4.1 'bash estado_equipo.sh'` (solo lectura)
4. Pruebas manuales de la tabla (interfaz en `http://192.168.4.1:5000`).
5. `ssh alex@192.168.4.1 'bash estado_equipo.sh --prueba-video'` (crea 1 vídeo y 1 foto)
6. `scp 'alex@192.168.4.1:~/diagnostico-*.tgz' diagnostico/` y descomprimir `codigo_raspberry.tgz` en
   `diagnostico/` para compararlo con `Code/`.

### C1. Versiones (del script)

| Componente | Sistema | venv (ruta: …) |
|---|---|---|
| Modelo de placa / SO / kernel | | — |
| Python | | |
| `include-system-site-packages` | — | |
| picamera2 / libcamera | | |
| ai_edge_litert / tflite_runtime | | |
| opencv / numpy / Flask | | |
| RPi.GPIO / lgpio | | |
| Intérprete que usa el servicio (`/proc/<pid>/exe`) | | |

### C2. Funciones

| # | Prueba | Cómo | Resultado | Nota |
|---|---|---|---|---|
| 1 | AP aparece tras arranque en frío | Mac, lista de redes; tiempo desde encendido | | |
| 2 | La interfaz carga | navegador | | |
| 3 | La app la lanzó systemd, no alguien a mano | script §5 | | |
| 4 | El intérprete del servicio importa picamera2 **y** ai_edge_litert | script §3 y §5 | | |
| 5 | Vista en vivo | ¿fluida? ¿retardo? | | |
| 6 | Foto: guarda, segmenta y clasifica | nº de recuadros, etiquetas, consola web | | |
| 7 | Vídeo 10 s → se guarda `.mp4` | Samples | | |
| 8 | Tras el vídeo: ¿vuelve la vista en vivo? ¿funciona foto? | a mano + script §10 | | |
| 9 | Bomba (Take sample, 2000 pasos) | gira, sentido, caudal aprox., ¿salta pasos? | | |
| 10 | Enfoque +/−, límites 40/60, "ignorar límites" | | | |
| 11 | Enable: motores sin par en reposo, drivers fríos tras 10 min | tocar eje / dedo en el disipador | | |
| 12 | LED on/off | | | |
| 13 | Descargar una muestra / Download All | ¿zip o txt? | | |
| 14 | Borrar una muestra / todas | | | |
| 15 | 3 arranques en frío seguidos: todo vuelve sin intervención | | | |
| 16 | Alimentación: `get_throttled` tras 10 min moviendo motores | script §1 | | |
| 17 | Hora del sistema sin internet (modo AP) | script §1 vs reloj real | | |
| 18 | Modelo desplegado: md5, forma de salida, etiquetas, ms/inferencia | script §7–8 | | |
| 19 | Óptica: se alcanza el foco dentro de 40–60; capilar entero; espaciador montado | foto | | |
| 20 | µm por píxel (portaobjetos micrométrico o microesferas), en la resolución completa **y** en la de 640×480 que usa la app | foto de la escala | | |
| 21 | Píxeles de lado a lado de una célula de *Chlorella* y de una colonia de *Acutodesmus* en la foto que clasifica la app | foto de cultivo | | |
| 22 | Auto Focus (LED encendido, bomba parada): termina en < 30 s y la imagen queda nítida; repetir 3 veces desde posiciones distintas | botón Auto Focus + consola web | | Probado solo con cámara simulada (29/10/2026) |

### C3. Lo que falla hoy (rellenar tras C1–C2)

—
