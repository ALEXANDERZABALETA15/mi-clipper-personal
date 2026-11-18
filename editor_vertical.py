"""Editor local para clips verticales con gameplay y cámara superpuesta.

Todo el procesamiento se realiza con FFmpeg y Pillow, sin APIs ni servicios externos.
"""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


class ErrorEditorVertical(RuntimeError):
    """Error controlado del editor vertical."""


def rectangulo_a_pixeles(rectangulo: dict[str, float], ancho: int, alto: int) -> tuple[int, int, int, int]:
    """Convierte un rectángulo expresado en porcentajes a coordenadas pares."""
    if ancho < 4 or alto < 4:
        raise ErrorEditorVertical("El video de origen tiene una resolución demasiado pequeña.")

    try:
        x = float(rectangulo["x"])
        y = float(rectangulo["y"])
        porcentaje_ancho = float(rectangulo["ancho"])
        porcentaje_alto = float(rectangulo["alto"])
    except (KeyError, TypeError, ValueError) as error:
        raise ErrorEditorVertical("La selección de recorte está incompleta.") from error

    valores = (x, y, porcentaje_ancho, porcentaje_alto)
    if any(valor != valor or valor in (float("inf"), float("-inf")) for valor in valores):
        raise ErrorEditorVertical("Los valores del recorte no son válidos.")
    if x < 0 or y < 0 or porcentaje_ancho <= 0 or porcentaje_alto <= 0:
        raise ErrorEditorVertical("El recorte debe tener posición y tamaño positivos.")
    if x + porcentaje_ancho > 100.001 or y + porcentaje_alto > 100.001:
        raise ErrorEditorVertical("El recorte se sale de los límites del video.")

    izquierda = int(round(ancho * x / 100))
    superior = int(round(alto * y / 100))
    ancho_recorte = int(round(ancho * porcentaje_ancho / 100))
    alto_recorte = int(round(alto * porcentaje_alto / 100))

    izquierda = max(0, min(izquierda, ancho - 2))
    superior = max(0, min(superior, alto - 2))
    izquierda -= izquierda % 2
    superior -= superior % 2
    ancho_recorte = min(ancho_recorte, ancho - izquierda)
    alto_recorte = min(alto_recorte, alto - superior)
    ancho_recorte -= ancho_recorte % 2
    alto_recorte -= alto_recorte % 2

    if ancho_recorte < 2 or alto_recorte < 2:
        raise ErrorEditorVertical("El área seleccionada es demasiado pequeña.")
    return izquierda, superior, ancho_recorte, alto_recorte


def validar_configuracion(configuracion: dict[str, Any]) -> None:
    """Valida las opciones antes de generar una composición."""
    if configuracion.get("camara_posicion", "Superior") not in ("Superior", "Inferior"):
        raise ErrorEditorVertical("La posición vertical de la cámara no es válida.")
    if configuracion.get("camara_alineacion", "Derecha") not in ("Izquierda", "Centro", "Derecha"):
        raise ErrorEditorVertical("La alineación de la cámara no es válida.")
    try:
        ancho = int(configuracion.get("camara_ancho", 45))
    except (TypeError, ValueError) as error:
        raise ErrorEditorVertical("El tamaño de la cámara no es válido.") from error
    if not 25 <= ancho <= 65:
        raise ErrorEditorVertical("El tamaño de la cámara debe estar entre 25 % y 65 %.")
    if "gameplay" not in configuracion or "camara" not in configuracion:
        raise ErrorEditorVertical("Debes indicar las áreas de gameplay y cámara.")


def obtener_dimensiones(ruta_video: str | Path) -> tuple[int, int]:
    """Obtiene el ancho y alto del primer flujo de video con ffprobe."""
    try:
        resultado = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "json", str(ruta_video),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        flujos = json.loads(resultado.stdout).get("streams", [])
        if not flujos:
            raise ErrorEditorVertical("No encontré una pista de video en el archivo original.")
        ancho, alto = int(flujos[0]["width"]), int(flujos[0]["height"])
        if ancho < 4 or alto < 4:
            raise ErrorEditorVertical("La resolución del video no es válida.")
        return ancho, alto
    except FileNotFoundError as error:
        raise ErrorEditorVertical("No encuentro FFprobe. Comprueba que FFmpeg esté en el PATH.") from error
    except subprocess.TimeoutExpired as error:
        raise ErrorEditorVertical("La lectura de la información del video tardó demasiado.") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode(errors="replace")[-600:]
        raise ErrorEditorVertical("No pude leer la resolución del video: " + detalle) from error
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise ErrorEditorVertical("FFprobe devolvió información de video no válida.") from error


