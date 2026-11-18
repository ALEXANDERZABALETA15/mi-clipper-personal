# ---------- IMPORTAR HERRAMIENTAS ----------
import io                      # para leer imágenes desde la memoria
import os                      # para leer la clave guardada en tu computador
import subprocess              # para reconocer los errores de FFmpeg
import time                    # para medir cuánto tarda cada etapa
from datetime import datetime  # para ponerle fecha y hora al nombre del clip guardado
from PIL import Image          # para saber el tamaño real del clip
import streamlit as st         # crea la página web
from yt_dlp.utils import DownloadError   # el error cuando una descarga falla
import clipper                 # descarga, audio, transcripción y cortes
import inteligencia            # la IA que elige los mejores momentos
import titulos                 # el código de los títulos (titulos.py)
import locutor                 # las voces narradoras (locutor.py)

# ---------- CONFIGURACIÓN DE LA PÁGINA ----------
st.set_page_config(page_title="Mi Clipper", layout="wide")
st.title("Mi Clipper personal")

# ---------- MEMORIA DE LA PÁGINA ----------
if "clips" not in st.session_state:
    st.session_state.clips = []    # lista de clips (cada uno guarda su video en memoria)
if "tiempos" not in st.session_state:
    st.session_state.tiempos = {}  # cuánto tardó cada etapa
if "aviso" not in st.session_state:
    st.session_state.aviso = ""    # mensaje si la IA no se pudo usar

# ---------- BARRA LATERAL CON LOS CONTROLES ----------
with st.sidebar:
    st.header("Ajustes")
    link = st.text_input("Link del video")                                  # caja para el link
    archivo = st.file_uploader("...o sube un video de tu computador",       # plan B si el link falla
                               type=["mp4", "mov", "mkv", "webm"])
    modo = st.radio("Modo de selección", ["Inteligente (IA)", "Rápido (volumen)"])
    usa_ia = modo.startswith("Inteligente")
    clave, idioma_gancho, precision = "", "Español", "Equilibrada (base)"   # valores por defecto
    if usa_ia:
        clave = st.text_input("Clave de Gemini (gratis)",                   # tu clave de aistudio.google.com/apikey
                              value=os.environ.get("GEMINI_API_KEY", ""), type="password")
        if st.button("Probar clave"):                                       # revisa que todo funcione en 2 segundos
            try:
                modelos_prueba = inteligencia.preparar_ia(clave)
                st.success(f"Clave lista. Modelo que usaré: {modelos_prueba[0]}")
            except inteligencia.ErrorIA as e:
                st.error(str(e))
        idioma_gancho = st.selectbox("Idioma de títulos y ganchos",
                                     ["Español", "English", "El mismo del video"])
        precision = st.radio("Precisión de la voz del video", ["Rápida (tiny)", "Equilibrada (base)"], index=1)
    formato = st.radio("Formato", ["9:16", "16:9"], horizontal=True)        # vertical u horizontal
    duracion = st.radio("Duración objetivo (s)", [30, 40, 45], horizontal=True)
    cantidad = st.slider("Cantidad de clips", 3, 8, 5)                      # cuántos clips generar
    calidad = st.radio("Calidad de descarga", ["Rápida (480p)", "Normal (720p)"])
    por_fila = st.slider("Clips por fila", 2, 5, 4)                         # cuántos se ven lado a lado

    st.divider()
    st.subheader("Voz narradora")
    nombre_voz = st.selectbox("Voz", list(locutor.VOCES_BASE))              # voces disponibles
    codigo_voz = locutor.VOCES_BASE[nombre_voz]
    velocidad = st.slider("Velocidad (%)", -20, 30, 0)
    tono = st.slider("Tono (Hz)", -20, 20, 0)
    if st.button("Probar voz"):                                             # una muestra para escuchar
        muestra = ("Hello, this is the voice that will narrate your clips."
                   if codigo_voz.startswith("en-")
                   else "Hola, esta es la voz que va a narrar tus clips.")
        try:
            st.audio(locutor.generar_audio(muestra, codigo_voz, velocidad, tono), format="audio/mp3")
        except locutor.ErrorVoz as e:
            st.error(str(e))

    st.divider()
    generar = st.button("Generar clips", type="primary")                    # botón principal
altura = 480 if calidad.startswith("Rápida") else 720                       # convierte la opción en número

# ---------- GENERAR LOS CLIPS ----------
if generar and not (link or archivo):
    st.warning("Pega un link o sube un video.")

