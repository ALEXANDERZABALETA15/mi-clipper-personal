# ---------- IMPORTAR HERRAMIENTAS ----------
import io                          # para trabajar con imágenes en memoria
import subprocess                  # para ejecutar FFmpeg
import tempfile                    # para archivos temporales
from pathlib import Path           # para manejar rutas
from PIL import Image, ImageDraw, ImageFont   # Pillow: dibuja el título como una imagen

# ---------- PLANTILLAS (puedes agregar más) ----------
BLANCO = (255, 255, 255)
PLANTILLAS = {
    # fondo = color de la caja, texto = color del título, resalte = color del gancho
    "Negro + amarillo": {"fondo": (0, 0, 0), "texto": BLANCO, "resalte": (255, 221, 0)},
    "Negro + azul":     {"fondo": (0, 0, 0), "texto": BLANCO, "resalte": (56, 160, 255)},
}

# Posición vertical de la caja (fracción del alto del video)
# "Arriba" y "Abajo" evitan las zonas que tapan los botones de TikTok y Shorts
POSICIONES = {"Arriba": 0.10, "Centro": None, "Abajo": 0.68}

# ---------- FUENTES (letras gruesas, de las que ya trae Windows) ----------
FUENTES = [
    "C:/Windows/Fonts/seguibl.ttf",                        # Segoe UI Black (Windows)
    "C:/Windows/Fonts/arialbd.ttf",                        # Arial Bold (Windows)
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",   # Mac
    "DejaVuSans-Bold.ttf",                                 # Linux
]

def cargar_fuente(tamano):
    for ruta in FUENTES:                                   # prueba una por una
        try:
            return ImageFont.truetype(ruta, tamano)        # si existe, la usa
        except OSError:
            continue                                       # si no existe, prueba la siguiente
    return ImageFont.load_default(tamano)                  # último recurso

# ---------- PARTIR UN TEXTO EN LÍNEAS QUE CAIGAN EN LA CAJA ----------
def partir_lineas(texto, fuente, ancho_max, dibujo):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = (actual + " " + palabra).strip()          # intenta agregar la palabra
        if dibujo.textlength(prueba, font=fuente) <= ancho_max:
            actual = prueba                                # cabe: la agrega
        else:
            if actual:
                lineas.append(actual)                      # no cabe: cierra la línea
            actual = palabra                               # y empieza otra
    if actual:
        lineas.append(actual)
    return lineas

# ---------- CREAR LA CAJA CON EL TÍTULO (una imagen PNG) ----------
def crear_banner(titulo, gancho, plantilla, ancho_video, alto_video):
    titulo = titulo.strip()
    gancho = gancho.strip().upper()               # el gancho va en MAYÚSCULAS para que resalte
    if not titulo and not gancho:
        return None                               # no hay nada que dibujar
    colores = PLANTILLAS[plantilla]
    base = min(ancho_video, alto_video) * 0.055   # tamaño de letra según el video
    f_titulo = cargar_fuente(int(base))           # letra del título
    f_gancho = cargar_fuente(int(base * 1.3))     # el gancho va más grande
    vertical = alto_video > ancho_video
    ancho_caja = int(ancho_video * (0.9 if vertical else 0.7))   # ancho de la caja negra
    margen = int(base * 0.8)                      # espacio entre el borde y el texto
    medidor = ImageDraw.Draw(Image.new("RGB", (1, 1)))           # lienzo de prueba para medir
    bloques = []                                  # cada línea: (texto, letra, color)
    for linea in partir_lineas(titulo, f_titulo, ancho_caja - 2 * margen, medidor):
        bloques.append((linea, f_titulo, colores["texto"]))
    for linea in partir_lineas(gancho, f_gancho, ancho_caja - 2 * margen, medidor):
        bloques.append((linea, f_gancho, colores["resalte"]))
    altos = [int(sum(f.getmetrics()) * 1.05) for _, f, _ in bloques]   # alto de cada línea
    alto_caja = sum(altos) + 2 * margen
    banner = Image.new("RGBA", (ancho_caja, alto_caja), (0, 0, 0, 0))  # imagen transparente
    dibujo = ImageDraw.Draw(banner)
    dibujo.rounded_rectangle(                     # la caja negra con esquinas redondeadas
        [0, 0, ancho_caja - 1, alto_caja - 1],
        radius=int(base * 0.5),
        fill=colores["fondo"] + (255,),
    )
    y = margen
    for (linea, fuente, color), alto in zip(bloques, altos):
        ancho_linea = dibujo.textlength(linea, font=fuente)
        dibujo.text(((ancho_caja - ancho_linea) / 2, y), linea, font=fuente, fill=color)  # centrado
        y += alto
    return banner

# ---------- DÓNDE VA LA CAJA DENTRO DEL VIDEO ----------
def posicion(banner, ancho_video, alto_video, lugar):
    x = (ancho_video - banner.width) // 2                  # centrada de lado a lado
    fraccion = POSICIONES[lugar]
    if fraccion is None:
        y = (alto_video - banner.height) // 2              # centro
    else:
        y = int(alto_video * fraccion)                     # arriba o abajo
    y = min(y, alto_video - banner.height - 10)            # que no se salga del video
    return x, y

# ---------- VISTA PREVIA SOBRE UN FRAME DEL CLIP ----------
def vista_previa(miniatura_bytes, banner, lugar):
    foto = Image.open(io.BytesIO(miniatura_bytes)).convert("RGBA")
    if banner is not None:
        x, y = posicion(banner, foto.width, foto.height, lugar)
        foto.paste(banner, (x, y), banner)                 # pega la caja sobre la foto
    return foto.convert("RGB")

# ---------- PEGAR EL TÍTULO AL VIDEO DE VERDAD ----------
def aplicar_al_video(datos_video, banner, ancho, alto, lugar):
    x, y = posicion(banner, ancho, alto, lugar)
    with tempfile.TemporaryDirectory() as carpeta:         # carpeta temporal que se borra sola
        carpeta = Path(carpeta)
        (carpeta / "entrada.mp4").write_bytes(datos_video) # guarda el clip
        banner.save(carpeta / "banner.png")                # guarda la caja
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(carpeta / "entrada.mp4"),            # video
            "-i", str(carpeta / "banner.png"),             # imagen del título
            "-filter_complex", f"[0:v][1:v]overlay={x}:{y}",   # pega la imagen en x, y
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",                                # el audio no se toca
            "-movflags", "+faststart",
            str(carpeta / "salida.mp4"),
        ], check=True, capture_output=True)
        return (carpeta / "salida.mp4").read_bytes()       # devuelve el video ya con título