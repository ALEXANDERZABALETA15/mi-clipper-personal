# ---------- IMPORTAR HERRAMIENTAS ----------
import asyncio                 # para poder usar edge-tts (trabaja de forma asíncrona)
import subprocess              # para ejecutar FFmpeg y ffprobe
import tempfile                # para archivos temporales que se borran solos
from pathlib import Path       # para manejar rutas
import edge_tts                # las voces gratis de Microsoft Edge

# ---------- VOCES DISPONIBLES (puedes agregar más) ----------
# Para ver todas las que existen: en la terminal, "edge-tts --list-voices"
VOCES_BASE = {
    "Gonzalo (Colombia, hombre)": "es-CO-GonzaloNeural",
    "Salome (Colombia, mujer)": "es-CO-SalomeNeural",
    "Jorge (México, hombre)": "es-MX-JorgeNeural",
    "Dalia (México, mujer)": "es-MX-DaliaNeural",
    "Alvaro (España, hombre)": "es-ES-AlvaroNeural",
    "Elvira (España, mujer)": "es-ES-ElviraNeural",
    "Tomas (Argentina, hombre)": "es-AR-TomasNeural",
    "Alonso (EE. UU. español, hombre)": "es-US-AlonsoNeural",
    "Guy (inglés EE. UU., hombre)": "en-US-GuyNeural",
    "Andrew (inglés EE. UU., hombre)": "en-US-AndrewNeural",
    "Aria (inglés EE. UU., mujer)": "en-US-AriaNeural",
}

class ErrorVoz(Exception):
    """Error propio: no se pudo generar o poner la voz."""
    pass

# ---------- GENERAR EL AUDIO DE LA VOZ ----------
async def _sintetizar(texto, voz, ruta, velocidad, tono):
    comunicador = edge_tts.Communicate(texto, voz, rate=velocidad, pitch=tono)
    await comunicador.save(str(ruta))                    # guarda el audio en un archivo mp3

def generar_audio(texto, voz, velocidad=0, tono=0):
    if not texto.strip():
        raise ErrorVoz("No hay texto para narrar.")
    rate = f"{velocidad:+d}%"                            # por ejemplo "+10%" o "-5%"
    pitch = f"{tono:+d}Hz"                               # por ejemplo "-5Hz"
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "voz.mp3"
            asyncio.run(_sintetizar(texto, voz, ruta, rate, pitch))
            return ruta.read_bytes()                     # devuelve el audio como bytes
    except Exception as e:
        raise ErrorVoz(f"No pude generar la voz (¿hay internet?). Detalle: {str(e)[:100]}")

# ---------- CUÁNTO DURA UN ARCHIVO (con ffprobe, que viene con FFmpeg) ----------
def duracion(ruta):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(ruta)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

# ---------- PONER LA VOZ NUEVA EN EL CLIP ----------
def poner_voz(datos_video, datos_voz, mantener_fondo=False):
    aviso = ""
    with tempfile.TemporaryDirectory() as carpeta:
        c = Path(carpeta)
        (c / "video.mp4").write_bytes(datos_video)
        (c / "voz.mp3").write_bytes(datos_voz)
        dur_video = duracion(c / "video.mp4")
        dur_voz = duracion(c / "voz.mp3")
        factor = dur_voz / dur_video if dur_video > 0 else 1.0
        filtro_voz = "apad"                              # si la voz es más corta, rellena con silencio
        if factor > 1.0:                                 # si es más larga, la acelera para que quepa
            acelerar = min(factor, 1.6)                  # pero nunca más de 1.6 veces
            filtro_voz = f"atempo={acelerar:.3f},apad"
            if factor > 1.6:
                aviso = "La voz es más larga que el clip y se recortó el final. Acorta el texto."
        if mantener_fondo:                               # audio original bajito + voz nueva
            filtro = (f"[0:a]volume=0.15[o];[1:a]{filtro_voz}[v];"
                      f"[o][v]amix=inputs=2:duration=first:normalize=0[a]")
        else:                                            # solo la voz nueva
            filtro = f"[1:a]{filtro_voz}[a]"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(c / "video.mp4"),                  # el clip
            "-i", str(c / "voz.mp3"),                    # la voz nueva
            "-filter_complex", filtro,
            "-map", "0:v", "-map", "[a]",                # video original + audio nuevo
            "-c:v", "copy",                              # el video no se vuelve a comprimir (rápido)
            "-c:a", "aac",
            "-t", f"{dur_video:.2f}",                    # que dure lo mismo que el clip
            "-movflags", "+faststart",
            str(c / "salida.mp4"),
        ], check=True, capture_output=True)
        return (c / "salida.mp4").read_bytes(), aviso