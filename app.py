"""
Mi Presión: registro de presión arterial para la familia.
Datos en una hoja de Google (a través de puente.gs) o en un CSV local si no hay enlace.
"""
import datetime as dt
import html
import json
import math
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Mi Presión", page_icon="❤️", layout="centered")


# ---------- Configuración ----------
def secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default


PERSONAS = list(secret("personas", ["Mamá", "Papá"]))
TZ = ZoneInfo(secret("zona_horaria", "Europe/Madrid"))
COLUMNAS = ["id", "persona", "fecha_hora", "sistolica", "diastolica", "pulso", "brazo", "notas"]
CSV_LOCAL = Path("datos_presion.csv")
USA_HOJA = bool(secret("enlace_hoja"))
CLAVE_DATOS = secret("clave_datos", "")

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

# Colores pastel (fondo, texto) por estado
ESTADOS = {
    "Baja": ("#BCD6F4", "#1D4F8A"),
    "Normal": ("#C9E2A8", "#36561A"),
    "Elevada": ("#F6E08A", "#6B5300"),
    "Hipertensión etapa 1": ("#F9CF9F", "#8A4A0E"),
    "Hipertensión etapa 2": ("#F7B6C8", "#8A1C3C"),
    "Crisis hipertensiva": ("#F28B9B", "#6E0F1F"),
}
CORTO = {
    "Hipertensión etapa 1": "Etapa 1",
    "Hipertensión etapa 2": "Etapa 2",
    "Crisis hipertensiva": "Crisis",
}
# ---------- Mascotas (dibujos propios en SVG) ----------
TINTA = "#1E1E1E"


def _mama_svg():
    # Bolita amarilla bailando con los brazos arriba
    return (
        '<svg viewBox="0 0 120 130" xmlns="http://www.w3.org/2000/svg" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        f'<g stroke="{TINTA}" stroke-width="2.6">'
        '<path d="M43 58 C37 42 29 30 19 21"/><path d="M12 22 l6 -1.5 M13 28 l6 -1.5"/>'
        '<path d="M78 58 C84 42 92 30 102 21"/><path d="M103 14 l5 3 M99 12 l4 4"/>'
        '<path d="M42 84 C30 84 24 76 26 66 l5 -2"/>'
        '<path d="M68 101 C72 110 70 118 62 125 l8 0"/>'
        '</g>'
        '<circle cx="60" cy="72" r="31" fill="#F2C14E"/>'
        f'<g stroke="{TINTA}" stroke-width="2.4">'
        '<path d="M48 66 q4 -5 8 0"/><path d="M64 66 q4 -5 8 0"/><path d="M56 74 q4 4 8 0"/>'
        '</g>'
        '<ellipse cx="45" cy="74" rx="5" ry="3.4" fill="#F09A7A" opacity=".85"/>'
        '<ellipse cx="75" cy="74" rx="5" ry="3.4" fill="#F09A7A" opacity=".85"/>'
        '</svg>'
    )


def _papa_svg():
    # Triángulo verde corriendo
    verde = "#7FBF9A"
    return (
        '<svg viewBox="0 0 120 130" xmlns="http://www.w3.org/2000/svg" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        f'<g stroke="{verde}" stroke-width="9">'
        '<path d="M44 72 C34 74 28 76 20 82"/>'
        '<path d="M78 70 L95 70 L99 58"/>'
        '<path d="M52 100 L42 114 L31 112"/>'
        '<path d="M70 100 L74 124 L84 124"/>'
        '</g>'
        '<g stroke="#1E3A4C" stroke-width="2.2"><path d="M12 80 l6 -2 M13 86 l6 -2"/><path d="M104 56 l6 1 M103 62 l6 1"/></g>'
        f'<path d="M60 22 C66 22 70 28 73 37 L91 90 C94 99 89 104 81 104 L39 104 C31 104 26 99 29 90 L47 37 C50 28 54 22 60 22Z" fill="{verde}"/>'
        '<g stroke="#1E3A4C" stroke-width="2.3">'
        '<path d="M53 64 q3 3 6 0"/><path d="M65 62 q3 3 6 0"/><path d="M58 72 q4 3 8 0"/>'
        '</g>'
        '</svg>'
    )


