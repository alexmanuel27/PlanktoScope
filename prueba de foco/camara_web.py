#!/usr/bin/env python3
"""
Ver la(s) cámara(s) de la Raspberry Pi 5 en un navegador web, con medida de foco.

En la Pi:
    python3 camara_web.py                  # 1280x720, puerto 8000
    python3 camara_web.py --ancho 1920 --alto 1080 --puerto 8080

Luego, desde cualquier equipo en la misma red:  http://IP_DE_LA_PI:8000

Requiere Raspberry Pi OS Bookworm (picamera2, numpy y simplejpeg ya vienen instalados).
Si hay dos cámaras (los dos puertos CSI de la Pi 5) se muestran las dos.

Medida de foco: varianza del laplaciano (más alto = más nítido), global y en una
rejilla 3x3, para comprobar si toda la imagen está enfocada a la vez.
"""
import argparse
import io
import json
import os
import subprocess
import threading
import time
from http import server
from socketserver import ThreadingMixIn

import numpy as np
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

CARPETA_FOTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capturas")


class SalidaStream(io.BufferedIOBase):
    """Guarda el último JPEG y avisa a los clientes que esperan."""

    def __init__(self):
        self.frame = None
        self.condicion = threading.Condition()

    def write(self, buf):
        with self.condicion:
            self.frame = buf
            self.condicion.notify_all()