def crear_clip_fuente(
    video_original: str | Path,
    inicio: float,
    fin: float,
    destino: str | Path,
    max_ancho: int = 1280,
) -> Path:
    """Guarda el fragmento completo, sin recorte vertical, para poder editarlo después."""
    origen = Path(video_original)
    salida = Path(destino)
    if not origen.is_file():
        raise ErrorEditorVertical("No encuentro el video original para preparar el editor.")
    if float(fin) <= float(inicio):
        raise ErrorEditorVertical("El tiempo de inicio y fin del clip no es válido.")
    salida.parent.mkdir(parents=True, exist_ok=True)
    filtro = f"scale='min({int(max_ancho)},iw)':-2"

    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-y", "-ss", f"{float(inicio):.3f}",
                "-i", str(origen), "-t", f"{float(fin) - float(inicio):.3f}",
                "-map", "0:v:0", "-map", "0:a?", "-vf", filtro,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(salida),
            ],
            check=True,
            capture_output=True,
            timeout=900,
        )
    except FileNotFoundError as error:
        raise ErrorEditorVertical("No encuentro FFmpeg. Comprueba que esté instalado y en el PATH.") from error
    except subprocess.TimeoutExpired as error:
        raise ErrorEditorVertical("La preparación del fragmento original superó los 15 minutos.") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode(errors="replace")[-900:]
        raise ErrorEditorVertical("No pude conservar el fragmento original: " + detalle) from error

    if not salida.is_file() or salida.stat().st_size == 0:
        raise ErrorEditorVertical("FFmpeg no generó el fragmento original del editor.")
    return salida


def _extraer_fotograma(ruta_video: str | Path, segundo: float = 1.0) -> Image.Image:
    try:
        resultado = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(max(0, segundo)),
                "-i", str(ruta_video), "-frames:v", "1", "-f", "image2pipe",
                "-vcodec", "mjpeg", "pipe:1",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return Image.open(io.BytesIO(resultado.stdout)).convert("RGB")
    except FileNotFoundError as error:
        raise ErrorEditorVertical("No encuentro FFmpeg para crear la vista previa.") from error
    except subprocess.TimeoutExpired as error:
        raise ErrorEditorVertical("La extracción de la vista previa tardó demasiado.") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode(errors="replace")[-600:]
        raise ErrorEditorVertical("No pude obtener un fotograma del video: " + detalle) from error
    except (OSError, ValueError) as error:
        raise ErrorEditorVertical("No pude leer el fotograma del video original.") from error