if generar and (link or archivo):
    clipper.DURACION_CLIP = duracion   # le pasamos tu elección a clipper.py
    clipper.NUM_CLIPS = cantidad
    clipper.MODELO_WHISPER = "tiny" if precision.startswith("Rápida") else "base"
    tiempos = {}                       # aquí anotamos los tiempos
    aviso = ""                         # aquí guardamos un aviso si la IA falla
    usa_ia_ahora = usa_ia              # puede cambiar a False si la IA no está disponible
    modelos_ia = []
    try:
        with st.spinner("Trabajando... puede tardar unos minutos"):
            clipper.preparar()                                    # carpeta temporal limpia

            # --- Revisamos la IA ANTES de gastar minutos transcribiendo ---
            if usa_ia:
                try:
                    modelos_ia = inteligencia.preparar_ia(clave)
                except inteligencia.ErrorIA as e:
                    aviso = f"No pude usar la IA ({e}). Usé el modo rápido por volumen."
                    usa_ia_ahora = False

            t = time.perf_counter()                               # arranca el cronómetro
            if archivo is not None:                               # si subiste un archivo, usa ese
                video = clipper.guardar_video_subido(archivo.getvalue())
            else:                                                 # si no, descarga del link
                video = clipper.descargar(link, altura)
            tiempos["Descarga"] = time.perf_counter() - t

            t = time.perf_counter()
            audio = clipper.sacar_audio(video)                    # saca el audio
            senal = clipper.cargar_audio(audio)                   # lo carga una sola vez
            tiempos["Audio"] = time.perf_counter() - t

            if usa_ia_ahora:
                # --- MODO INTELIGENTE: transcribe todo y la IA elige ---
                t = time.perf_counter()
                barra = st.progress(0.0, text="Transcribiendo el video completo...")
                def avance(fraccion):                             # se llama cada vez que hay una frase nueva
                    f = min(max(fraccion, 0.0), 1.0)
                    barra.progress(f, text=f"Transcribiendo... {int(f * 100)}%")
                segmentos, idioma_video = clipper.transcribir_todo(senal, avance)
                barra.empty()                                     # quita la barra al terminar
                tiempos["Transcripción"] = time.perf_counter() - t

                t = time.perf_counter()
                try:
                    seleccion = inteligencia.elegir_clips_con_ia(
                        senal, clipper.SR, segmentos, clave, cantidad, duracion,
                        idioma_gancho, idioma_video, modelos_ia)
                except inteligencia.ErrorIA as e:                 # si la IA falla, usamos el volumen
                    aviso = f"No pude usar la IA ({e}). Usé el modo por volumen."
                    candidatos = clipper.encontrar_momentos(senal)
                    seleccion = clipper.elegir_clips_con_segmentos(candidatos, segmentos)
                tiempos["Selección"] = time.perf_counter() - t
            else:
                # --- MODO RÁPIDO: por volumen ---
                t = time.perf_counter()
                candidatos = clipper.encontrar_momentos(senal)    # momentos con más volumen
                tiempos["Análisis"] = time.perf_counter() - t
                t = time.perf_counter()
                seleccion = clipper.elegir_clips_rapido(senal, candidatos)   # transcribe solo alrededor
                tiempos["Transcripción"] = time.perf_counter() - t

            t = time.perf_counter()
            nuevos = []
            for i, c in enumerate(seleccion, start=1):
                ruta = clipper.cortar(video, c["inicio"], c["fin"], i, formato, altura)   # corta cada clip
                nuevos.append({
                    "id": f"{i}_{int(c['inicio'])}",              # identificador único del clip
                    "inicio": c["inicio"],                        # segundo donde empieza
                    "duracion": c["fin"] - c["inicio"],           # cuánto dura
                    "texto": c["texto"],                          # lo que se dice en el clip
                    "puntaje": c.get("puntaje"),                  # puntaje de la IA (si hubo)
                    "tipo": c.get("tipo", ""),                    # tipo de momento
                    "motivo": c.get("motivo", ""),                # por qué lo eligió
                    "titulo": c.get("titulo") or clipper.titulo_provisional(c["texto"]),
                    "gancho": c.get("gancho", ""),                # frase gancho sugerida
                    "datos": ruta.read_bytes(),                   # el video queda en memoria
                    "miniatura": clipper.sacar_miniatura(ruta, i),      # un frame para la vista previa
                    "datos_titulo": None,                         # video con título (si lo aplicas)
                    "datos_voz": None,                            # video con voz nueva (si la aplicas)
                    "aviso_voz": "",                              # aviso al poner la voz
                })
            if usa_ia_ahora:                                      # los mejores primero
                nuevos.sort(key=lambda c: -(c["puntaje"] or 0))
            tiempos["Recorte"] = time.perf_counter() - t

            clipper.limpiar()                                     # borra los archivos temporales
            st.session_state.clips = nuevos                       # guarda los clips
            st.session_state.tiempos = tiempos                    # guarda los tiempos
            st.session_state.aviso = aviso                        # guarda el aviso (si hay)
        if not nuevos:
            st.warning("No encontré momentos para este video. Prueba con otro o con otra duración.")
    except DownloadError as e:                                    # falló la descarga del link
        clipper.limpiar()
        st.error(clipper.explicar_error(e))
    except subprocess.CalledProcessError as e:                    # falló FFmpeg
        clipper.limpiar()
        st.error("FFmpeg no pudo procesar el video. Prueba con otro video o con otra calidad.")
        with st.expander("Detalle técnico"):
            st.code((e.stderr or b"").decode(errors="ignore")[-800:])
    except Exception as e:                                        # cualquier otra cosa
        clipper.limpiar()
        st.error(f"Algo salió mal: {e}")

