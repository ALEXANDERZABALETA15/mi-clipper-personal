# ---------- IMPORTAR HERRAMIENTAS ----------
import json                    # para leer la respuesta de la IA
import re                      # para buscar el número de versión en el nombre del modelo
import numpy as np             # para cálculos con listas de números
import librosa                 # para medir el volumen del audio
import requests                # para hablar con Gemini por internet (ya la tienes instalada)

# ---------- CONFIGURACIÓN ----------
URL_BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_CARACTERES = 600_000       # límite de texto que le mandamos a la IA de una sola vez
# Palabras que indican que un modelo NO sirve para leer texto y elegir clips
EXCLUIR = ("image", "tts", "live", "audio", "embedding", "robotics",
           "computer", "imagen", "veo", "aqa", "learnlm")

class ErrorIA(Exception):
    """Error propio: la IA no se pudo usar (el programa entonces usa el modo por volumen)."""
    pass

# ---------- PREGUNTARLE A GOOGLE QUÉ MODELOS TIENE TU CLAVE ----------
def listar_modelos(clave):
    nombres, token = [], None
    for _ in range(5):                                   # hasta 5 páginas de resultados
        params = {"pageSize": 200}
        if token:
            params["pageToken"] = token
        try:
            r = requests.get(f"{URL_BASE}/models", headers={"x-goog-api-key": clave},
                             params=params, timeout=30)
        except requests.RequestException as e:
            raise ErrorIA(f"no hay conexión con Gemini ({str(e)[:80]})")
        if r.status_code in (400, 401, 403):
            raise ErrorIA("la clave de Gemini no es válida o no tiene permiso")
        if r.status_code != 200:
            raise ErrorIA(f"no pude consultar los modelos (error {r.status_code})")
        datos = r.json()
        for m in datos.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                nombres.append(m["name"].replace("models/", ""))
        token = datos.get("nextPageToken")
        if not token:
            break
    return nombres

# ---------- ELEGIR LOS MEJORES MODELOS "FLASH" ----------
def elegir_modelos(nombres):
    candidatos = []
    for n in nombres:
        b = n.lower()
        if "flash" not in b or any(x in b for x in EXCLUIR):
            continue                                     # solo modelos flash que lean texto
        v = re.search(r"gemini-(\d+(?:\.\d+)?)", b)
        version = float(v.group(1)) if v else 0.0
        # Orden: primero los estables, luego los que no son "lite", luego la versión más alta
        candidatos.append((("preview" in b or "exp" in b), ("lite" in b), -version, n))
    candidatos.sort()
    return [c[3] for c in candidatos][:5]                # nos quedamos con los 5 mejores

def preparar_ia(clave):
    if not clave:
        raise ErrorIA("falta la clave de Gemini")
    modelos = elegir_modelos(listar_modelos(clave))
    if not modelos:
        raise ErrorIA("tu clave no tiene modelos Flash disponibles")
    return modelos

# ---------- VOLUMEN DE CADA SEGUNDO, DE 0 A 9 ----------
def volumen_por_segundo(senal, sr):
    rms = librosa.feature.rms(y=senal, frame_length=sr, hop_length=sr)[0]   # volumen por segundo
    if len(rms) == 0:
        return np.zeros(1)
    tope = np.percentile(rms, 95)                        # el volumen "fuerte" de este video
    if tope <= 0:
        return np.zeros(len(rms))
    return np.clip(rms / tope, 0, 1) * 9                 # lo pasa a una escala de 0 a 9

# ---------- ARMAR EL TEXTO QUE LEE LA IA ----------
def armar_transcripcion(segmentos, vol):
    lineas = []
    for i, s in enumerate(segmentos):
        trozo = vol[int(s["inicio"]): int(s["fin"]) + 1]             # volumen durante esa frase
        v = int(round(trozo.mean())) if len(trozo) else 0
        lineas.append(f"{i} | {s['inicio']:.0f}-{s['fin']:.0f}s | vol {v} | {s['texto']}")
    return "\n".join(lineas)

# ---------- LAS INSTRUCCIONES PARA LA IA ----------
def crear_prompt(transcripcion, cantidad, duracion, idioma, idioma_video):
    if idioma == "Español":
        idioma_texto = "español"
    elif idioma == "English":
        idioma_texto = "inglés"
    else:
        idioma_texto = f"el mismo idioma del video (código {idioma_video})"
    return f"""Eres un editor experto en videos cortos (YouTube Shorts, Reels, TikTok).
Te paso la transcripción de un video. Cada línea tiene este formato:
número | segundos de inicio-fin | vol (volumen de la voz, de 0 a 9) | texto

Tu trabajo: elegir los {cantidad} mejores momentos para convertirlos en clips de unos {duracion} segundos (nunca menos de 30 ni más de 45).

Un buen clip:
- Se entiende solo, sin haber visto el resto del video (tiene el contexto necesario).
- Empieza al comienzo de una frase o idea y termina cuando la idea se cierra. Nunca cortado a mitad de frase.
- Tiene algo que atrapa en los primeros 3 segundos, o un remate al final: dato sorprendente, emoción fuerte, conflicto, humor, historia con final, consejo útil, revelación o frase memorable.
- Un volumen alto (7 a 9) suele indicar emoción, pero no es el único criterio.

Evita: saludos, presentaciones, intros, publicidad o patrocinadores, despedidas, charla vacía, partes repetidas y momentos que dependen de algo que se dijo antes.
Los clips no pueden cruzarse entre sí.

Para cada clip devuelve:
- desde: número de la primera línea del clip
- hasta: número de la última línea del clip
- puntaje: de 0 a 100, qué tan bueno es como short
- tipo: una palabra (humor, emoción, dato, historia, consejo, acción, polémica, otro)
- motivo: una frase corta que explique por qué sirve
- titulo: título descriptivo, máximo 60 caracteres
- gancho: frase corta y fuerte, máximo 8 palabras, que haga querer seguir viendo. Usa uno de estos patrones: una pregunta que dé curiosidad, un dato inesperado, una promesa directa de lo que se verá, o hablarle directo a un tipo de persona.

El título y el gancho deben ser verdad según lo que pasa en el clip: no exageres ni inventes.
Escribe el título y el gancho en: {idioma_texto}.

Responde SOLO con JSON, con esta forma exacta:
{{"clips": [{{"desde": 0, "hasta": 0, "puntaje": 0, "tipo": "", "motivo": "", "titulo": "", "gancho": ""}}]}}

Transcripción:
{transcripcion}
"""

