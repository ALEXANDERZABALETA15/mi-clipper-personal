# ---------- IMPORTAR HERRAMIENTAS ----------
import shutil                # para borrar carpetas temporales
import subprocess            # para ejecutar FFmpeg desde Python
import tempfile              # para saber dónde está la carpeta temporal de Windows
from pathlib import Path     # para manejar carpetas y archivos fácil
import numpy as np           # para hacer cálculos con listas de números
import librosa               # para analizar el audio (volumen)
import yt_dlp                # para descargar el video del link
from faster_whisper import WhisperModel   # para transcribir el audio

# ---------- CONFIGURACIÓN ----------
DURACION_CLIP = 40           # duración objetivo de cada clip (la cambia la página)
NUM_CLIPS = 5                # cuántos clips genera (la cambia la página)
MODELO_WHISPER = "base"      # "tiny" = más rápido, "base" = equilibrado (la cambia la página)
SR = 16000                   # muestras de audio por segundo
IGNORAR_FINAL = 20           # segundos del final que se ignoran en el modo por volumen

# Para videos con restricción de edad: "firefox" (con YouTube abierto en Firefox).
# No uses "chrome": en Windows da error de permisos.
COOKIES_NAVEGADOR = "firefox"
# Opcional: un archivo cookies.txt en la carpeta del proyecto (si existe, se usa primero)
COOKIES_ARCHIVO = Path(__file__).parent / "cookies.txt"

# Carpeta de trabajo TEMPORAL (dentro de la carpeta temp de Windows, no en tu proyecto)
CARPETA = Path(tempfile.gettempdir()) / "clipper_trabajo"

# ---------- PREPARAR / LIMPIAR LA CARPETA TEMPORAL ----------
def preparar():
    shutil.rmtree(CARPETA, ignore_errors=True)   # borra restos de la vez anterior
    CARPETA.mkdir(parents=True, exist_ok=True)   # la crea limpia

def limpiar():
    shutil.rmtree(CARPETA, ignore_errors=True)   # borra todo lo temporal

# ---------- PASO 1: DESCARGAR EL VIDEO ----------
def descargar(link, altura=480):
    h = altura
    opciones = {
        # Prefiere video H.264 (más liviano de cortar). Si no hay, usa lo mejor disponible.
        "format": (f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/"
                   f"bv*[height<={h}][vcodec^=avc1]+ba/"
                   f"bv*[height<={h}]+ba/b[height<={h}]"),
        "outtmpl": str(CARPETA / "video.%(ext)s"),   # nombre del archivo guardado
        "merge_output_format": "mp4",                # lo guarda como mp4
        "noplaylist": True,                          # si el link trae una lista, baja solo ese video
        "quiet": True,                               # menos texto en la terminal
        "no_color": True,                            # sin códigos raros en los mensajes
    }
    if COOKIES_ARCHIVO.exists():                     # si hay un archivo cookies.txt, lo usa
        opciones["cookiefile"] = str(COOKIES_ARCHIVO)
    elif COOKIES_NAVEGADOR:                          # si no, usa las cookies del navegador elegido
        opciones["cookiesfrombrowser"] = (COOKIES_NAVEGADOR,)
    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([link])                         # descarga el video
    return CARPETA / "video.mp4"                     # devuelve la ruta del video

# ---------- USAR UN VIDEO SUBIDO DESDE TU COMPUTADOR ----------
def guardar_video_subido(datos):
    destino = CARPETA / "video.mp4"      # lo guarda con el nombre que espera el resto del programa
    destino.write_bytes(datos)
    return destino

# ---------- PASO 2: SACAR EL AUDIO ----------
def sacar_audio(video):
    audio = CARPETA / "audio.wav"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video),  # -y sobrescribe, -i es el video de entrada
        "-vn",                             # -vn = sin video, solo audio
        "-ac", "1",                        # un solo canal (mono)
        "-ar", str(SR),                    # calidad baja, suficiente y más rápido
        str(audio),
    ], check=True, capture_output=True)    # capture_output = no llena la terminal de texto
    return audio

def cargar_audio(audio):
    senal, _ = librosa.load(str(audio), sr=SR, mono=True)   # el audio como lista de números
    return senal

# ---------- MODELO DE VOZ (se carga una sola vez) ----------
_modelo = None
_nombre_modelo = None

def obtener_modelo():
    global _modelo, _nombre_modelo
    if _modelo is None or _nombre_modelo != MODELO_WHISPER:   # carga si no existe o si cambiaste de modelo
        _modelo = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
        _nombre_modelo = MODELO_WHISPER
    return _modelo

