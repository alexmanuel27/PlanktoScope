# Prueba de foco — cámara de 2 lentes en Raspberry Pi 5

Servidor web mínimo para ver la cámara de la Pi desde el navegador de otro equipo y medir
si toda la imagen está enfocada a la vez.

## Archivos
- `camara_web.py` — se ejecuta **en la Pi**. Muestra la cámara en el navegador (MJPEG),
  con medida de foco global y en rejilla 3×3, y botón de foto (se guarda en la Pi en
  `capturas/` y se descarga en tu equipo). Si hay dos cámaras conectadas, muestra las dos.
- `buscar_raspi.sh` — se ejecuta **en el Mac** para encontrar la IP de la Pi.

## Pasos
1. Conecta el Mac a la misma red que la Pi y busca su IP:
   ```bash
   bash buscar_raspi.sh
   ```
   Si estás en una wifi que crea la propia Pi, su IP suele ser la del router que muestra
   el script. Si tienes la Pi con pantalla/teclado: `hostname -I`.
2. Copia el programa y arráncalo (usuario `alex`):
   ```bash
   scp camara_web.py alex@IP_DE_LA_PI:~
   ssh alex@IP_DE_LA_PI
   rpicam-hello --list-cameras     # comprobar que la Pi ve la cámara
   python3 camara_web.py           # opcional: --ancho 1920 --alto 1080
   ```
3. Abre en el navegador: `http://IP_DE_LA_PI:8000`

## Cómo leer la medida de foco
- **Foco global**: varianza del laplaciano. Más alto = más nítido. Solo sirve para comparar
  la misma escena (cambia con iluminación y contenido).
- **Rejilla 3×3**: verde = zona más nítida, rojo = más borrosa.
- **Uniformidad (mín/máx)**: cercano a 1 = toda la imagen igual de enfocada. Para probar
  lo de "todo el foco sin mover nada", pon una muestra con relieve (o una regla inclinada)
  y mira si la uniformidad se mantiene alta.

## Problemas típicos
- `No se detecta ninguna cámara`: cinta mal puesta o al revés; en la Pi 5 se usa la cinta
  estrecha de 22 pines. Revisa con `rpicam-hello --list-cameras`.
- `No se pudo abrir la cámara ... ¿Otro programa la está usando?`: si la Pi lleva el
  software del PlanktoScope, su servicio tiene la cámara ocupada; páralo antes.
- Si la cámara no es de Raspberry Pi (p. ej. Arducam), puede necesitar una línea
  `dtoverlay=...` en `/boot/firmware/config.txt` según el modelo.
