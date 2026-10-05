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

### C3. Lo que falla hoy (rellenar tras C1–C2)

—
