# Modular PlanktoScope — resumen de mejoras

## 1. Motores y hardware
- **Arranque suave** de los motores: antes daban tirones, ahora aceleran poco a poco.
- **Motor del enfoque:** ajustado para moverse con más suavidad.
- **Bomba:** ya no se traba al arrancar, y la luz se apaga mientras bombea para no gastar energía de más.
- **Arranque de la Raspberry:** con los dos motores conectados no arranca por falta de energía; de momento se conectan después de encender. Queda anotado para mejorarlo en la próxima placa.

## 2. Cámara y fotos
- **Fotos más grandes y detalladas** (2028×1520 píxeles). 
- Al pulsar **Capture Photo** se guarda la foto clasificada y también la original sin tocar.
- La **consola** de mensajes ya no se queda en "Connecting...".
- En *Samples* se puede abrir cada imagen al pulsarla, y la opción de ignorar límites funciona.

## 3. Enfoque automático y capas
- **Autofoco:** el equipo recorre el rango y elige el punto más nítido. Coincide con el enfoque manual.
- **Captura por capas:** como la muestra va en un capilar, las algas quedan a distintas profundidades. El equipo detecta cada nivel y hace una foto de cada uno.
- Descarta capas repetidas, así no cuenta dos veces la misma alga.
- Corregido que un objeto grande engañara al enfoque(ya no pasa).

## 4. Detección y clasificación
- **Detección de objetos** con corrección del fondo (quita manchas y reflejos fijos del cristal).
- **Medidas de cada objeto:** tamaño, forma y color. Se pueden dar en micras tras calibrar con una regla de microscopio.
- **Clasificador más honesto:** corregimos un fallo que le restaba acierto (de 0,74 a 0,84) y ahora solo da un nombre si está seguro (al menos 55 %). Si no, lo deja como "objeto".
- **Recorte** de cada objeto en alta resolución.
- Umbral de confianza calibrado y ficha del modelo documentada.

## 5. Series en el tiempo (panel derecho)
- La bomba toma muestras automáticamente cada cierto tiempo; la serie corre sola y va mostrando una gráfica.
- Ignora lo que no se mueve (suciedad pegada) y usa su propio fondo.
- Se guarda un archivo con la hora, los objetos, las clases y la cantidad por mililitro.
- Mientras corre una serie, la interfaz se bloquea para que nadie la estropee sin querer.
- **Luz:** se enciende al pulsar Start, está apagada en reposo y **parpadea al terminar**.
- **Barra de espacio** de la tarjeta SD en una esquina.

## 6. Datos y EcoTaxa
- **Exportación a EcoTaxa** con un botón (plataforma científica para identificar plancton).
- **Sesiones:** cada día de trabajo queda registrado con el cultivo, su edad, la dilución y quién lo hizo.
- **Protocolo para crear nuestra colección de imágenes** (`datos/PROTOCOLO_DATASET.md`): categorías (Chlorella vulgaris, Acutodesmus obliquus, otra alga, fibra, burbuja, detrito, borroso, duda) y separación por sesión para que la evaluación sea justa.

## 6b. Entrenamiento de nuestro propio modelo
- Programas para preparar los datos, entrenar, evaluar y calibrar el clasificador.
- Probado con una colección pública (LMFM-12) con buen resultado (0,813 de acierto).
- Incidente: se sobrescribieron por error dos archivos; se restauraron, se comprobaron y quedó registrado.

## 7. Volumen
- Se calcula el volumen de cada foto y el volumen bombeado; se calibra en Ajustes.
- **En diseño:** medir el volumen real con una cámara externa apuntando al tubo de destino, con una pelotita flotante que marque el nivel. Se calibra añadiendo cantidades conocidas de 5 en 5 mL.

## Pendientes
2. Foto de prueba del tubo con la pelotita.
3. Calibrar el tamaño (regla de microscopio), el grosor del capilar y la bomba(esto se que lo tienes pero yo aun no lo subo).
4. Reunir fotos reales de las algas y rellenar la tabla de sesiones antes de entrenar.
