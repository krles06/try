import streamlit as st
import pdfplumber
import pandas as pd
import openai

# Clave API desde secrets (Streamlit Cloud)
openai.api_key = st.secrets["OPENAI_API_KEY"]

st.set_page_config(page_title="FacturaFlow AI", layout="wide")
st.title("📄 FacturaFlow AI - Carga masiva y extracción inteligente de datos")

uploaded_files = st.file_uploader("Sube tus facturas en PDF", type="pdf", accept_multiple_files=True)

# Campos posibles a extraer
campos_posibles = [
    "Proveedor", "CIF", "Número de factura",
    "Fecha", "Base imponible", "IVA", "Total"
]

campos_seleccionados = st.multiselect(
    "Selecciona los campos que quieres extraer y en qué orden",
    options=campos_posibles,
    default=campos_posibles
)

def extract_text_from_pdf(file):
    try:
        with pdfplumber.open(file) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception:
        return None

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

if uploaded_files and campos_seleccionados:
    resultados = []

    with st.spinner("Procesando facturas..."):
        for file in uploaded_files:
            nombre_archivo = file.name
            try:
                text = extract_text_from_pdf(file)
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

    # Crear y mostrar tabla
    columnas_finales = ["archivo", "error"] + campos_seleccionados
    df = pd.DataFrame(resultados)
    df = df[columnas_finales]
    st.success("¡Facturas procesadas!")
    st.dataframe(df)

    # Botón para descargar Excel
    excel_name = "facturas_exportadas.xlsx"
    df.to_excel(excel_name, index=False)
    with open(excel_name, "rb") as f:
        st.download_button("📥 Descargar Excel", f, file_name=excel_name)