def _rosa_svg():
    # Frijolito rosa saludando
    return (
        '<svg viewBox="0 0 120 130" xmlns="http://www.w3.org/2000/svg" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        f'<g stroke="{TINTA}" stroke-width="2.6">'
        '<path d="M36 70 C26 66 20 58 18 46"/><path d="M84 72 C94 74 100 70 104 62"/>'
        '<path d="M50 104 L48 124 l-7 0"/><path d="M70 104 L74 124 l7 0"/>'
        '<path d="M14 40 l3 -6 M20 38 l1 -6"/>'
        '</g>'
        '<rect x="32" y="40" width="56" height="66" rx="26" fill="#F4A3BE"/>'
        f'<g stroke="{TINTA}" stroke-width="2.4"><path d="M47 66 q4 -5 8 0"/><path d="M65 66 q4 -5 8 0"/><path d="M56 75 q4 4 8 0"/></g>'
        '<ellipse cx="45" cy="76" rx="4.5" ry="3" fill="#E86A92" opacity=".55"/>'
        '<ellipse cx="75" cy="76" rx="4.5" ry="3" fill="#E86A92" opacity=".55"/>'
        '</svg>'
    )


# color fuerte, color suave, dibujo
PERFILES = {
    "mama": ("#F2C14E", "#FBE7A6", _mama_svg),
    "papa": ("#7FBF9A", "#D4ECDD", _papa_svg),
    "otro": ("#F4A3BE", "#F9D3E1", _rosa_svg),
}


def perfil(nombre):
    n = nombre.lower().replace("á", "a")
    if "mam" in n or "madre" in n:
        return PERFILES["mama"]
    if "pap" in n or "padre" in n:
        return PERFILES["papa"]
    return PERFILES["otro"]


def mascota(nombre, clase="mascota"):
    return f'<div class="{clase}">{perfil(nombre)[2]()}</div>'



def md(h: str):
    st.markdown(h, unsafe_allow_html=True)


