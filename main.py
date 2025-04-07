import streamlit as st
import pdfplumber
import pandas as pd
import openai
import pytesseract
from PIL import Image
import fitz  # PyMuPDF
from io import BytesIO

# API key desde secrets
openai.api_key = st.secrets["OPENAI_API_KEY"]

st.set_page_config(page_title="FacturaFlow AI + OCR", layout="wide")
st.title("📄 FacturaFlow AI - Extrae datos de facturas escaneadas o digitales")

uploaded_files = st.file_uploader("Sube tus facturas en PDF", type="pdf", accept_multiple_files=True)

# Selector de campos
campos_posibles = [
    "Proveedor", "CIF", "Número de factura",
    "Fecha", "Base imponible", "IVA", "Total"
]

campos_seleccionados = st.multiselect(
    "Selecciona los campos que quieres extraer y en qué orden",
    options=campos_posibles,
    default=campos_posibles
)

# Función de extracción con diagnóstico
def extract_text(file, nombre_archivo):
    try:
        file_bytes = file.read()
        file_buffer = BytesIO(file_bytes)

        # Intento con pdfplumber
        with pdfplumber.open(file_buffer) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            st.info(f"📄 {nombre_archivo}: Texto extraído con pdfplumber")
            st.text(text)
            return text
    except Exception as e:
        st.warning(f"⚠️ pdfplumber falló con {nombre_archivo}: {e}")

    # OCR
    try:
        file_buffer = BytesIO(file_bytes)
        doc = fitz.open(stream=file_buffer.read(), filetype="pdf")
        text = ""
        for page in doc:
            pix = page.get_pixmap(dpi=400)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = img.convert("L")
            img = img.point(lambda x: 0 if x < 180 else 255, '1')
            texto_ocr = pytesseract.image_to_string(img, lang="spa")
            text += texto_ocr + "\n"
        if text.strip():
            st.success(f"📷 {nombre_archivo}: Texto extraído con OCR")
            st.text(text)
            return text
        else:
            st.error(f"❌ {nombre_archivo}: OCR tampoco encontró texto.")
            return None
    except Exception as e:
        st.error(f"❌ {nombre_archivo}: Error al hacer OCR: {e}")
        return None

# GPT parsing
def parse_invoice_with_gpt(text, campos):
    prompt = f"""
Ets un assistent que rep textos de factures i ha d’extreure la informació següent en format JSON:

{chr(10).join(f"- {campo}" for campo in campos)}

Aquí tens el text d’una factura:

{text}

Retorna només el JSON. Si falta algun camp, deixa'l en blanc.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        return eval(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}

# Procesamiento
if uploaded_files and campos_seleccionados:
    resultados = []

    with st.spinner("Procesando facturas..."):
        for file in uploaded_files:
            nombre_archivo = file.name
            try:
                text = extract_text(file, nombre_archivo)
                if not text or text.strip() == "":
                    resultados.append({
                        "archivo": nombre_archivo,
                        "error": "No se pudo extraer texto del PDF",
                        **{campo: "" for campo in campos_seleccionados}
                    })
                    continue

                parsed_data = parse_invoice_with_gpt(text, campos_seleccionados)

                if "error" in parsed_data:
                    resultados.append({
                        "archivo": nombre_archivo,
                        "error": parsed_data["error"],
                        **{campo: "" for campo in campos_seleccionados}
                    })
                else:
                    resultados.append({
                        "archivo": nombre_archivo,
                        "error": "",
                        **{campo: parsed_data.get(campo, "") for campo in campos_seleccionados}
                    })

            except Exception as e:
                resultados.append({
                    "archivo": nombre_archivo,
                    "error": f"Error inesperado: {str(e)}",
                    **{campo: "" for campo in campos_seleccionados}
                })

    columnas_finales = ["archivo", "error"] + campos_seleccionados
    df = pd.DataFrame(resultados)
    df = df[columnas_finales]
    st.success("¡Facturas procesadas!")
    st.dataframe(df)

    excel_name = "facturas_exportadas.xlsx"
    df.to_excel(excel_name, index=False)
    with open(excel_name, "rb") as f:
        st.download_button("📥 Descargar Excel", f, file_name=excel_name)
