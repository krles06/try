import streamlit as st
import pdfplumber
import pandas as pd
import openai
import requests
from PIL import Image
import fitz  # PyMuPDF
from io import BytesIO

# Configuración general de la página
st.set_page_config(page_title="FacturAI - Extracción inteligente de facturas", layout="wide")

# Estilos personalizados
st.markdown("""
    <style>
    body {
        background-color: #ffffff;
        color: #111111;
        font-family: 'Segoe UI', sans-serif;
    }
    .title {
        font-size: 3rem;
        font-weight: bold;
        color: #ff7300;
    }
    .subheader {
        font-size: 1.2rem;
        margin-bottom: 2rem;
        color: #444;
    }
    .stButton>button {
        background-color: #ff7300;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: bold;
        border-radius: 6px;
    }
    .stDownloadButton>button {
        background-color: #222;
        color: white;
        border-radius: 6px;
    }
    </style>
""", unsafe_allow_html=True)

# Encabezado de la app
st.markdown("<div class='title'>FacturAI</div>", unsafe_allow_html=True)
st.markdown("<div class='subheader'>Extrae automáticamente información de tus facturas en PDF, incluso si están escaneadas.</div>", unsafe_allow_html=True)

# Claves API
openai.api_key = st.secrets["OPENAI_API_KEY"]
ocr_api_key = st.secrets["OCR_API_KEY"]

# Subida de archivos
archivos_subidos = st.file_uploader("📤 Sube tus facturas en PDF", type="pdf", accept_multiple_files=True)

# Campos disponibles
campos_disponibles = [
    "Proveedor", "CIF", "Número de factura",
    "Fecha", "Base imponible", "IVA", "Total"
]

campos_elegidos = st.multiselect(
    "📋 Elige los datos que deseas extraer y el orden en que se mostrarán:",
    options=campos_disponibles,
    default=campos_disponibles
)

# OCR con API de OCR.space con control de errores y calidad
def extraer_texto_ocrspace(imagen: Image.Image, nombre_archivo: str) -> str:
    try:
        buffer = BytesIO()
        imagen.save(buffer, format="PNG")
        buffer.seek(0)

        respuesta = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": buffer},
            data={"apikey": ocr_api_key, "language": "spa", "OCREngine": "2"},
        )

        if respuesta.status_code != 200:
            st.error(f"❌ {nombre_archivo}: Error HTTP {respuesta.status_code} en OCR.space")
            return None

        try:
            resultado = respuesta.json()
        except Exception:
            st.error(f"❌ {nombre_archivo}: Respuesta inválida desde OCR.space")
            return None

        if resultado.get("IsErroredOnProcessing"):
            mensaje = resultado.get("ErrorMessage", ["Error desconocido"])[0]
            st.error(f"❌ {nombre_archivo}: OCR.space devolvió un error: {mensaje}")
            return None

        texto_extraido = resultado["ParsedResults"][0]["ParsedText"]
        if len(texto_extraido.strip()) < 30:
            st.warning(f"⚠️ {nombre_archivo}: El texto es muy escaso. ¿Factura borrosa o ilegible?")
            return None

        return texto_extraido

    except requests.exceptions.RequestException as e:
        st.error(f"❌ {nombre_archivo}: Fallo de conexión con OCR.space: {e}")
        return None

# Extraer texto: pdfplumber o OCR
def extraer_texto_pdf(file, nombre_archivo):
    try:
        contenido = file.read()
        buffer = BytesIO(contenido)

        with pdfplumber.open(buffer) as pdf:
            texto = ""
            for page in pdf.pages:
                contenido_pagina = page.extract_text()
                if contenido_pagina:
                    texto += contenido_pagina + "\n"
        if texto.strip():
            st.info(f"📄 {nombre_archivo}: Texto extraído digitalmente")
            return texto
    except:
        pass

    try:
        buffer = BytesIO(contenido)
        doc = fitz.open(stream=buffer.read(), filetype="pdf")
        texto = ""
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            imagen = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_texto = extraer_texto_ocrspace(imagen, nombre_archivo)
            if ocr_texto:
                texto += ocr_texto + "\n"
        if texto.strip():
            st.success(f"📷 {nombre_archivo}: Texto extraído con OCR")
            return texto
    except Exception as e:
        st.error(f"❌ {nombre_archivo}: Error al procesar el archivo: {e}")
        return None

# Llamada a OpenAI
def analizar_con_openai(texto, campos):
    prompt = f"""Eres un asistente que recibe el texto completo de una factura. Extrae la siguiente información y devuélvela en formato JSON:

{chr(10).join(f"- {campo}" for campo in campos)}

Texto de la factura:

{texto}

Devuelve solo el JSON. Si falta algún campo, deja su valor en blanco."""
    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        return eval(respuesta.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}

# Procesamiento de archivos
if archivos_subidos and campos_elegidos:
    resultados = []

    with st.spinner("🔎 Analizando facturas..."):
        for archivo in archivos_subidos:
            nombre = archivo.name
            try:
                texto = extraer_texto_pdf(archivo, nombre)
                if not texto or texto.strip() == "":
                    resultados.append({
                        "archivo": nombre,
                        "error": "No se pudo extraer texto del PDF",
                        **{campo: "" for campo in campos_elegidos}
                    })
                    continue

                resultado = analizar_con_openai(texto, campos_elegidos)

                if "error" in resultado:
                    resultados.append({
                        "archivo": nombre,
                        "error": resultado["error"],
                        **{campo: "" for campo in campos_elegidos}
                    })
                else:
                    resultados.append({
                        "archivo": nombre,
                        "error": "",
                        **{campo: resultado.get(campo, "") for campo in campos_elegidos}
                    })

            except Exception as e:
                resultados.append({
                    "archivo": nombre,
                    "error": f"Error inesperado: {str(e)}",
                    **{campo: "" for campo in campos_elegidos}
                })

    df = pd.DataFrame(resultados)
    columnas_finales = ["archivo", "error"] + campos_elegidos
    df = df[columnas_finales]

    st.success("✅ ¡Facturas procesadas correctamente!")
    st.dataframe(df)

    nombre_excel = "facturas_resultado.xlsx"
    df.to_excel(nombre_excel, index=False)
    with open(nombre_excel, "rb") as f:
        st.download_button("📥 Descargar Excel", f, file_name=nombre_excel)