# ---------- PREGUNTARLE A GEMINI (prueba los modelos de uno en uno) ----------
def pedir_a_gemini(prompt, clave, modelos):
    ultimo = "sin respuesta"
    llego_limite = False
    for modelo in modelos:
        try:
            r = requests.post(
                f"{URL_BASE}/models/{modelo}:generateContent",
                headers={"x-goog-api-key": clave, "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
                },
                timeout=180,
            )
        except requests.RequestException as e:
            raise ErrorIA(f"no hay conexión con Gemini ({str(e)[:80]})")
        if r.status_code == 429:                         # límite de este modelo: prueba el siguiente
            llego_limite = True
            ultimo = f"{modelo}: límite alcanzado"
            continue
        if r.status_code != 200:
            try:
                mensaje = r.json().get("error", {}).get("message", "")
            except ValueError:
                mensaje = ""
            if "api key" in mensaje.lower():
                raise ErrorIA("la clave de Gemini no es válida")
            ultimo = f"{modelo}: error {r.status_code}"
            continue
        try:
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(texto)                     # convierte el texto JSON en datos
        except (KeyError, IndexError, ValueError, TypeError):
            ultimo = f"{modelo}: respuesta en formato raro"
            continue
    if llego_limite:
        raise ErrorIA("llegaste al límite gratis de Gemini; espera unos minutos o hasta mañana")
    raise ErrorIA(f"ningún modelo respondió ({ultimo}); probé: {', '.join(modelos)}")

# ---------- AJUSTAR EL CLIP A 30-45 SEGUNDOS SIN PARTIR FRASES ----------
def ajustar_rango(desde, hasta, segmentos, total):
    n = len(segmentos)
    inicio = segmentos[desde]["inicio"]
    while segmentos[hasta]["fin"] - inicio < 30 and hasta < n - 1:    # muy corto: suma frases
        hasta += 1
    while segmentos[hasta]["fin"] - inicio > 45 and hasta > desde:    # muy largo: quita frases
        hasta -= 1
    fin = segmentos[hasta]["fin"]
    if fin - inicio > 45:                                # una sola frase larguísima: corta en 45
        fin = inicio + 45
    if fin - inicio < 30:                                # si aun así quedó corto: llega a 30
        fin = inicio + 30
    inicio = max(0, inicio - 0.4)                        # un respiro antes de la primera palabra
    fin = min(total, fin + 0.4)                          # y otro después de la última
    return inicio, fin, hasta

def _puntaje(p):
    try:
        return float(p.get("puntaje", 0) or 0)
    except (ValueError, TypeError, AttributeError):
        return 0.0

# ---------- FUNCIÓN PRINCIPAL: LA IA ELIGE LOS CLIPS ----------
def elegir_clips_con_ia(senal, sr, segmentos, clave, cantidad, duracion, idioma, idioma_video, modelos):
    if not segmentos:
        raise ErrorIA("no se detectó voz en el video")
    vol = volumen_por_segundo(senal, sr)
    transcripcion = armar_transcripcion(segmentos, vol)
    if len(transcripcion) > MAX_CARACTERES:
        raise ErrorIA("el video es demasiado largo para analizarlo de una sola vez")
    datos = pedir_a_gemini(crear_prompt(transcripcion, cantidad, duracion, idioma, idioma_video),
                           clave, modelos)
    propuestas = datos.get("clips", []) if isinstance(datos, dict) else datos
    if not isinstance(propuestas, list):
        raise ErrorIA("la IA no devolvió una lista de clips")

    total = len(senal) / sr                              # duración del video en segundos
    n = len(segmentos)
    elegidos = []
    for p in sorted(propuestas, key=_puntaje, reverse=True):         # del mejor puntaje al peor
        try:
            desde = max(0, min(int(p["desde"]), n - 1))
            hasta = max(desde, min(int(p["hasta"]), n - 1))
        except (KeyError, ValueError, TypeError):
            continue                                     # propuesta mal formada: la saltamos
        inicio, fin, hasta = ajustar_rango(desde, hasta, segmentos, total)
        if any(not (fin <= e["inicio"] or inicio >= e["fin"]) for e in elegidos):
            continue                                     # se cruza con otro clip: la saltamos
        elegidos.append({
            "inicio": inicio,
            "fin": fin,
            "texto": " ".join(s["texto"] for s in segmentos[desde:hasta + 1]),
            "puntaje": int(_puntaje(p)),
            "tipo": str(p.get("tipo", "")).strip(),
            "motivo": str(p.get("motivo", "")).strip(),
            "titulo": str(p.get("titulo", "")).strip()[:70],
            "gancho": str(p.get("gancho", "")).strip()[:70],
        })
        if len(elegidos) == cantidad:
            break
    if not elegidos:
        raise ErrorIA("la IA no devolvió clips válidos")
    return elegidos