# DECISIONES

Cada opción descartada, con fecha y motivo. Lo que no está aquí no está decidido.

| Fecha | Decisión | Descartado | Por qué |
|---|---|---|---|
| sep 2026 (antes del 27/09) | El índice de calidad de agua sale del alcance del artículo y se retira de la aplicación | Mantener el índice o adaptarlo | Los ~19 géneros del índice son mayoritariamente marinos (05/10: la app usa las mismas 19 etiquetas que el modelo, no 5); no es aplicable a estanques de agua dulce de Bruselas |
| sep 2026 | El entorno de ejecución se resuelve con un entorno único con acceso a paquetes del sistema (`--system-site-packages`) o con contenedor; se elige entre ambos el 29–30/09 tras el diagnóstico | Seguir lanzando la app fuera del venv; activar/desactivar el venv desde el clasificador; cualquier otro parche | `picamera2`/libcamera solo funciona con paquetes del sistema y `ai_edge_litert` solo estaba en el venv: la combinación actual se rompe con cualquier cambio y en campo supone perder la sesión |
| sep 2026 | El clasificador se reentrena especializado en las especies compradas (plan K3.2/K3.5) | Seguir con el modelo de 19 géneros marinos | Ver ESTADO.md A2–A3 |
| sep 2026 | El manuscrito vive en `publication plan/Modular-Planktoscope` (Daniela); este repo es solo de ingeniería | — | Separación de responsabilidades |
| 06/10/2026 | La placa actual se queda como está: se arranca la Raspberry con los motores sin alimentar y la resistencia de EN pasa de GND a 3,3 V en la próxima versión del HAT | Añadir ahora una resistencia de 1 kΩ de EN a 3,3 V en cada driver | Decisión de Alex: no tocar la placa montada antes del envío. Con EN a GND los drivers están activados durante el arranque y la Raspberry no llega a arrancar |
| 06/10/2026 | `config.txt`: `gpio=9,13=op,dh,pu` y SPI desactivado (copia en `sistema/config.txt` cuando se traiga) | — | Mantiene EN en alto después del arranque y al cerrarse la app; GPIO9/11 estaban tomados por el SPI |
| 07/10/2026 | Entorno: el venv existente pasa a `include-system-site-packages = true` y se le quitan los paquetes que ya da el sistema (picamera2, numpy, opencv…); un único servicio systemd lo lanza (`sistema/arreglar_entorno.sh`) | Contenedor; venv nuevo descargando paquetes | Funciona sin internet (la Raspberry está en modo punto de acceso), se puede deshacer con la copia del venv y deja un solo intérprete |
| 07/10/2026 | Índice de calidad de agua retirado de la app (barra, categoría y score fuera del nombre de la foto) | — | Ejecución de la decisión de septiembre |
| 07/10/2026 | Energía: LED apagado mientras gira la bomba y reencendido suave (~0,5 s, PWM) tras `led_delay_after_pump`; foco sin rampa a velocidad constante lenta | Rampa en el foco | Los movimientos del foco son cortos (100 pasos) y la rampa no llegaba a crucero |
