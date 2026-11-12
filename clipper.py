# ---------- IMPORTAR HERRAMIENTAS ----------
import subprocess            # para ejecutar FFmpeg desde Python
import sys                   # para leer el link que escribes en la terminal
from pathlib import Path     # para manejar carpetas y archivos fácil
import numpy as np           # para hacer cálculos con listas de números
import librosa               # para analizar el audio (volumen)
import yt_dlp                # para descargar el video del link

# ---------- CONFIGURACIÓN (puedes cambiar estos números) ----------
DURACION_CLIP = 40           # cada clip dura 40 segundos (usa 30 o 45 si quieres)
NUM_CLIPS = 5                # cuántos clips quieres que genere
CARPETA = Path("salida")     # carpeta donde se guarda todo
CARPETA.mkdir(exist_ok=True) # crea la carpeta si no existe

# ---------- PASO 1: DESCARGAR EL VIDEO ----------
def descargar(link):
    opciones = {
        "format": "bv*[height<=720]+ba/b[height<=720]",  # video hasta 720p (más liviano)
        "outtmpl": str(CARPETA / "video.%(ext)s"),       # nombre del archivo guardado
        "merge_output_format": "mp4",                    # lo guarda como mp4
        "overwrites": True,                              # vuelve a descargar aunque ya exista un video
        "noplaylist": True,                              # si el link trae una lista, baja solo ese video
    }
    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([link])                             # descarga el video
    return CARPETA / "video.mp4"                         # devuelve la ruta del video

# ---------- PASO 2: SACAR EL AUDIO ----------
def sacar_audio(video):
    audio = CARPETA / "audio.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video),  # -y sobrescribe, -i es el video de entrada
        "-vn",                             # -vn = sin video, solo audio
        "-ac", "1",                        # un solo canal (mono)
        "-ar", "16000",                    # calidad baja, suficiente y más rápido
        str(audio),
    ], check=True)
    return audio

# ---------- PASO 3: ENCONTRAR LOS MEJORES MOMENTOS ----------
def encontrar_momentos(audio):
    y, sr = librosa.load(str(audio), sr=16000)           # carga el audio como números
    # Mide el volumen de cada segundo (una ventana de 16000 muestras = 1 segundo)
    volumen = librosa.feature.rms(y=y, frame_length=sr, hop_length=sr)[0]
    # Suma el volumen de cada bloque de DURACION_CLIP segundos seguidos
    ventana = np.ones(DURACION_CLIP)
    puntaje = np.convolve(volumen, ventana, mode="valid")
    # Ordena los inicios de mayor a menor puntaje
    orden = np.argsort(puntaje)[::-1]
    elegidos = []
    for inicio in orden:
        # Solo acepta el momento si no se cruza con otro ya elegido
        if all(abs(inicio - e) >= DURACION_CLIP for e in elegidos):
            elegidos.append(int(inicio))
        if len(elegidos) == NUM_CLIPS:
            break
    return sorted(elegidos)                              # devuelve los segundos de inicio

# ---------- PASO 4: CORTAR LOS CLIPS ----------
def cortar(video, inicio, numero):
    salida = CARPETA / f"clip_{numero}.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(inicio),                # desde qué segundo empieza
        "-i", str(video),
        "-t", str(DURACION_CLIP),          # cuántos segundos dura
        "-c:v", "libx264", "-c:a", "aac",  # formato compatible con todo
        str(salida),
    ], check=True)
    print(f"Clip {numero} listo: {salida}")

# ---------- PROGRAMA PRINCIPAL (solo si lo ejecutas desde la terminal) ----------
if __name__ == "__main__":
    link = sys.argv[1]                     # el link que escribes al ejecutar
    video = descargar(link)
    audio = sacar_audio(video)
    momentos = encontrar_momentos(audio)
    for i, inicio in enumerate(momentos, start=1):
        cortar(video, inicio, i)
    print("Listo. Revisa la carpeta 'salida'.")