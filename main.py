import streamlit as st
import pdfplumber
import pandas as pd
import openai

# Cargar API key desde secrets
openai.api_key = st.secrets["OPENAI_API_KEY"]

st.set_page_config(page_title="FacturaFlow AI", layout="wide")
st.title("📄 FacturaFlow AI - Carga masiva y extracción inteligente de datos")

uploaded_files = st.file_uploader("Sube tus facturas en PDF", type="pdf", accept_multiple_files=True)

def extract_text_from_pdf(file):
    with pdfplumber.open(file) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def parse_invoice_with_gpt(text):
    prompt = f"""
Ets un assistent que rep textos de factures i ha d’extreure la informació següent en format JSON:
- Proveedor
- CIF o NIF
- Número de factura
- Fecha de emisión
- Base imponible
- IVA
- Total

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

if uploaded_files:
    resultados = []
    with st.spinner("Procesando facturas..."):
        for file in uploaded_files:
            text = extract_text_from_pdf(file)
            parsed_data = parse_invoice_with_gpt(text)
            parsed_data["archivo"] = file.name
            resultados.append(parsed_data)

    df = pd.DataFrame(resultados)
    st.success("¡Facturas procesadas con éxito!")
    st.dataframe(df)

    # Exportar a Excel
    excel_name = "facturas_exportadas.xlsx"
    df.to_excel(excel_name, index=False)
    with open(excel_name, "rb") as f:
        st.download_button("📥 Descargar Excel", f, file_name=excel_name)