# ---------- TRANSCRIBIR EL VIDEO COMPLETO (modo inteligente) ----------
def transcribir_todo(senal, progreso=None):
    modelo = obtener_modelo()
    total = len(senal) / SR                              # duración del audio en segundos
    # beam_size=1 es más rápido; vad_filter=True salta los silencios
    partes, info = modelo.transcribe(senal, vad_filter=True, beam_size=1)
    segmentos = []
    for p in partes:                                     # aquí es donde realmente trabaja
        segmentos.append({"inicio": p.start, "fin": p.end, "texto": p.text.strip()})
        if progreso and total > 0:
            progreso(p.end / total)                      # avisa a la página cuánto va
    return segmentos, info.language                      # frases con tiempos + idioma detectado

# ---------- TRANSCRIBIR SOLO UN PEDACITO (modo rápido) ----------
def transcribir_ventana(senal, desde, hasta):
    modelo = obtener_modelo()
    desde = max(0, desde)
    trozo = senal[int(desde * SR): int(hasta * SR)]      # corta solo ese pedazo del audio
    if len(trozo) < SR:                                  # menos de 1 segundo: no hay nada
        return []
    partes, _ = modelo.transcribe(trozo, vad_filter=True, beam_size=1)
    # Los tiempos salen desde 0 en el trozo; le sumamos "desde" para que sean los del video
    return [
        {"inicio": p.start + desde, "fin": p.end + desde, "texto": p.text.strip()}
        for p in partes
    ]

# ---------- BUSCAR MOMENTOS CON MÁS VOLUMEN ----------
def encontrar_momentos(senal):
    # Mide el volumen de cada segundo (una ventana de SR muestras = 1 segundo)
    volumen = librosa.feature.rms(y=senal, frame_length=SR, hop_length=SR)[0]
    if len(volumen) < DURACION_CLIP:                     # el video es más corto que un clip
        return [0]                                       # entonces usamos desde el inicio
    # Suma el volumen de cada bloque de DURACION_CLIP segundos seguidos
    ventana = np.ones(DURACION_CLIP)
    puntaje = np.convolve(volumen, ventana, mode="valid")
    if len(puntaje) > 2 * IGNORAR_FINAL:                 # en videos normales...
        puntaje[-IGNORAR_FINAL:] = 0                     # ...ignora el final (logos, créditos)
    orden = np.argsort(puntaje)[::-1]                    # de mayor a menor puntaje
    candidatos = []
    for inicio in orden:
        # Solo acepta el momento si no se cruza con otro ya elegido
        if all(abs(inicio - e) >= DURACION_CLIP for e in candidatos):
            candidatos.append(int(inicio))
        if len(candidatos) == NUM_CLIPS * 3:             # guardamos de sobra por si algunos se cruzan
            break
    return candidatos                                    # de mejor a peor puntaje

# ---------- AJUSTAR UN MOMENTO A FRASES COMPLETAS ----------
def limites_duracion(duracion=None):
    """Devuelve la duración mínima y máxima aceptable para el modo elegido."""
    objetivo = int(duracion if duracion is not None else DURACION_CLIP)
    if objetivo <= 45:                         # conserva el comportamiento de Shorts
        return max(30, objetivo - 5), min(45, objetivo + 5)
    tolerancia = max(12, int(round(objetivo * 0.05)))  # 5 % para segmentos largos
    return max(60, objetivo - tolerancia), objetivo + tolerancia


# ---------- AJUSTAR UN MOMENTO A FRASES COMPLETAS ----------
def ajustar_a_frases(inicio, segmentos):
    nuevo_inicio = inicio
    for s in segmentos:
        if s["inicio"] <= inicio < s["fin"]:
            nuevo_inicio = s["inicio"]
            break
        if s["inicio"] > inicio:
            if s["inicio"] - inicio <= 5:
                nuevo_inicio = s["inicio"]
            break

    minimo, maximo = limites_duracion()
    finales = [s["fin"] for s in segmentos
               if nuevo_inicio + minimo <= s["fin"] <= nuevo_inicio + maximo]
    if finales:
        fin = min(finales, key=lambda f: abs(f - (nuevo_inicio + DURACION_CLIP)))
    else:
        fin = nuevo_inicio + DURACION_CLIP

    if segmentos:
        fin = min(fin, segmentos[-1]["fin"])
    return nuevo_inicio, fin

def texto_del_clip(segmentos, inicio, fin):
    partes = [s["texto"] for s in segmentos if inicio - 1 <= s["inicio"] < fin]
    return " ".join(partes)                              # todo lo que se dice en el clip

