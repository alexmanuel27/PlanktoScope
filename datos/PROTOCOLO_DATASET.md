# Protocolo del dataset propio (v1, 02/11/2026)

Escrito **antes** de capturar, para que el dataset sirva para entrenar y, sobre todo, para evaluar de verdad.
La lección de la auditoría (`modelos/plankton_mobilenet_v1/FICHA.md`) es que el test original de Kaggle tenía 117 de 118
imágenes copiadas del entrenamiento y daba un 1,000 falso. Esto no debe repetirse.

## 1. Qué se entrena

Un **clasificador de recortes**: una imagen por objeto, la que guarda la app en `samples/recortes/`, a 2028×1520. La
detección sigue siendo la clásica (`Code/ml/detector.py`). Si más adelante hace falta un detector entrenado, estos mismos
datos sirven de base, pero entonces hay que dibujar cajas.

## 2. Clases v1

| Clase (carpeta / categoría) | Qué entra | Qué NO entra |
|---|---|---|
| `chlorella_vulgaris` | células del cultivo de *C. vulgaris*, sueltas o en grupos pequeños | — |
| `acutodesmus_obliquus` | células o colonias (cenobios) del cultivo de *A. obliquus* (= *Tetradesmus obliquus*) | — |
| `otra_alga` | cualquier otra alga: contaminación del cultivo, muestras de lago | — |
| `no_alga_fibra` | fibras, pelos, filamentos sin pigmento | algas filamentosas (→ `otra_alga`) |
| `no_alga_burbuja` | burbujas | — |
| `no_alga_detrito` | partículas, restos, polvo, cristales | — |
| `borroso` | objetos que no se pueden identificar por desenfoque (la app los marca `descartado`) | — |
| `duda` | quien etiqueta no está seguro | **no se usa para entrenar ni para evaluar** |

Las algas se etiquetan a nivel de especie aunque formen colonias: la colonia es parte de la especie.

## 3. Captura

1. **Al empezar cada sesión:**
   - Capilar con agua limpia, LED encendido y **Background**.
   - **Calibración** (µm/px) cada vez que cambie la óptica o el enfoque mecánico.
2. **Dilución:**
   - Como mucho 20–30 objetos por campo (protocolo del PlanktoScope).
   - Si se tocan entre sí, diluir ×2.
3. **Campos independientes:**
   - Usar **Time Series** con bomba entre muestras, en lugar de muchas fotos del mismo campo.
   - La misma célula fotografiada dos veces es una copia.
4. **Una sesión = un cultivo (o una muestra de lago) en un día.**
   - No mezclar especies en el capilar para el dataset de entrenamiento.
   - Así la etiqueta de especie sale del cultivo y el etiquetado se reduce a separar alga / no alga / borroso / duda.
5. **Variedad:**
   - Al menos **5 sesiones por especie**, en días distintos y con cultivos de edades distintas.
   - Cambiar la dilución y, si es posible, la intensidad del LED entre sesiones.
6. **Cuánto:**
   - Objetivo: **≥ 300 recortes válidos por clase** para un primer modelo; 600 o más es mejor.
   - Referencia: en LMFM-12, unas 600 imágenes por especie dieron ~99,9 % en su propio dominio.
   - Las clases `no_alga_*` y `borroso` salen solas de las mismas sesiones.

## 4. Metadatos: `datos/sesiones.csv`

Una fila por sesión. La escribe la app: panel *Session* → *Start session* antes de la primera foto y *End session*
al terminar. La fila queda en `samples/sesiones.csv`: descárgala y añádela a `datos/sesiones.csv`, rellenando
`particion` antes de entrenar.

```
sesion,fecha,origen,especie_cultivo,edad_cultivo_dias,dilucion,operador,fotos_desde,fotos_hasta,serie,um_por_px,particion,notas
S001,2026-11-05,cultivo,chlorella_vulgaris,7,1:10,Daniela,12,40,serie_3.csv,0.0,train,
```

`fotos_desde`–`fotos_hasta` son los números de foto de la app (`objetos_<n>.csv`, recortes `<n>_...png`). Con eso
cada recorte queda ligado a su sesión. `particion` (train/val/test) se decide antes de entrenar (§6) y
`src/ml/prepara_dataset.py` la usa para montar el dataset.

## 5. Etiquetado

**Opción recomendada: EcoTaxa.**
- **Download EcoTaxa** en Samples genera un zip con los recortes y su TSV: medidas, etiqueta de la app y clase del
  modelo como columna informativa, sin anotación.
- Se importa en un proyecto de EcoTaxa, Daniela valida las categorías de la tabla de arriba y se exporta el TSV
  validado.

**Alternativa sin internet:** mover los PNG de `recortes/` a carpetas con el nombre de la clase.

**Control de calidad:**
- Una segunda persona etiqueta a ciegas el 10 % de los recortes de cada clase y se anota el acuerdo.
- Antes de entrenar se hace validación cruzada y se revisan solo los recortes sospechosos: baja confianza en su
  propia etiqueta o vecinos de otra clase, como hace PlanktonLake-CEREEP.

## 6. Particiones: SIEMPRE por sesión

- **test:** 1 sesión por especie, elegida antes de entrenar y que no se toca hasta el final. Más todas las sesiones de
  lago, como prueba de objetos que el modelo no conoce.
- **validación:** 1 sesión por especie, para elegir hiperparámetros y el umbral de confianza.
- **entrenamiento:** el resto.
- **Prohibido** repartir recortes de una misma sesión entre particiones: las células de un mismo cultivo y día se
  parecen demasiado y la cifra saldría inflada.
- Comprobación automática antes de entrenar: ningún recorte de test o validación puede tener una copia exacta (md5) o
  casi exacta (dHash) en entrenamiento. Se reutiliza `src/ml/evaluar_modelo.py`.

## 7. Cómo se evaluará (no hay modelo sin estos números)

- **Por clase:** precisión, recall y matriz de confusión en test, con intervalos de confianza.
- **Exactitud balanceada.** Las clases no tendrán el mismo número de recortes.
- **Por conteos:** error del recuento por clase en cada sesión de test, que es lo que usa el artículo.
- **Objetos desconocidos (sesiones de lago):** qué fracción de objetos fuera de clase se clasifica como una de las dos
  especies.
- **Umbral de confianza:** el que conserva el 95 % de recall en validación (como en
  `modelos/plankton_mobilenet_v1/calibracion_2026-11-01`).
- **Ficha:** todo queda en `modelos/<nombre>/FICHA.md` junto al `.tflite`.