def crear_previsualizaciones(
    ruta_video: str | Path,
    configuracion: dict[str, Any],
    ancho_salida: int = 360,
) -> tuple[bytes, bytes]:
    """Devuelve (fotograma con áreas marcadas, composición vertical de muestra)."""
    validar_configuracion(configuracion)
    fotograma = _extraer_fotograma(ruta_video)
    ancho, alto = fotograma.size
    caja_game = rectangulo_a_pixeles(configuracion["gameplay"], ancho, alto)
    caja_camara = rectangulo_a_pixeles(configuracion["camara"], ancho, alto)

    marcado = fotograma.copy()
    dibujo = ImageDraw.Draw(marcado)
    grosor = max(3, ancho // 250)
    dibujo.rectangle(
        (caja_game[0], caja_game[1], caja_game[0] + caja_game[2], caja_game[1] + caja_game[3]),
        outline=(255, 70, 70), width=grosor,
    )
    dibujo.rectangle(
        (caja_camara[0], caja_camara[1], caja_camara[0] + caja_camara[2], caja_camara[1] + caja_camara[3]),
        outline=(40, 220, 110), width=grosor,
    )
    try:
        fuente = ImageFont.truetype("arial.ttf", max(16, ancho // 45))
    except OSError:
        fuente = ImageFont.load_default()
    dibujo.text((12, 12), "GAMEPLAY", fill=(255, 90, 90), font=fuente, stroke_width=2, stroke_fill="black")
    dibujo.text((12, 38), "CÁMARA", fill=(40, 240, 120), font=fuente, stroke_width=2, stroke_fill="black")

    salida_alto = int(ancho_salida * 16 / 9)
    caja_game_imagen = fotograma.crop(
        (caja_game[0], caja_game[1], caja_game[0] + caja_game[2], caja_game[1] + caja_game[3])
    )
    composicion = ImageOps.fit(
        caja_game_imagen,
        (ancho_salida, salida_alto),
        method=Image.Resampling.LANCZOS,
    )

    camara = fotograma.crop(
        (caja_camara[0], caja_camara[1], caja_camara[0] + caja_camara[2], caja_camara[1] + caja_camara[3])
    )
    ancho_camara = max(2, int(ancho_salida * int(configuracion.get("camara_ancho", 45)) / 100))
    alto_maximo = int(salida_alto * 0.36)
    camara.thumbnail((ancho_camara, alto_maximo), Image.Resampling.LANCZOS)
    borde = max(2, ancho_salida // 180)
    marco = Image.new("RGB", (camara.width + borde * 2, camara.height + borde * 2), "white")
    marco.paste(camara, (borde, borde))

    alineacion = configuracion.get("camara_alineacion", "Derecha")
    margen = max(8, ancho_salida // 24)
    if alineacion == "Izquierda":
        x = margen
    elif alineacion == "Centro":
        x = (ancho_salida - marco.width) // 2
    else:
        x = ancho_salida - marco.width - margen
    y = margen if configuracion.get("camara_posicion", "Superior") == "Superior" else salida_alto - marco.height - margen
    composicion.paste(marco, (max(0, x), max(0, y)))

    salida_marcado = io.BytesIO()
    salida_composicion = io.BytesIO()
    marcado.thumbnail((960, 540), Image.Resampling.LANCZOS)
    marcado.save(salida_marcado, format="JPEG", quality=88, optimize=True)
    composicion.save(salida_composicion, format="JPEG", quality=88, optimize=True)
    return salida_marcado.getvalue(), salida_composicion.getvalue()


def aplicar_composicion(
    ruta_video: str | Path,
    configuracion: dict[str, Any],
    ancho_salida: int = 720,
) -> bytes:
    """Renderiza gameplay 9:16 con la webcam recortada y superpuesta."""
    validar_configuracion(configuracion)
    origen = Path(ruta_video)
    if not origen.is_file():
        raise ErrorEditorVertical("No encuentro el fragmento original de este clip.")
    if ancho_salida not in (540, 720):
        raise ErrorEditorVertical("La resolución de salida debe ser 540 o 720 píxeles de ancho.")

    ancho_origen, alto_origen = obtener_dimensiones(origen)
    gx, gy, gw, gh = rectangulo_a_pixeles(configuracion["gameplay"], ancho_origen, alto_origen)
    cx, cy, cw, ch = rectangulo_a_pixeles(configuracion["camara"], ancho_origen, alto_origen)

    alto_salida = ancho_salida * 16 // 9
    ancho_camara = int(ancho_salida * int(configuracion.get("camara_ancho", 45)) / 100)
    ancho_camara -= ancho_camara % 2
    alto_maximo_camara = int(alto_salida * 0.36)
    margen = max(18, ancho_salida // 24)
    alineacion = configuracion.get("camara_alineacion", "Derecha")
    if alineacion == "Izquierda":
        posicion_x = str(margen)
    elif alineacion == "Centro":
        posicion_x = "(main_w-overlay_w)/2"
    else:
        posicion_x = f"main_w-overlay_w-{margen}"
    posicion_y = str(margen) if configuracion.get("camara_posicion", "Superior") == "Superior" else "main_h-overlay_h-" + str(margen)

    filtros = (
        f"[0:v]crop={gw}:{gh}:{gx}:{gy},"
        f"scale={ancho_salida}:{alto_salida}:force_original_aspect_ratio=increase,"
        f"crop={ancho_salida}:{alto_salida},setsar=1[game];"
        f"[0:v]crop={cw}:{ch}:{cx}:{cy},"
        f"scale={ancho_camara}:{alto_maximo_camara}:force_original_aspect_ratio=decrease,"
        f"pad=iw+8:ih+8:4:4:color=white,setsar=1[cam];"
        f"[game][cam]overlay=x={posicion_x}:y={posicion_y}:shortest=1,format=yuv420p[outv]"
    )

    try:
        with tempfile.TemporaryDirectory(prefix="mi_clipper_export_") as temporal:
            salida = Path(temporal) / "clip_vertical_editor.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-y", "-i", str(origen),
                    "-filter_complex", filtros, "-map", "[outv]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(salida),
                ],
                check=True,
                capture_output=True,
                timeout=900,
            )
            if not salida.is_file() or salida.stat().st_size == 0:
                raise ErrorEditorVertical("FFmpeg terminó, pero no generó el clip compuesto.")
            return salida.read_bytes()
    except FileNotFoundError as error:
        raise ErrorEditorVertical("No encuentro FFmpeg. Comprueba que esté instalado y en el PATH.") from error
    except subprocess.TimeoutExpired as error:
        raise ErrorEditorVertical("La exportación del clip superó los 15 minutos y fue detenida.") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode(errors="replace")[-1200:]
        raise ErrorEditorVertical("FFmpeg no pudo crear el clip con cámara: " + detalle) from error
    except OSError as error:
        raise ErrorEditorVertical(f"No pude guardar el video compuesto: {error}") from error
