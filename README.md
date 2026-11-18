# Mi Clipper Personal

Aplicación personal en Python y Streamlit para descargar o cargar videos, transcribirlos y seleccionar clips automáticamente.

## Funcionalidades

- Descarga de videos mediante yt-dlp o carga de archivos locales.
- Extracción de audio con FFmpeg.
- Transcripción local con faster-whisper.
- Selección inteligente de segmentos con Gemini.
- Modo rápido basado en análisis de volumen.
- Recorte horizontal 16:9 y vertical 9:16.
- Títulos, ganchos y voz narradora.
- Editor vertical 9:16 para conservar el gameplay y superponer la cámara del streamer con recortes y posición ajustables.
- Exportación de varios clips seleccionados en un único archivo ZIP.
- Reproducción, guardado y descarte de clips.

## Duraciones

| Formato | Duraciones |
|---|---|
| Vertical 9:16 | 30, 40 y 45 segundos |
| Horizontal 16:9 | 3, 5 y 8 minutos |

En el formato horizontal, el modo inteligente también puede generar un resumen y puntos clave por segmento. La duración es aproximada: se permite una tolerancia del 5 % para respetar el cierre de las frases.

## Requisitos

- Python 3.10 o superior.
- FFmpeg instalado y disponible en PATH.
- Una clave de Gemini para la selección inteligente (opcional; el modo rápido no la necesita).
- Conexión a internet para descargar videos y generar voz con Edge TTS.

## Instalación

1. Clonar el repositorio.
2. Crear y activar un entorno virtual.
3. Instalar dependencias:

```bash
pip install -r requirements.txt
```

4. Instalar FFmpeg y comprobar que los comandos `ffmpeg` y `ffprobe` funcionan.
5. Ejecutar:

```bash
streamlit run app.py
```

## Uso recomendado

- Usa 9:16 para Shorts, Reels y TikTok.
- Usa 16:9 para segmentos largos de YouTube.
- Para segmentos de 3, 5 u 8 minutos, usa el modo Inteligente para obtener resumen y puntos clave.
- El video de origen debe tener suficiente contenido hablado para completar la duración solicitada.

## Estado

Proyecto personal en desarrollo.

## Editor vertical para streamers

Al generar clips en formato 9:16, Mi Clipper conserva temporalmente el fragmento original completo para abrir el editor vertical. En cada clip puedes ajustar en porcentajes el recorte del gameplay y el recorte de la webcam, elegir si la cámara aparece arriba o abajo, alinear a izquierda/centro/derecha y cambiar su tamaño. La vista previa muestra las dos áreas y el resultado vertical. La composición se renderiza localmente con FFmpeg, sin APIs ni servicios externos.

La exportación múltiple permite marcar varios clips y reunir sus versiones finales en un ZIP.
