# ---------- IMPORTAR HERRAMIENTAS ----------
import io                      # para leer imágenes desde la memoria
import os                      # para leer la clave guardada en tu computador
import subprocess              # para reconocer los errores de FFmpeg
import time                    # para medir cuánto tarda cada etapa
import tempfile
import zipfile
from datetime import datetime  # para ponerle fecha y hora al nombre del clip guardado
from PIL import Image          # para saber el tamaño real del clip
import streamlit as st         # crea la página web
from yt_dlp.utils import DownloadError   # el error cuando una descarga falla
import clipper                 # descarga, audio, transcripción y cortes
import inteligencia            # la IA que elige los mejores momentos
import titulos                 # el código de los títulos (titulos.py)
import locutor                 # las voces narradoras (locutor.py)
import subtitulos               # editor local de subtítulos
import editor_vertical           # editor local de composición vertical

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
if "editor_folder" not in st.session_state:
    st.session_state.editor_folder = tempfile.mkdtemp(prefix="mi_clipper_editor_")

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
    if formato == "9:16":
        duracion_opciones = {"30 segundos": 30, "40 segundos": 40, "45 segundos": 45}
        etiqueta_duracion = "Duración objetivo"
        duracion = st.radio(etiqueta_duracion, list(duracion_opciones), horizontal=True, index=1)
        duracion = duracion_opciones[duracion]
        cantidad = st.slider("Cantidad de clips", 3, 8, 5)
    else:
        duracion_opciones = {"3 minutos": 180, "5 minutos": 300, "8 minutos": 480}
        duracion = st.radio("Duración de cada segmento", list(duracion_opciones), horizontal=True, index=1)
        duracion = duracion_opciones[duracion]
        cantidad = st.slider("Cantidad de segmentos", 1, 5, 2)
        st.caption("La IA buscará bloques completos de información, explicaciones e historias. Cada segmento tendrá una duración aproximada de la opción elegida.")
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
                ruta = clipper.cortar(video, c["inicio"], c["fin"], i, formato, altura)
                fuente_editor = None
                if formato == "9:16":
                    nombre_fuente = "fuente_" + str(i) + "_" + str(int(c["inicio"])) + ".mp4"
                    fuente_editor = str(editor_vertical.crear_clip_fuente(
                        video, c["inicio"], c["fin"],
                        os.path.join(st.session_state.editor_folder, nombre_fuente)
                    ))
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
                    "resumen": c.get("resumen", ""),
                    "puntos_clave": c.get("puntos_clave", []),
                    "datos": ruta.read_bytes(),                   # el video queda en memoria
                    "miniatura": clipper.sacar_miniatura(ruta, i),      # un frame para la vista previa
                    "datos_titulo": None,                         # video con título (si lo aplicas)
                    "datos_voz": None,                            # video con voz nueva (si la aplicas)
                    "aviso_voz": "",                              # aviso al poner la voz
                    "datos_subtitulos": None,
                    "srt": None,
                    "formato": formato,
                    "editor_fuente": fuente_editor,
                    "datos_editor": None,
                    "config_editor": None,
                    "incluir_zip": True,
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
    minutos_clip, segundos_clip = divmod(int(clip["duracion"]), 60)
    st.caption(f"Inicio {minuto}:{segundo:02d} · Duración {minutos_clip}:{segundos_clip:02d}")
    if clip.get("resumen"):
        with st.expander("Resumen del segmento", expanded=True):
            st.write(clip["resumen"])
            puntos = clip.get("puntos_clave") or []
            if puntos:
                st.markdown("**Puntos clave**")
                for punto in puntos:
                    if str(punto).strip():
                        st.markdown(f"- {punto}")

    # Lo que se ve: con voz nueva > con título > el clip original
    mostrado = clip.get("datos_subtitulos") or clip["datos_voz"] or clip["datos_titulo"] or clip["datos"]
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
                    clip["datos_subtitulos"] = None
                    clip["datos_voz"] = None                      # la voz hay que volver a aplicarla
                st.rerun()                                        # refresca para ver el resultado
        if clip["datos_titulo"] and st.button("Quitar título", key=f"q_{cid}"):
            clip["datos_titulo"] = None                           # vuelve al clip limpio
            clip["datos_voz"] = None
            st.rerun()


    if clip.get("editor_fuente") and clip.get("formato") == "9:16":
        with st.expander("Editor vertical: gameplay + cámara", expanded=False):
            st.caption("Selecciona las áreas en el video original. La webcam se superpone al gameplay en un Short 9:16.")
            ancho_fuente, alto_fuente = editor_vertical.obtener_dimensiones(clip["editor_fuente"])
            st.caption(f"Video original conservado: {ancho_fuente} × {alto_fuente}. Los recortes se ajustan en porcentajes.")
            anterior = clip.get("config_editor") or {}
            gd = anterior.get("gameplay", {"x": 0, "y": 0, "ancho": 100, "alto": 100})
            st.markdown("**Gameplay (marco rojo)**")
            a, b = st.columns(2)
            gx = a.slider("Gameplay: izquierda (%)", 0, 95, int(gd["x"]), key=f"egx_{cid}")
            gy = b.slider("Gameplay: arriba (%)", 0, 95, int(gd["y"]), key=f"egy_{cid}")
            gw = st.slider("Gameplay: ancho (%)", 5, 100-gx, min(int(gd["ancho"]), 100-gx), key=f"egw_{cid}")
            gh = st.slider("Gameplay: alto (%)", 5, 100-gy, min(int(gd["alto"]), 100-gy), key=f"egh_{cid}")
            cd = anterior.get("camara", {"x": 70, "y": 5, "ancho": 25, "alto": 30})
            st.markdown("**Cámara del streamer (marco verde)**")
            a, b = st.columns(2)
            cx = a.slider("Cámara: izquierda (%)", 0, 95, min(int(cd["x"]),95), key=f"ecx_{cid}")
            cy = b.slider("Cámara: arriba (%)", 0, 95, min(int(cd["y"]),95), key=f"ecy_{cid}")
            cw = st.slider("Cámara: ancho (%)", 5, 100-cx, min(int(cd["ancho"]),100-cx), key=f"ecw_{cid}")
            ch = st.slider("Cámara: alto (%)", 5, 100-cy, min(int(cd["alto"]),100-cy), key=f"ech_{cid}")
            a, b, c = st.columns(3)
            pos = a.selectbox("Posición webcam", ["Superior","Inferior"], index=0 if anterior.get("camara_posicion","Superior")=="Superior" else 1, key=f"epos_{cid}")
            ali = b.selectbox("Alineación", ["Izquierda","Centro","Derecha"], index=["Izquierda","Centro","Derecha"].index(anterior.get("camara_alineacion","Derecha")), key=f"eali_{cid}")
            tam = c.slider("Tamaño webcam (%)", 25, 65, int(anterior.get("camara_ancho",45)), key=f"esize_{cid}")
            config = {"gameplay":{"x":gx,"y":gy,"ancho":gw,"alto":gh},"camara":{"x":cx,"y":cy,"ancho":cw,"alto":ch},"camara_posicion":pos,"camara_alineacion":ali,"camara_ancho":tam}
            try:
                marcada, previa = editor_vertical.crear_previsualizaciones(clip["editor_fuente"], config)
                a, b = st.columns(2)
                a.image(marcada, caption="Rojo: gameplay · Verde: webcam", use_container_width=True)
                b.image(previa, caption="Vista previa 9:16", use_container_width=True)
            except editor_vertical.ErrorEditorVertical as error:
                st.error(str(error))
            if st.button("Generar clip vertical con cámara", type="primary", key=f"erender_{cid}"):
                try:
                    with st.spinner("Componiendo gameplay y webcam..."):
                        clip["datos_editor"] = editor_vertical.aplicar_composicion(clip["editor_fuente"], config, 720)
                        clip["config_editor"] = config
                        clip["datos_subtitulos"] = None
                        clip["datos_voz"] = None
                    st.success("Composición vertical creada.")
                    st.rerun()
                except editor_vertical.ErrorEditorVertical as error:
                    st.error(str(error))
            if clip.get("datos_editor"):
                st.video(clip["datos_editor"])
                st.download_button("Descargar composición 9:16", clip["datos_editor"], file_name=f"clip_vertical_{cid}.mp4", mime="video/mp4", key=f"edl_{cid}")
                if st.button("Quitar composición", key=f"eremove_{cid}"):
                    clip["datos_editor"] = None
                    st.rerun()

    with st.expander("Subtítulos automáticos", expanded=False):
        st.caption("Generados localmente con Faster-Whisper y FFmpeg. Sin APIs de pago.")
        col_s1, col_s2 = st.columns(2)
        tamano_sub = col_s1.selectbox("Tamaño", list(subtitulos.TAMANOS), index=1, key=f"stam_{cid}")
        color_sub = col_s2.selectbox("Color", list(subtitulos.COLORES), key=f"scol_{cid}")
        posicion_sub = st.selectbox("Posición", list(subtitulos.POSICIONES), key=f"spos_{cid}")
        fondo_sub = st.checkbox("Fondo oscuro para mejorar la lectura", value=True, key=f"sfondo_{cid}")
        negrita_sub = st.checkbox("Texto en negrita", value=True, key=f"sbold_{cid}")

        if st.button("Generar / actualizar subtítulos", type="primary", key=f"sg_{cid}"):
            try:
                with st.spinner("Transcribiendo el clip y aplicando subtítulos..."):
                    segmentos_sub = subtitulos.transcribir_video(
                        clip["datos"], "tiny" if precision.startswith("Rápida") else "base"
                    )
                    contenido_srt = subtitulos.crear_srt(segmentos_sub, 0, clip["duracion"])
                    clip["srt"] = contenido_srt
                    video_base_subtitulos = (
                        clip["datos_voz"] or clip["datos_titulo"] or clip["datos"]
                    )
                    clip["datos_subtitulos"] = subtitulos.aplicar_subtitulos(
                        video_base_subtitulos, contenido_srt,
                        formato=clip.get("formato", "9:16"),
                        tamano=tamano_sub, posicion=posicion_sub,
                        color=color_sub, fondo=fondo_sub, negrita=negrita_sub,
                    )
                st.success("Subtítulos aplicados correctamente.")
                st.rerun()
            except subtitulos.ErrorSubtitulos as e:
                st.error(str(e))

        if clip.get("srt"):
            st.download_button(
                "Descargar subtítulos (.srt)",
                data=clip["srt"].encode("utf-8-sig"),
                file_name=f"subtitulos_{cid}.srt",
                mime="application/x-subrip",
                key=f"sd_{cid}",
            )
            if st.button("Quitar subtítulos del video", key=f"sq_{cid}"):
                clip["datos_subtitulos"] = None
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
                    clip["datos_subtitulos"] = None
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
for i in range(0, len(clips), por_fila):
    columnas = st.columns(por_fila)
    for columna, clip in zip(columnas, clips[i:i + por_fila]):
        with columna:
            mostrar_clip(clip)

if clips:
    st.divider()
    st.subheader("Exportación de varios clips")
    st.caption("Marca los clips que quieres reunir en un único ZIP.")
    for clip in clips:
        clip["incluir_zip"] = st.checkbox(f"Incluir clip {clip['id']}", value=clip.get("incluir_zip", True), key=f"zip_{clip['id']}")
    if st.button("Preparar descarga de clips seleccionados", type="primary"):
        elegidos = [clip for clip in clips if clip.get("incluir_zip")]
        if not elegidos:
            st.warning("Selecciona al menos un clip.")
        else:
            paquete = io.BytesIO()
            with zipfile.ZipFile(paquete, "w", compression=zipfile.ZIP_DEFLATED) as archivo_zip:
                for clip in elegidos:
                    contenido = clip.get("datos_subtitulos") or clip.get("datos_editor") or clip.get("datos_voz") or clip.get("datos_titulo") or clip["datos"]
                    archivo_zip.writestr(f"clip_{clip['id']}.mp4", contenido)
            st.download_button(f"Descargar {len(elegidos)} clips en ZIP", data=paquete.getvalue(), file_name=f"mi_clipper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip", mime="application/zip", key="descargar_zip_clips")