class Camara:
    def __init__(self, num, info, ancho, alto, calidad):
        self.num = num
        self.modelo = info.get("Model", "?")
        self.picam2 = Picamera2(num)
        config = self.picam2.create_video_configuration(main={"size": (ancho, alto)})
        self.picam2.configure(config)
        self.tam = self.picam2.camera_config["main"]["size"]
        self.salida = SalidaStream()
        self.picam2.start_recording(JpegEncoder(q=calidad), FileOutput(self.salida))
        self.foco = {"total": 0.0, "rejilla": [[0.0] * 3 for _ in range(3)]}
        threading.Thread(target=self._medir_foco, daemon=True).start()

    def _medir_foco(self):
        while True:
            try:
                img = self.picam2.capture_array("main")
                g = img[::2, ::2, :3].astype(np.float32).mean(axis=2)
                lap = (4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1]
                       - g[1:-1, :-2] - g[1:-1, 2:])
                h, w = lap.shape
                rejilla = [[float(lap[f * h // 3:(f + 1) * h // 3,
                                      c * w // 3:(c + 1) * w // 3].var())
                            for c in range(3)] for f in range(3)]
                self.foco = {"total": float(lap.var()), "rejilla": rejilla}
            except Exception as e:  # no tumbar el servidor por un fallo puntual
                print(f"[cam {self.num}] error midiendo foco: {e}")
            time.sleep(0.5)

    def foto(self):
        """Captura un JPEG a la resolución actual, lo guarda en la Pi y lo devuelve."""
        buf = io.BytesIO()
        self.picam2.capture_file(buf, format="jpeg")
        datos = buf.getvalue()
        os.makedirs(CARPETA_FOTOS, exist_ok=True)
        nombre = time.strftime(f"cam{self.num}_%Y%m%d_%H%M%S.jpg")
        with open(os.path.join(CARPETA_FOTOS, nombre), "wb") as f:
            f.write(datos)
        return nombre, datos


PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cámara Pi — prueba de foco</title>
<style>
 body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:12px}
 h1{font-size:18px;margin:0 0 10px}
 .cams{display:flex;flex-wrap:wrap;gap:16px}
 .cam{flex:1 1 600px;max-width:100%}
 .marco{position:relative}
 .marco img{width:100%;display:block;background:#000}
 .rej{position:absolute;inset:0;display:grid;grid-template:repeat(3,1fr)/repeat(3,1fr)}
 .rej div{border:1px solid rgba(255,255,255,.25);display:flex;align-items:flex-start;
   justify-content:flex-start;font:12px monospace;padding:3px;color:#fff;text-shadow:0 0 3px #000}
 .rej.oculta{display:none}
 .barra{display:flex;gap:12px;align-items:center;margin:6px 0;flex-wrap:wrap;font-size:14px}
 button,a.btn{background:#2d6cdf;color:#fff;border:0;border-radius:6px;padding:6px 12px;
   cursor:pointer;text-decoration:none;font-size:14px}
 .num{font:16px monospace;color:#7fd17f}
</style></head><body>
<h1>Cámara Raspberry Pi — prueba de foco</h1>
<div class="cams" id="cams"></div>
<script>
const CAMS = __CAMS__;
const cont = document.getElementById('cams');
for (const c of CAMS) {
  cont.insertAdjacentHTML('beforeend', `
  <div class="cam">
    <div class="barra"><b>Cámara ${c.num}</b> <span>${c.modelo} · ${c.ancho}×${c.alto}</span></div>
    <div class="marco"><img src="/stream/${c.num}.mjpg">
      <div class="rej" id="rej${c.num}">${'<div></div>'.repeat(9)}</div></div>
    <div class="barra">
      Foco global: <span class="num" id="tot${c.num}">–</span>
      Uniformidad (mín/máx): <span class="num" id="uni${c.num}">–</span>
      <button onclick="document.getElementById('rej${c.num}').classList.toggle('oculta')">Rejilla</button>
      <a class="btn" href="/foto/${c.num}.jpg">Foto</a>
    </div>
  </div>`);
}
async function actualizar() {
  try {
    const datos = await (await fetch('/foco.json')).json();
    for (const d of datos) {
      const vals = d.rejilla.flat(), max = Math.max(...vals) || 1, min = Math.min(...vals);
      document.getElementById('tot' + d.num).textContent = d.total.toFixed(1);
      document.getElementById('uni' + d.num).textContent = (min / max).toFixed(2);
      document.querySelectorAll('#rej' + d.num + ' div').forEach((el, i) => {
        const r = vals[i] / max;  // verde = zona más nítida, rojo = más borrosa
        el.textContent = vals[i].toFixed(0);
        el.style.background = `rgba(${Math.round(255 * (1 - r))},${Math.round(200 * r)},0,.18)`;
      });
    }
  } catch (e) {}
  setTimeout(actualizar, 700);
}
actualizar();
</script></body></html>"""


class Manejador(server.BaseHTTPRequestHandler):
    camaras = []

    def log_message(self, *a):  # silenciar el log de cada petición
        pass

    def _enviar(self, codigo, tipo, cuerpo, extra=None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def _camara(self, prefijo, sufijo):
        try:
            n = int(self.path[len(prefijo):-len(sufijo)])
            return next(c for c in self.camaras if c.num == n)
        except (ValueError, StopIteration):
            return None

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            cams = [{"num": c.num, "modelo": c.modelo, "ancho": c.tam[0], "alto": c.tam[1]}
                    for c in self.camaras]
            html = PAGINA.replace("__CAMS__", json.dumps(cams))
            self._enviar(200, "text/html; charset=utf-8", html.encode())
        elif self.path == "/foco.json":
            datos = [{"num": c.num, **c.foco} for c in self.camaras]
            self._enviar(200, "application/json", json.dumps(datos).encode())
        elif self.path.startswith("/stream/") and self.path.endswith(".mjpg"):
            cam = self._camara("/stream/", ".mjpg")
            if cam is None:
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with cam.salida.condicion:
                        cam.salida.condicion.wait()
                        frame = cam.salida.frame
                    self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # el navegador cerró la pestaña
        elif self.path.startswith("/foto/") and self.path.endswith(".jpg"):
            cam = self._camara("/foto/", ".jpg")
            if cam is None:
                return self.send_error(404)
            nombre, datos = cam.foto()
            print(f"Foto guardada en la Pi: capturas/{nombre}")
            self._enviar(200, "image/jpeg", datos,
                         {"Content-Disposition": f'attachment; filename="{nombre}"'})
        else:
            self.send_error(404)


class Servidor(ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def ips_locales():
    try:
        return subprocess.check_output(["hostname", "-I"], text=True).split()
    except Exception:
        return []


def main():
    p = argparse.ArgumentParser(description="Streaming web de la cámara de la Pi")
    p.add_argument("--ancho", type=int, default=1280)
    p.add_argument("--alto", type=int, default=720)
    p.add_argument("--calidad", type=int, default=85, help="calidad JPEG 1-100")
    p.add_argument("--puerto", type=int, default=8000)
    a = p.parse_args()

    infos = Picamera2.global_camera_info()
    if not infos:
        raise SystemExit("No se detecta ninguna cámara. Revisa la cinta (contactos hacia "
                         "el lado correcto) y prueba:  rpicam-hello --list-cameras")
    for i, info in enumerate(infos):
        print(f"Cámara {i}: {info}")

    camaras = []
    for i, info in enumerate(infos):
        try:
            camaras.append(Camara(i, info, a.ancho, a.alto, a.calidad))
        except Exception as e:
            print(f"No se pudo abrir la cámara {i}: {e}\n"
                  "  ¿Otro programa la está usando? (p. ej. el servicio del PlanktoScope)")
    if not camaras:
        raise SystemExit("Ninguna cámara disponible.")
    Manejador.camaras = camaras

    print("\nAbre en el navegador:")
    for ip in ips_locales() or ["IP_DE_LA_PI"]:
        if ":" not in ip:  # solo IPv4
            print(f"   http://{ip}:{a.puerto}")
    print("Ctrl+C para salir.\n")

    srv = Servidor(("", a.puerto), Manejador)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for c in camaras:
            c.picam2.stop_recording()


if __name__ == "__main__":
    main()