# ---------- Estilos ----------
md(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
:root { --ink:#1E1E1E; --cream:#FBF6EC; --muted:#7A746A; --card:#FFFFFF; }
html, body, .stApp, p, div, label, button, input, textarea, h1, h2, h3 { font-family: 'Plus Jakarta Sans', system-ui, sans-serif !important; }
[data-testid="stIconMaterial"] { font-family: 'Material Symbols Rounded' !important; }
.stApp { background: var(--cream); color: var(--ink); }
header[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display:none !important; }
.block-container { padding: 1.2rem 1rem 3rem !important; max-width: 480px !important; }

/* Columnas lado a lado también en el celular */
[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .6rem !important; }
[data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }

/* Encabezado */
.top { display:flex; align-items:center; gap:.75rem; margin:.2rem 0 .9rem; }
.avatar { width:64px; height:64px; border-radius:50%; display:flex; align-items:center; justify-content:center; overflow:visible;
          font-weight:800; font-size:1.35rem; color:var(--ink); flex-shrink:0; }
.hola { font-size:.9rem; color:var(--muted); line-height:1.1; }
.nombre { font-size:1.55rem; font-weight:800; line-height:1.15; letter-spacing:-.02em; }
.fecha { margin-left:auto; background:#fff; border-radius:999px; padding:.45rem .85rem; font-size:.85rem; font-weight:600; }

/* Selectores tipo píldora */
button[data-variant="segmented_control"] { border-radius:999px !important; border:none !important; background:#fff !important;
    padding:.5rem 1.15rem !important; min-height:2.7rem; color:var(--ink) !important; box-shadow:none !important; margin-right:.4rem !important; }
button[data-variant="segmented_control"] p { font-size:1rem !important; font-weight:700 !important; }
button[data-variant="segmented_control"][aria-checked="true"] { background:var(--ink) !important; }
button[data-variant="segmented_control"][aria-checked="true"] p { color:#fff !important; }

.st-key-rango_hist button[data-variant="segmented_control"], .st-key-rango_graf button[data-variant="segmented_control"] { padding:.4rem .8rem !important; min-height:2.4rem; margin-right:.25rem !important; }
.st-key-rango_hist button p, .st-key-rango_graf button p { font-size:.9rem !important; }

/* Tarjeta principal con anillo */
.hero { background:#fff; border-radius:32px; padding:1.1rem 1rem 1.3rem; text-align:center; margin:.6rem 0 .8rem; }
.hero svg { width:100%; max-width:290px; height:auto; display:block; margin:0 auto -.4rem; }
.chip { display:inline-block; border-radius:999px; padding:.42rem 1rem; font-weight:700; font-size:.92rem; }
.sub { color:var(--muted); font-size:.85rem; margin-top:.5rem; }

/* Mini tarjetas */
.grid { display:grid; grid-template-columns:repeat(3,1fr); gap:.6rem; margin:.2rem 0 .8rem; }
.mini { border-radius:24px; padding:.8rem .75rem .85rem; min-height:118px; display:flex; flex-direction:column; }
.mini .ico { width:34px; height:34px; border-radius:50%; background:rgba(255,255,255,.75); display:flex; align-items:center; justify-content:center; }
.mini .ico svg { width:18px; height:18px; }
.mini .lbl { font-size:.75rem; margin-top:auto; padding-top:.5rem; opacity:.8; line-height:1.15; }
.mini .val { font-size:1.45rem; font-weight:800; letter-spacing:-.02em; line-height:1.15; }
.mini .val small { font-size:.75rem; font-weight:600; opacity:.7; }

/* Tarjeta del asistente */
.tip { position:relative; overflow:hidden; background:#F7C6D9; border-radius:28px; padding:1rem 1.1rem 1.1rem; margin:.2rem 0 1rem; }
.tip .t1 { font-size:.75rem; font-weight:600; opacity:.7; }
.tip .t2 { font-size:1.02rem; font-weight:700; line-height:1.35; margin-top:.25rem; position:relative; z-index:1; max-width:88%; }
.tip .t2 b { text-decoration: underline; text-decoration-thickness:3px; text-underline-offset:3px; }
.tip .mascota { position:absolute; right:-6px; bottom:-14px; width:96px; }
.tip .t2 { max-width:72% !important; }
.avatar .mini-masc { width:62px; margin-top:4px; }
.mascota svg, .mini-masc svg, .grande svg { width:100%; height:auto; display:block; transform-origin:50% 85%; animation:baile 2.6s ease-in-out infinite; }
.grande { width:120px; margin:.2rem auto .4rem; }
@keyframes baile { 0%,100% { transform:rotate(-5deg) translateY(0); } 50% { transform:rotate(5deg) translateY(-4px); } }
@media (prefers-reduced-motion: reduce) { .mascota svg, .mini-masc svg, .grande svg { animation:none; } }

/* Pestañas como píldoras */
[role="tablist"] { gap:.3rem; background:#fff; border-radius:999px; padding:.3rem; border:none !important; box-shadow:none !important; width:100%; }
[role="tablist"] > :not([data-testid="stTab"]) { display:none !important; }
[data-testid="stTab"] { border-radius:999px !important; padding:.6rem .5rem !important; flex:1; justify-content:center; display:flex; border:none !important; }
[data-testid="stTab"] p { font-size:1rem !important; font-weight:700 !important; }
[data-testid="stTab"][aria-selected="true"] { background:var(--ink) !important; }
[data-testid="stTab"][aria-selected="true"] p { color:#fff !important; }
[role="tablist"]::after, [role="tablist"]::before, .react-aria-SelectionIndicator { display:none !important; }

/* Formulario */
[data-testid="stForm"] { background:#fff; border:none !important; border-radius:32px; padding:1.2rem 1rem 1rem !important; }
[data-testid="stForm"] label p { font-weight:700 !important; font-size:.95rem !important; }
.st-key-alta, .st-key-baja, .st-key-pulso { border-radius:24px; padding:.7rem .7rem .55rem; }
.st-key-alta { background:#F7C6D9; } .st-key-baja { background:#BCD6F4; } .st-key-pulso { background:#F6E08A; }
.st-key-alta input, .st-key-baja input, .st-key-pulso input { font-size:2rem !important; font-weight:800 !important; background:transparent !important; padding-left:.2rem !important; }
.st-key-alta [data-baseweb="input"], .st-key-baja [data-baseweb="input"], .st-key-pulso [data-baseweb="input"] { background:rgba(255,255,255,.55) !important; border:none !important; border-radius:16px !important; }
.st-key-alta [data-testid="stNumberInputContainer"], .st-key-baja [data-testid="stNumberInputContainer"], .st-key-pulso [data-testid="stNumberInputContainer"] { border:none !important; background:transparent !important; }
.st-key-alta button, .st-key-baja button, .st-key-pulso button { background:transparent !important; }
[data-testid="stForm"] [data-testid="stExpander"] details { border:none; background:var(--cream); border-radius:20px; }

/* Botones */
[data-testid="stElementContainer"]:has(.stFormSubmitButton), [data-testid="stElementContainer"]:has(.stButton), [data-testid="stElementContainer"]:has(.stDownloadButton) { width:100% !important; }
[data-testid="stFormSubmitButton"], .stButton, .stDownloadButton { width:100% !important; }
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
    width:100%; border-radius:999px !important; padding:.85rem 1rem !important; min-height:3.3rem;
    background:var(--ink) !important; color:#fff !important; border:none !important; }
.stButton button p, .stFormSubmitButton button p, .stDownloadButton button p { font-size:1.1rem !important; font-weight:700 !important; color:#fff !important; }
.stDownloadButton button { background:#C9E2A8 !important; }
.stDownloadButton button p { color:var(--ink) !important; }

/* Historial */
.lista { display:flex; flex-direction:column; gap:.5rem; margin:.4rem 0 1rem; }
.item { background:#fff; border-radius:22px; padding:.65rem .8rem .65rem .65rem; display:flex; align-items:center; gap:.75rem; }
.dia { width:50px; height:54px; border-radius:16px; display:flex; flex-direction:column; align-items:center; justify-content:center; flex-shrink:0; }
.dia b { font-size:1.2rem; line-height:1; } .dia span { font-size:.7rem; font-weight:600; }
.med { flex:1; min-width:0; }
.med .p { font-size:1.2rem; font-weight:800; letter-spacing:-.01em; } .med .p small { font-size:.72rem; font-weight:600; color:var(--muted); }
.med .d { font-size:.78rem; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.item .chip { font-size:.75rem; padding:.3rem .65rem; white-space:nowrap; }
.seccion { font-size:1.3rem; font-weight:800; letter-spacing:-.02em; margin:.6rem 0 .2rem; }

/* Gráfica */
.st-key-graf { background:#fff; border-radius:32px; padding:1rem .6rem .4rem; }
.leyenda { display:flex; gap:.5rem; margin:.1rem .4rem .3rem; }
.leyenda span { border-radius:999px; padding:.3rem .75rem; font-size:.8rem; font-weight:700; }

[data-testid="stExpander"] details { border-radius:20px; border:none; background:#fff; }
.pie { color:var(--muted); font-size:.78rem; text-align:center; margin-top:1.5rem; line-height:1.5; }
</style>
"""
)


# ---------- Clave de acceso (opcional) ----------
CLAVE = secret("clave")
# La clave también puede venir en el enlace (…?persona=Mamá&clave=xxxx) para no tener que escribirla
if CLAVE and str(st.query_params.get("clave", "")) == str(CLAVE):
    st.session_state.autorizado = True
if CLAVE and not st.session_state.get("autorizado"):
    md('<div class="hero"><div style="font-size:3rem">❤️</div><div class="nombre">Mi Presión</div>'
       '<div class="sub">Escribe la clave de la familia para entrar</div></div>')
    clave = st.text_input("Clave de acceso", type="password")
    if st.button("Entrar"):
        if clave == CLAVE:
            st.session_state.autorizado = True
            st.rerun()
        else:
            st.error("Clave incorrecta")
    st.stop()


# ---------- Almacenamiento ----------
# Los datos viven en una hoja de Google. La hoja tiene un pequeño script (puente.gs)
# publicado como "aplicación web"; la app le manda y le pide datos por ese enlace.
def _puente(metodo, datos=None):
    url = secret("enlace_hoja")
    if metodo == "GET":
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode({"clave": CLAVE_DATOS}))
    else:
        cuerpo = json.dumps({"clave": CLAVE_DATOS, **datos}).encode("utf-8")
        req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if resp.get("error"):
        raise RuntimeError("La hoja rechazó la conexión: revisa que clave_datos sea igual en el script y en los secretos.")
    return resp


@st.cache_data(ttl=60, show_spinner=False)
def cargar() -> pd.DataFrame:
    if USA_HOJA:
        filas = _puente("GET")["filas"]
        df = pd.DataFrame(filas[1:], columns=filas[0]) if len(filas) > 1 else pd.DataFrame(columns=COLUMNAS)
    elif CSV_LOCAL.exists():
        df = pd.read_csv(CSV_LOCAL, dtype={"id": str})
    else:
        df = pd.DataFrame(columns=COLUMNAS)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS)
    df["id"] = df["id"].astype(str)
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
    for c in ["sistolica", "diastolica", "pulso"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["notas"] = df["notas"].fillna("").astype(str)
    df["brazo"] = df["brazo"].fillna("").astype(str)
    return df.dropna(subset=["fecha_hora", "sistolica", "diastolica"])


def guardar(fila: dict):
    if USA_HOJA:
        _puente("POST", {"accion": "agregar", "fila": {c: str(fila[c]) for c in COLUMNAS}})
    else:
        nuevo = pd.DataFrame([fila], columns=COLUMNAS)
        nuevo.to_csv(CSV_LOCAL, mode="a", header=not CSV_LOCAL.exists(), index=False)
    cargar.clear()


def borrar(registro_id: str):
    if USA_HOJA:
        _puente("POST", {"accion": "borrar", "id": registro_id})
    else:
        df = pd.read_csv(CSV_LOCAL, dtype={"id": str})
        df[df["id"] != registro_id].to_csv(CSV_LOCAL, index=False)
    cargar.clear()


# ---------- Clasificación (guías AHA/ACC) ----------
def clasificar(sis, dia):
    if sis > 180 or dia > 120:
        e = "Crisis hipertensiva"
    elif sis >= 140 or dia >= 90:
        e = "Hipertensión etapa 2"
    elif sis >= 130 or dia >= 80:
        e = "Hipertensión etapa 1"
    elif sis >= 120:
        e = "Elevada"
    elif sis < 90 or dia < 60:
        e = "Baja"
    else:
        e = "Normal"
    return (e, *ESTADOS[e])


def aviso_crisis(sis, dia):
    if sis > 180 or dia > 120:
        st.error(
            "🚨 **Presión muy alta.** Descansa 5 minutos y vuelve a medir. "
            "Si sigue así, o hay dolor de pecho, falta de aire, dolor de cabeza fuerte, "
            "visión borrosa o dificultad para hablar, **llama a emergencias de inmediato.**"
        )


# ---------- Piezas visuales ----------
ICONOS = {
    "corazon": '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>',
    "pulso": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "calendario": '<rect x="3" y="4" width="18" height="18" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "grafica": '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
}


def icono(nombre):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="#1E1E1E" stroke-width="2.2" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONOS[nombre]}</svg>')


# Segmentos del anillo: (estado, desde, hasta, grados de arco)
SEGMENTOS = [("Baja", 70, 90, 34), ("Normal", 90, 120, 56), ("Elevada", 120, 130, 40),
             ("Hipertensión etapa 1", 130, 140, 40), ("Hipertensión etapa 2", 140, 180, 56),
             ("Crisis hipertensiva", 180, 210, 44)]
INICIO = 135  # grados (0 = derecha, sentido horario)


def _punto(ang, r, c=150):
    a = math.radians(ang)
    return c + r * math.cos(a), c + r * math.sin(a)


def angulo_de(sis):
    ang = INICIO
    for _, a, b, g in SEGMENTOS:
        if sis <= b:
            return ang + g * (max(sis, a) - a) / (b - a)
        ang += g
    return ang


def anillo(sis, dia, texto_abajo="mmHg"):
    r, ancho, recorte = 116, 26, 9.5
    partes, ang = [], INICIO
    for estado, _, _, g in SEGMENTOS:
        a1, a2 = ang + recorte, ang + g - recorte
        x1, y1 = _punto(a1, r)
        x2, y2 = _punto(a2, r)
        partes.append(f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 0 1 {x2:.1f} {y2:.1f}" stroke="{ESTADOS[estado][0]}" '
                      f'stroke-width="{ancho}" stroke-linecap="round" fill="none"/>')
        ang += g
    mx, my = _punto(angulo_de(sis), r)
    tinta = clasificar(sis, dia)[2]
    partes.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="19" fill="#fff" stroke="#1E1E1E" stroke-width="3"/>'
                  f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="8" fill="{tinta}"/>')
    partes.append(f'<text x="150" y="160" text-anchor="middle" font-size="58" font-weight="800" fill="#1E1E1E" '
                  f'letter-spacing="-2">{int(sis)}/{int(dia)}</text>'
                  f'<text x="150" y="192" text-anchor="middle" font-size="15" fill="#7A746A">{texto_abajo}</text>')
    return f'<svg viewBox="0 10 300 255" xmlns="http://www.w3.org/2000/svg">{"".join(partes)}</svg>'


def mini(color, ico, etiqueta, valor, unidad=""):
    u = f" <small>{unidad}</small>" if unidad else ""
    return (f'<div class="mini" style="background:{color}"><div class="ico">{icono(ico)}</div>'
            f'<div class="lbl">{etiqueta}</div><div class="val">{valor}{u}</div></div>')


def fecha_corta(t):
    hoy = dt.datetime.now(TZ).date()
    if t.date() == hoy:
        return f"Hoy, {t:%H:%M}"
    if t.date() == hoy - dt.timedelta(days=1):
        return f"Ayer, {t:%H:%M}"
    return f"{DIAS[t.weekday()]} {t.day} {MESES[t.month - 1]}, {t:%H:%M}"


def ahora_naive():
    return pd.Timestamp(dt.datetime.now(TZ).replace(tzinfo=None))


def filtrar(df, dias):
    return df if not dias else df[df["fecha_hora"] >= ahora_naive() - pd.Timedelta(days=dias)]


# ---------- Encabezado y persona ----------
param = st.query_params.get("persona")
if "persona" not in st.session_state:
    st.session_state.persona = param if param in PERSONAS else PERSONAS[0]
    st.session_state.sel_persona = st.session_state.persona


def _cambiar_persona():
    # si tocan la opción ya marcada, no dejamos el selector vacío
    if st.session_state.sel_persona is None:
        st.session_state.sel_persona = st.session_state.persona
    else:
        st.session_state.persona = st.session_state.sel_persona


persona = st.session_state.persona
hoy = dt.datetime.now(TZ)
FUERTE, SUAVE, _ = perfil(persona)
md(f'<div class="top"><div class="avatar" style="background:{SUAVE}">{mascota(persona, "mini-masc")}</div>'
   f'<div><div class="hola">Hola,</div><div class="nombre">{html.escape(persona)}</div></div>'
   f'<div class="fecha">{DIAS[hoy.weekday()]} {hoy.day} {MESES[hoy.month - 1]}</div></div>')

md("<style>" + "".join(
    f'.st-key-sel_persona button[data-variant="segmented_control"]:nth-of-type({i + 1})[aria-checked="true"] '
    f'{{ background:{perfil(n)[0]} !important; }}'
    f'.st-key-sel_persona button[data-variant="segmented_control"]:nth-of-type({i + 1})[aria-checked="true"] p '
    f'{{ color:#1E1E1E !important; }}'
    for i, n in enumerate(PERSONAS)) + "</style>")
st.segmented_control("¿Quién se mide?", PERSONAS, key="sel_persona", on_change=_cambiar_persona,
                     label_visibility="collapsed")
st.query_params["persona"] = persona

if not USA_HOJA:
    st.caption("⚠️ Modo prueba: los datos se guardan en este equipo (sin Google Sheets).")

try:
    todos = cargar()
except Exception as e:
    st.error(f"No pude leer los datos: {e}")
    st.stop()

datos = (todos[todos["persona"] == persona].iloc[::-1]
         .sort_values("fecha_hora", ascending=False, kind="stable"))

# ---------- Resumen ----------
if datos.empty:
    md(f'<div class="hero">{mascota(persona, "grande")}'
       '<div class="nombre" style="font-size:1.25rem">Aún no hay mediciones</div>'
       '<div class="sub">Registra la primera abajo y aquí verás tu resumen.</div></div>')
else:
    u = datos.iloc[0]
    est, fondo, tinta = clasificar(u.sistolica, u.diastolica)
    brazo = f" · Brazo {u.brazo.lower()[:3]}." if u.brazo else ""
    md(f'<div class="hero">{anillo(u.sistolica, u.diastolica, "última medición · mmHg")}'
       f'<span class="chip" style="background:{fondo};color:{tinta}">{est}</span>'
       f'<div class="sub">{fecha_corta(u.fecha_hora)}{brazo}</div></div>')

    sem = filtrar(datos, 7)
    pulso_txt = "—" if pd.isna(u.pulso) else f"{int(u.pulso)}"
    prom_txt = f"{sem.sistolica.mean():.0f}/{sem.diastolica.mean():.0f}" if len(sem) else "—"
    md('<div class="grid">'
       + mini("#F7C6D9", "corazon", "Pulso", pulso_txt, "lpm" if pulso_txt != "—" else "")
       + mini("#C9E2A8", "grafica", "Promedio 7 días", prom_txt)
       + mini("#BCD6F4", "calendario", "Mediciones 30 días", len(filtrar(datos, 30)))
       + "</div>")

    # Mensaje del "asistente": compara esta semana con la anterior
    previa = datos[(datos.fecha_hora < ahora_naive() - pd.Timedelta(days=7))
                   & (datos.fecha_hora >= ahora_naive() - pd.Timedelta(days=14))]
    if len(sem) >= 2 and len(previa) >= 2:
        dif = sem.sistolica.mean() - previa.sistolica.mean()
        if abs(dif) < 4:
            msg = "Tu presión alta se mantuvo <b>estable</b> esta semana comparada con la anterior. ¡Sigue así!"
        elif dif < 0:
            msg = f"Tu presión alta promedio <b>bajó {abs(dif):.0f} puntos</b> esta semana. ¡Muy bien! 👏"
        elif dif < 8:
            msg = f"Tu presión alta promedio <b>subió {dif:.0f} puntos</b> esta semana. Vamos a vigilarla."
        else:
            msg = f"Tu presión alta promedio <b>subió {dif:.0f} puntos</b> esta semana. Coméntalo con tu médico si sigue así."
    else:
        msg = "Mide tu presión <b>a la misma hora</b> cada día para poder comparar mejor tus semanas."
    md(f'<div class="tip" style="background:{SUAVE}"><div class="t1">Tu resumen semanal</div>'
       f'<div class="t2">{msg}</div>{mascota(persona)}</div>')

tab_reg, tab_hist, tab_graf = st.tabs(["Registrar", "Historial", "Gráfica"])

# ---------- Registrar ----------
with tab_reg:
    ahora = dt.datetime.now(TZ)
    with st.form("nuevo", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1.container(key="alta"):
            sis = st.number_input("Alta", 60, 260, 120, step=1)
        with c2.container(key="baja"):
            dia = st.number_input("Baja", 30, 160, 80, step=1)
        with st.container(key="pulso"):
            pulso = st.number_input("Pulso (opcional)", 0, 220, 0, step=1, help="Déjalo en 0 si no lo mediste")
        with st.expander("Fecha, hora, brazo y notas"):
            c3, c4 = st.columns(2)
            fecha = c3.date_input("Fecha", ahora.date(), format="DD/MM/YYYY")
            hora = c4.time_input("Hora", ahora.time().replace(second=0, microsecond=0), step=300)
            brazo = st.radio("Brazo", ["Izquierdo", "Derecho"], horizontal=True)
            notas = st.text_input("Notas", placeholder="Ej: después de caminar, tomé medicina…")
        enviado = st.form_submit_button("Guardar medición")

    if enviado:
        if sis <= dia:
            st.error("La presión alta debe ser mayor que la baja. Revisa los números.")
        else:
            guardar(
                {
                    "id": uuid.uuid4().hex[:10],
                    "persona": persona,
                    "fecha_hora": dt.datetime.combine(fecha, hora).strftime("%Y-%m-%d %H:%M"),
                    "sistolica": int(sis),
                    "diastolica": int(dia),
                    "pulso": int(pulso) if pulso else "",
                    "brazo": brazo,
                    "notas": notas,
                }
            )
            st.session_state.ultimo_guardado = (int(sis), int(dia))
            st.rerun()

    if "ultimo_guardado" in st.session_state:
        sis_g, dia_g = st.session_state.pop("ultimo_guardado")
        est, fondo, tinta = clasificar(sis_g, dia_g)
        md(f'<div class="tip" style="background:{SUAVE};margin-top:.8rem"><div class="t1">✅ ¡Medición guardada!</div>'
           f'<div class="t2">{sis_g}/{dia_g}</div>'
           f'<span class="chip" style="background:{fondo};color:{tinta};margin-top:.4rem;position:relative;z-index:1">{est}</span>'
           f'{mascota(persona)}</div>')
        aviso_crisis(sis_g, dia_g)

# ---------- Historial ----------
RANGOS = {"7 días": 7, "30 días": 30, "90 días": 90, "Todo": None}

with tab_hist:
    if datos.empty:
        st.info("Todavía no hay mediciones. Registra la primera en la pestaña Registrar.")
    else:
        rango = st.segmented_control("Periodo", list(RANGOS), default="30 días", key="rango_hist",
                                     label_visibility="collapsed") or "30 días"
        vista = filtrar(datos, RANGOS[rango])

        if vista.empty:
            st.info("No hay mediciones en este periodo.")
        else:
            est, fondo, tinta = clasificar(vista.sistolica.mean(), vista.diastolica.mean())
            pp = "—" if vista.pulso.isna().all() else f"{vista.pulso.mean():.0f}"
            md('<div class="grid" style="margin-top:.6rem">'
               + mini(fondo, "grafica", "Promedio", f"{vista.sistolica.mean():.0f}/{vista.diastolica.mean():.0f}")
               + mini("#F6E08A", "calendario", "Mediciones", len(vista))
               + mini("#F7C6D9", "corazon", "Pulso prom.", pp, "lpm" if pp != "—" else "")
               + "</div>")

            items = []
            for r in vista.head(60).itertuples():
                e, f, t = clasificar(r.sistolica, r.diastolica)
                extra = []
                if not pd.isna(r.pulso):
                    extra.append(f"♥ {int(r.pulso)}")
                if r.notas:
                    extra.append(html.escape(r.notas))
                det = f"{r.fecha_hora:%H:%M}" + (" · " + " · ".join(extra) if extra else "")
                items.append(
                    f'<div class="item"><div class="dia" style="background:{f};color:{t}">'
                    f'<b>{r.fecha_hora.day}</b><span>{MESES[r.fecha_hora.month - 1]}</span></div>'
                    f'<div class="med"><div class="p">{int(r.sistolica)}/{int(r.diastolica)} <small>mmHg</small></div>'
                    f'<div class="d">{det}</div></div>'
                    f'<span class="chip" style="background:{f};color:{t}">{CORTO.get(e, e)}</span></div>'
                )
            md('<div class="seccion">Mediciones</div><div class="lista">' + "".join(items) + "</div>")
            if len(vista) > 60:
                st.caption(f"Mostrando las 60 más recientes de {len(vista)}. Descarga el archivo para verlas todas.")

            csv = vista[COLUMNAS[1:]].to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇  Descargar para el médico", csv,
                               file_name=f"presion_{persona}_{dt.date.today():%Y%m%d}.csv", mime="text/csv")

        with st.expander("🗑️  Borrar una medición equivocada"):
            opciones = {
                f"{r.fecha_hora:%d/%m/%y %H:%M} — {int(r.sistolica)}/{int(r.diastolica)}": r.id
                for r in datos.head(30).itertuples()
            }
            elegido = st.selectbox("Medición", list(opciones))
            if st.button("Borrar esta medición"):
                borrar(opciones[elegido])
                st.rerun()

# ---------- Gráfica ----------
with tab_graf:
    if len(datos) < 2:
        st.info("Necesitas al menos 2 mediciones para ver la gráfica.")
    else:
        rango_g = st.segmented_control("Periodo", list(RANGOS), default="30 días", key="rango_graf",
                                       label_visibility="collapsed") or "30 días"
        g = filtrar(datos, RANGOS[rango_g])
        if len(g) < 2:
            st.info("No hay suficientes mediciones en este periodo.")
        else:
            largo = g.melt(id_vars=["fecha_hora"], value_vars=["sistolica", "diastolica"],
                           var_name="Tipo", value_name="mmHg").replace({"sistolica": "Alta", "diastolica": "Baja"})
            ymin = min(55, largo.mmHg.min() - 5)
            ymax = max(150, largo.mmHg.max() + 5)
            colores = alt.Scale(domain=["Alta", "Baja"], range=["#E86A92", "#5B8DEF"])
            x = alt.X("fecha_hora:T", title=None,
                      axis=alt.Axis(format="%d/%m", labelColor="#7A746A", grid=False, domain=False, ticks=False,
                                    labelFontSize=12))
            y = alt.Y("mmHg:Q", title=None, scale=alt.Scale(domain=[ymin, ymax]),
                      axis=alt.Axis(labelColor="#7A746A", gridColor="#F0EBE1", domain=False, ticks=False,
                                    labelFontSize=12, tickCount=5))

            zonas = pd.DataFrame({"y1": [90, 60], "y2": [120, 80], "c": ["#E8F3DA", "#E4EEFB"]})
            bandas = alt.Chart(zonas).mark_rect(opacity=.8).encode(
                y=alt.Y("y1:Q", scale=alt.Scale(domain=[ymin, ymax])), y2="y2:Q", color=alt.Color("c:N", scale=None, legend=None))
            lineas = alt.Chart(largo).mark_line(interpolate="monotone", strokeWidth=3).encode(
                x=x, y=y, color=alt.Color("Tipo:N", scale=colores, legend=None))
            puntos = alt.Chart(largo).mark_circle(size=55, opacity=1, stroke="#fff", strokeWidth=2).encode(
                x=x, y=y, color=alt.Color("Tipo:N", scale=colores, legend=None),
                tooltip=[alt.Tooltip("fecha_hora:T", title="Fecha", format="%d/%m %H:%M"), "Tipo", "mmHg"])
            graf = (bandas + lineas + puntos).properties(height=300).configure_view(strokeWidth=0) \
                .configure(background="transparent")

            with st.container(key="graf"):
                md('<div class="leyenda"><span style="background:#F7C6D9;color:#8A1C3C">● Alta</span>'
                   '<span style="background:#BCD6F4;color:#1D4F8A">● Baja</span></div>')
                st.altair_chart(graf, width="stretch")
            md('<div class="sub" style="text-align:center">Las franjas de color marcan la zona normal: '
               '<b style="color:#36561A">verde</b> para la alta (90–120) y <b style="color:#1D4F8A">azul</b> '
               'para la baja (60–80).</div>')

md('<div class="pie">Esta app es solo un registro y no sustituye la opinión de un médico.<br>'
   'Para medir: sentado, 5 min de reposo, espalda apoyada, brazo a la altura del corazón.</div>')