# ---------- AVISOS Y TIEMPOS ----------
if st.session_state.aviso:
    st.warning(st.session_state.aviso)
if st.session_state.tiempos:
    texto_tiempos = " | ".join(f"{k}: {v:.0f} s" for k, v in st.session_state.tiempos.items())
    st.caption(f"Tiempos → {texto_tiempos}")

# ---------- UNA TARJETA POR CLIP ----------
def mostrar_clip(clip):
    cid = clip["id"]                                              # nombre corto para el identificador
    minuto, segundo = divmod(int(clip["inicio"]), 60)             # pasa segundos a minutos:segundos
    if clip["puntaje"] is not None:                               # si la IA lo puntuó, lo mostramos
        st.markdown(f"**Puntaje {clip['puntaje']}/100** · {clip['tipo']}")
        st.caption(clip["motivo"])
    st.caption(f"Minuto {minuto}:{segundo:02d} · {clip['duracion']:.0f} s")

    # Lo que se ve: con voz nueva > con título > el clip original
    mostrado = clip["datos_voz"] or clip["datos_titulo"] or clip["datos"]
    st.video(mostrado)                                            # reproductor del clip

    col1, col2 = st.columns(2)                                    # Guardar y Descartar juntos
    col1.download_button(                                         # Guardar = descargar a tu PC
        "Guardar",
        data=mostrado,                                            # guarda lo que estás viendo
        file_name=datetime.now().strftime("%Y%m%d_%H%M%S") + f"_clip_{cid}.mp4",
        mime="video/mp4",
        key=f"g_{cid}",
    )
    if col2.button("Descartar", key=f"d_{cid}"):
        st.session_state.clips.remove(clip)                       # lo quita de la lista
        st.rerun()                                                # refresca la página

    with st.expander("Título con gancho"):                        # se abre solo si lo necesitas
        titulo = st.text_input("Título (letras blancas)", value=clip["titulo"], key=f"t_{cid}")
        gancho = st.text_input("Gancho (resaltado)",              # el gancho viene sugerido por la IA
                               value=clip["gancho"] or "Nadie vio venir esto", key=f"h_{cid}")
        plantilla = st.selectbox("Plantilla", list(titulos.PLANTILLAS), key=f"p_{cid}")
        lugar = st.selectbox("Posición", list(titulos.POSICIONES), key=f"l_{cid}")

        foto = Image.open(io.BytesIO(clip["miniatura"]))          # tamaño real del clip
        banner = titulos.crear_banner(titulo, gancho, plantilla, foto.width, foto.height)
        st.image(titulos.vista_previa(clip["miniatura"], banner, lugar),
                 caption="Vista previa")                          # cómo se vería

        if st.button("Aplicar al video", key=f"a_{cid}"):
            if banner is None:
                st.warning("Escribe un título o un gancho.")
            else:
                with st.spinner("Pegando el título..."):
                    clip["datos_titulo"] = titulos.aplicar_al_video(
                        clip["datos"], banner, foto.width, foto.height, lugar)
                    clip["datos_voz"] = None                      # la voz hay que volver a aplicarla
                st.rerun()                                        # refresca para ver el resultado
        if clip["datos_titulo"] and st.button("Quitar título", key=f"q_{cid}"):
            clip["datos_titulo"] = None                           # vuelve al clip limpio
            clip["datos_voz"] = None
            st.rerun()

    with st.expander("Voz narradora"):                            # cambia la voz del clip
        st.caption("Aplica primero el título y al final la voz.")
        texto_voz = st.text_area("Texto a narrar", value=clip["texto"], height=150, key=f"v_{cid}")
        fondo = st.checkbox("Dejar el audio original muy bajito de fondo", key=f"f_{cid}")
        if st.button("Aplicar voz", key=f"av_{cid}"):
            try:
                with st.spinner("Generando la voz..."):
                    base = clip["datos_titulo"] or clip["datos"]  # sobre el clip (con título si lo tiene)
                    audio_voz = locutor.generar_audio(texto_voz, codigo_voz, velocidad, tono)
                    clip["datos_voz"], clip["aviso_voz"] = locutor.poner_voz(base, audio_voz, fondo)
                st.rerun()
            except locutor.ErrorVoz as e:
                st.error(str(e))
            except subprocess.CalledProcessError:
                st.error("FFmpeg no pudo poner la voz en este clip.")
        if clip["aviso_voz"]:
            st.warning(clip["aviso_voz"])
        if clip["datos_voz"] and st.button("Quitar voz", key=f"qv_{cid}"):
            clip["datos_voz"] = None                              # vuelve al audio original
            clip["aviso_voz"] = ""
            st.rerun()

    with st.expander("Lo que se dice"):
        st.write(clip["texto"] or "(sin voz en este clip)")

# ---------- ACOMODAR LOS CLIPS EN CUADRÍCULA ----------
clips = st.session_state.clips
for i in range(0, len(clips), por_fila):                          # una vuelta por cada fila
    columnas = st.columns(por_fila)                               # crea las columnas de la fila
    for columna, clip in zip(columnas, clips[i:i + por_fila]):    # un clip en cada columna
        with columna:
            mostrar_clip(clip)