"""Generación y renderizado local de subtítulos para Mi Clipper.

No utiliza servicios externos ni dependencias adicionales.
Los archivos SRT y los videos intermedios se crean en carpetas temporales.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class ErrorSubtitulos(RuntimeError):
    """Error controlado al crear o aplicar subtítulos."""


COLORES = {
    "Blanco": "&H00FFFFFF",
    "Amarillo": "&H0000D7FF",
    "Cian": "&H00FFFF00",
    "Verde": "&H0064FF00",
}

TAMANOS = {
    "Pequeño": {"vertical": 38, "horizontal": 30},
    "Mediano": {"vertical": 48, "horizontal": 38},
    "Grande": {"vertical": 58, "horizontal": 46},
}

POSICIONES = {
    "Inferior": 2,
    "Centro": 5,
    "Superior": 8,
}


def _envolver_texto(texto: str, max_caracteres: int) -> list[str]:
    """Divide el texto en líneas sin separar palabras."""
    palabras = texto.split()
    if not palabras:
        return []

    lineas: list[str] = []
    actual = ""

    for palabra in palabras:
        candidato = f"{actual} {palabra}".strip()
        if not actual or len(candidato) <= max_caracteres:
            actual = candidato
        else:
            lineas.append(actual)
            actual = palabra

    if actual:
        lineas.append(actual)

    return lineas


def _timestamp_srt(segundos: float) -> str:
    """Convierte segundos a HH:MM:SS,mmm."""
    milisegundos = max(0, int(round(float(segundos) * 1000)))
    horas, resto = divmod(milisegundos, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    segundos_enteros, ms = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{segundos_enteros:02d},{ms:03d}"


def crear_srt(
    segmentos: list[dict[str, Any]],
    inicio_clip: float,
    fin_clip: float,
    max_caracteres: int = 38,
) -> str:
    """Crea subtítulos SRT usando las marcas de tiempo de Faster-Whisper.

    Los tiempos de entrada son absolutos respecto al video original.
    La salida queda sincronizada desde el segundo cero del clip.
    """
    if fin_clip <= inicio_clip:
        raise ErrorSubtitulos("La duración del clip no es válida.")

    eventos: list[tuple[float, float, str]] = []

    for segmento in sorted(segmentos or [], key=lambda item: float(item.get("inicio", 0))):
        try:
            inicio = max(float(inicio_clip), float(segmento["inicio"]))
            fin = min(float(fin_clip), float(segmento["fin"]))
            texto = re.sub(r"\s+", " ", str(segmento.get("texto", ""))).strip()
        except (KeyError, TypeError, ValueError):
            continue

        if not texto or fin <= inicio:
            continue

        lineas = _envolver_texto(texto, max(12, int(max_caracteres)))
        bloques = [
            "\n".join(lineas[posicion:posicion + 2])
            for posicion in range(0, len(lineas), 2)
        ]
        if not bloques:
            continue

        duracion = fin - inicio
        pesos = [max(1, len(bloque.split())) for bloque in bloques]
        peso_total = sum(pesos)
        acumulado = 0

        for indice, (bloque, peso) in enumerate(zip(bloques, pesos)):
            desde = inicio + duracion * (acumulado / peso_total)
            acumulado += peso
            hasta = fin if indice == len(bloques) - 1 else inicio + duracion * (acumulado / peso_total)

            desde_relativo = max(0.0, desde - float(inicio_clip))
            hasta_relativo = max(desde_relativo + 0.05, hasta - float(inicio_clip))
            hasta_relativo = min(hasta_relativo, float(fin_clip) - float(inicio_clip))
            if hasta_relativo > desde_relativo:
                eventos.append((desde_relativo, hasta_relativo, bloque))

    if not eventos:
        raise ErrorSubtitulos(
            "No hay marcas de tiempo disponibles para crear subtítulos en este clip."
        )

    eventos.sort(key=lambda evento: (evento[0], evento[1]))

    lineas_srt: list[str] = []
    for numero, (inicio, fin, texto) in enumerate(eventos, start=1):
        lineas_srt.extend(
            [
                str(numero),
                f"{_timestamp_srt(inicio)} --> {_timestamp_srt(fin)}",
                texto,
                "",
            ]
        )

    return "\n".join(lineas_srt).strip() + "\n"


def _comprobar_filtro_subtitulos() -> None:
    """Comprueba que FFmpeg tenga el filtro subtitles (compilación con libass)."""
    try:
        resultado = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as error:
        raise ErrorSubtitulos(
            "No encuentro FFmpeg. Comprueba que esté instalado y agregado al PATH de Windows."
        ) from error
    except subprocess.SubprocessError as error:
        raise ErrorSubtitulos("No pude comprobar los filtros disponibles de FFmpeg.") from error

    listado = (resultado.stdout or "") + "\n" + (resultado.stderr or "")
    if not re.search(r"\bsubtitles\s", listado):
        raise ErrorSubtitulos(
            "Tu versión de FFmpeg no incluye el filtro 'subtitles' (libass). "
            "Necesitas una compilación gratuita de FFmpeg que incluya libass. "
            "No hace falta instalar ninguna API ni contratar servicios."
        )


def aplicar_subtitulos(
    datos_video: bytes,
    contenido_srt: str,
    formato: str = "9:16",
    tamano: str = "Mediano",
    posicion: str = "Inferior",
    color: str = "Blanco",
    fondo: bool = True,
    negrita: bool = True,
) -> bytes:
    """Incrusta subtítulos en el MP4 mediante FFmpeg y devuelve el video final.

    Solo se usan archivos temporales. La carpeta se elimina al terminar.
    El audio se copia sin recodificar.
    """
    if not datos_video:
        raise ErrorSubtitulos("El video está vacío.")
    if not contenido_srt.strip():
        raise ErrorSubtitulos("No hay subtítulos para aplicar.")
    if tamano not in TAMANOS or posicion not in POSICIONES or color not in COLORES:
        raise ErrorSubtitulos("Una de las opciones visuales seleccionadas no es válida.")

    _comprobar_filtro_subtitulos()

    es_vertical = formato == "9:16"
    fuente = TAMANOS[tamano]["vertical" if es_vertical else "horizontal"]
    alineacion = POSICIONES[posicion]
    margen = 150 if es_vertical else 58
    if posicion == "Superior":
        margen = 90 if es_vertical else 40

    color_texto = COLORES[color]
    if fondo:
        estilo_borde = 3
        color_fondo = "&H70000000"
        grosor = 10
        sombra = 0
    else:
        estilo_borde = 1
        color_fondo = "&H00000000"
        grosor = 3
        sombra = 1

    force_style = ",".join(
        [
            "FontName=Arial",
            f"FontSize={fuente}",
            f"PrimaryColour={color_texto}",
            "OutlineColour=&H00000000",
            f"BackColour={color_fondo}",
            f"Bold={1 if negrita else 0}",
            f"BorderStyle={estilo_borde}",
            f"Outline={grosor}",
            f"Shadow={sombra}",
            f"Alignment={alineacion}",
            f"MarginV={margen}",
            "MarginL=55",
            "MarginR=55",
        ]
    )

    filtro = f"subtitles=filename=subtitulos.srt:force_style='{force_style}'"

    try:
        with tempfile.TemporaryDirectory(prefix="mi_clipper_subs_") as temporal:
            carpeta = Path(temporal)
            entrada = carpeta / "entrada.mp4"
            archivo_srt = carpeta / "subtitulos.srt"
            salida = carpeta / "salida_subtitulada.mp4"

            entrada.write_bytes(datos_video)
            archivo_srt.write_text(contenido_srt, encoding="utf-8", newline="\n")

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-y",
                        "-i",
                        str(entrada),
                        "-vf",
                        filtro,
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "23",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(salida),
                    ],
                    cwd=str(carpeta),
                    check=True,
                    capture_output=True,
                    timeout=900,
                )
            except subprocess.TimeoutExpired as error:
                raise ErrorSubtitulos(
                    "El proceso de subtítulos superó los 15 minutos y fue detenido."
                ) from error
            except subprocess.CalledProcessError as error:
                detalle = (error.stderr or b"").decode(errors="replace")[-1200:]
                raise ErrorSubtitulos(
                    "FFmpeg no pudo incrustar los subtítulos. Detalle técnico:\n" + detalle
                ) from error

            if not salida.exists() or salida.stat().st_size == 0:
                raise ErrorSubtitulos("FFmpeg terminó, pero no generó el video subtitulado.")

            return salida.read_bytes()

    except OSError as error:
        raise ErrorSubtitulos(f"No pude preparar los archivos temporales: {error}") from error


def transcribir_video(datos_video: bytes, modelo: str = "base") -> list[dict[str, Any]]:
    """Transcribe un clip local para el modo rápido, sin depender de APIs."""
    if not datos_video:
        raise ErrorSubtitulos("El video está vacío.")
    try:
        import clipper
        clipper.MODELO_WHISPER = modelo
        whisper = clipper.obtener_modelo()
        with tempfile.TemporaryDirectory(prefix="mi_clipper_audio_") as temporal:
            carpeta = Path(temporal)
            entrada = carpeta / "clip.mp4"
            audio = carpeta / "audio.wav"
            entrada.write_bytes(datos_video)
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-y", "-i", str(entrada),
                 "-vn", "-ac", "1", "-ar", "16000", str(audio)],
                check=True, capture_output=True, timeout=300,
            )
            partes, _ = whisper.transcribe(str(audio), vad_filter=True, beam_size=1)
            return [
                {"inicio": float(parte.start), "fin": float(parte.end),
                 "texto": parte.text.strip()}
                for parte in partes if parte.text and parte.text.strip()
            ]
    except ErrorSubtitulos:
        raise
    except subprocess.TimeoutExpired as error:
        raise ErrorSubtitulos("La extracción de audio superó los 5 minutos.") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode(errors="replace")[-800:]
        raise ErrorSubtitulos("FFmpeg no pudo extraer el audio: " + detalle) from error
    except Exception as error:
        raise ErrorSubtitulos(f"No pude transcribir este clip: {error}") from error
