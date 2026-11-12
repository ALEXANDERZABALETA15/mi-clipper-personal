# ---------- IMPORTAR HERRAMIENTAS ----------
import shutil                  # para copiar archivos (guardar un clip)
from datetime import datetime  # para ponerle fecha y hora al nombre del clip guardado
from pathlib import Path       # para manejar carpetas
import streamlit as st         # crea la página web
import clipper                 # tu código del archivo clipper.py

# ---------- CARPETA DE CLIPS GUARDADOS ----------
GUARDADOS = Path("guardados")      # aquí van los clips que tú aceptes
GUARDADOS.mkdir(exist_ok=True)     # la crea si no existe

# ---------- TÍTULO DE LA PÁGINA ----------
st.title("Mi Clipper personal")

# ---------- MEMORIA DE LA PÁGINA ----------
# Streamlit "recarga" todo cada vez que tocas un botón.
# session_state guarda la lista de clips para que no se pierda.
if "clips" not in st.session_state:
    st.session_state.clips = []    # empieza vacía

# ---------- CONTROLES ----------
link = st.text_input("Pega el link del video")                         # caja para el link
duracion = st.radio("Duración de cada clip (segundos)", [30, 40, 45])  # opciones de duración
cantidad = st.slider("Cantidad de clips", 3, 8, 5)                     # barra de 3 a 8, empieza en 5

# ---------- BOTÓN PARA GENERAR ----------
if st.button("Generar clips") and link:
    clipper.DURACION_CLIP = duracion   # le pasamos tu elección a clipper.py
    clipper.NUM_CLIPS = cantidad
    with st.spinner("Descargando y analizando el video... puede tardar unos minutos"):
        video = clipper.descargar(link)                  # baja el video
        audio = clipper.sacar_audio(video)               # saca el audio
        momentos = clipper.encontrar_momentos(audio)     # busca los mejores momentos
        rutas = []                                       # lista de clips creados
        for i, inicio in enumerate(momentos, start=1):
            clipper.cortar(video, inicio, i)             # corta cada clip
            rutas.append(clipper.CARPETA / f"clip_{i}.mp4")
        st.session_state.clips = rutas                   # guarda la lista en la memoria

# ---------- MOSTRAR CADA CLIP ----------
for ruta in list(st.session_state.clips):                # recorre los clips de la memoria
    st.video(str(ruta))                                  # reproductor del clip
    col1, col2 = st.columns(2)                           # dos botones lado a lado
    if col1.button("Guardar", key=f"g_{ruta}"):
        nombre = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + ruta.name
        shutil.copy(ruta, GUARDADOS / nombre)            # copia el clip a "guardados"
        st.session_state.clips.remove(ruta)              # lo quita de la lista
        st.rerun()                                       # refresca la página
    if col2.button("Descartar", key=f"d_{ruta}"):
        st.session_state.clips.remove(ruta)              # lo quita de la lista
        st.rerun()                                       # refresca la página