# ---------- MODO RÁPIDO: elige por volumen y transcribe solo alrededor ----------
def elegir_clips_rapido(senal, candidatos):
    elegidos = []
    total = len(senal) / SR
    margen = min(60, max(15, int(DURACION_CLIP * 0.08)))
    for inicio in candidatos:
        desde = max(0, inicio - margen)
        hasta = min(total, inicio + DURACION_CLIP + margen)
        segmentos = transcribir_ventana(senal, desde, hasta)
        ini, fin = ajustar_a_frases(inicio, segmentos)
        if fin - ini < limites_duracion()[0]:
            continue
        if all(fin <= e["inicio"] or ini >= e["fin"] for e in elegidos):
            elegidos.append({"inicio": ini, "fin": fin, "texto": texto_del_clip(segmentos, ini, fin)})
        if len(elegidos) == NUM_CLIPS:
            break
    return sorted(elegidos, key=lambda e: e["inicio"])

# ---------- RESPALDO: por volumen, pero con la transcripción completa ya hecha ----------
def elegir_clips_con_segmentos(candidatos, segmentos):
    elegidos = []
    for inicio in candidatos:
        ini, fin = ajustar_a_frases(inicio, segmentos)
        if all(fin <= e["inicio"] or ini >= e["fin"] for e in elegidos):
            elegidos.append({"inicio": ini, "fin": fin, "texto": texto_del_clip(segmentos, ini, fin)})
        if len(elegidos) == NUM_CLIPS:
            break
    return sorted(elegidos, key=lambda e: e["inicio"])

def titulo_provisional(texto):
    primera = texto.split(".")[0].strip()                # la primera frase
    if len(primera) > 60:
        primera = primera[:60] + "..."                   # si es muy larga, la recorta
    return primera or "Clip sin título"                  # si no hay voz, un nombre por defecto

# ---------- FILTRO DE FORMATO ----------
def filtro_de_formato(formato, altura):
    if formato == "9:16":                                # vertical: recorta el centro
        ancho = 540 if altura <= 480 else 720
        alto = ancho * 16 // 9                           # 540 -> 960, 720 -> 1280
        return f"crop=trunc(ih*9/16/2)*2:ih,scale={ancho}:{alto},setsar=1"
    ancho = 854 if altura <= 480 else 1280               # 16:9 horizontal
    return f"scale={ancho}:-2"

# ---------- CORTAR UN CLIP ----------
def cortar(video, inicio, fin, numero, formato="9:16", altura=480):
    salida = CARPETA / f"clip_{numero}.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", f"{inicio:.2f}",            # desde qué segundo empieza
        "-i", str(video),
        "-t", f"{fin - inicio:.2f}",       # cuántos segundos dura
        "-vf", filtro_de_formato(formato, altura),   # aplica el formato elegido
        "-c:v", "libx264",                 # compresor de video compatible con todo
        "-preset", "veryfast",             # rápido
        "-crf", "23",                      # calidad
        "-pix_fmt", "yuv420p",             # para que lo abran todos los celulares
        "-c:a", "aac",                     # compresor de audio
        "-movflags", "+faststart",         # el clip empieza a verse más rápido
        str(salida),
    ], check=True, capture_output=True)
    return salida

# ---------- MINIATURA DEL CLIP (para la vista previa del título) ----------
def sacar_miniatura(ruta, numero):
    salida = CARPETA / f"mini_{numero}.jpg"
    subprocess.run([
        "ffmpeg", "-y",
        "-ss", "1",                 # toma un frame del segundo 1
        "-i", str(ruta),
        "-frames:v", "1",           # una sola imagen
        "-q:v", "3",                # buena calidad
        str(salida),
    ], check=True, capture_output=True)
    return salida.read_bytes()      # devuelve la imagen como bytes

# ---------- EXPLICAR LOS ERRORES DE DESCARGA EN ESPAÑOL ----------
def explicar_error(error):
    texto = str(error).lower()
    if "confirm your age" in texto or "inappropriate" in texto or "age-restricted" in texto:
        return ("Este video tiene restricción de edad. Pon COOKIES_NAVEGADOR = \"firefox\" en "
                "clipper.py (con YouTube abierto en Firefox) o sube el archivo del video.")
    if "not a bot" in texto:
        return ("YouTube pide confirmar que no eres un robot. Prueba con COOKIES_NAVEGADOR = "
                "\"firefox\" o sube el archivo del video.")
    if "private video" in texto:
        return "Este video es privado. Solo su dueño puede descargarlo."
    if "members-only" in texto or "join this channel" in texto:
        return "Este video es solo para miembros del canal."
    if "country" in texto:
        return "Este video está bloqueado en tu país. Sube el archivo del video."
    if "live event will begin" in texto or "premieres" in texto or "is live" in texto:
        return "Ese live todavía no empieza o sigue en curso. Prueba cuando termine."
    if "unavailable" in texto or "removed" in texto:
        return "Ese video ya no está disponible. Revisa que el link sea correcto."
    return "No pude descargar ese video. Prueba subiendo el archivo. Detalle: " + str(error)[:200]