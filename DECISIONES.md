# DECISIONES

Cada opción descartada, con fecha y motivo. Lo que no está aquí no está decidido.

| Fecha | Decisión | Descartado | Por qué |
|---|---|---|---|
| sep 2026 (antes del 27/09) | El índice de calidad de agua sale del alcance del artículo y se retira de la aplicación | Mantener el índice o adaptarlo | Los ~19 géneros del índice son mayoritariamente marinos (05/10: la app usa las mismas 19 etiquetas que el modelo, no 5); no es aplicable a estanques de agua dulce de Bruselas |
| sep 2026 | El entorno de ejecución se resuelve con un entorno único con acceso a paquetes del sistema (`--system-site-packages`) o con contenedor; se elige entre ambos el 29–30/09 tras el diagnóstico | Seguir lanzando la app fuera del venv; activar/desactivar el venv desde el clasificador; cualquier otro parche | `picamera2`/libcamera solo funciona con paquetes del sistema y `ai_edge_litert` solo estaba en el venv: la combinación actual se rompe con cualquier cambio y en campo supone perder la sesión |
| sep 2026 | El clasificador se reentrena especializado en las especies compradas (plan K3.2/K3.5) | Seguir con el modelo de 19 géneros marinos | Ver ESTADO.md A2–A3 |
| sep 2026 | El manuscrito vive en `publication plan/Modular-Planktoscope` (Daniela); este repo es solo de ingeniería | — | Separación de responsabilidades |
