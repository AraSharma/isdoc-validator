import streamlit as st
from lxml import etree
from pathlib import Path
import fitz  # PyMuPDF
import re

st.set_page_config(page_title="ISDOC Validátor", layout="centered")
st.title("🧾 ISDOC Validátor (XML / ISDOC / PDF)")

uploaded_file = st.file_uploader("Nahraj fakturu (.isdoc, .xml nebo .pdf):", type=["isdoc", "xml", "pdf"])
xsd_path = Path("ISDOC_2013.xsd")

def extract_embedded_file(pdf_bytes):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            # 1. Globální přílohy (document-level attachments)
            attachments = doc.attachments()
            for fname, info in attachments.items():
                if fname.lower().endswith((".xml", ".isdoc")):
                    return info["file"]

            # 2. Přílohy vložené na jednotlivých stránkách (méně časté)
            for page in doc:
                for f in page.get_files():
                    if f["name"].lower().endswith((".xml", ".isdoc")):
                        return f["file"]
    except Exception as e:
        st.warning(f"Chyba při čtení příloh z PDF: {e}")
    return None

def extract_isdoc_from_text(pdf_bytes):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            full_text = ""
            for page in doc:
                full_text += page.get_text()
        match = re.search(r'(<Invoice[^>]+xmlns="http://isdoc.cz/namespace/2013"[^>]*>.*?</Invoice>)', full_text, re.DOTALL)
        if match:
            return match.group(1).encode("utf-8")
    except:
        pass
    return None

def validate_and_parse(xml_data: bytes):
    messages = []
    try:
        root = etree.fromstring(xml_data)
        tree = etree.ElementTree(root)
        try:
            with open(xsd_path, "rb") as f:
                schema_doc = etree.parse(f)
                schema = etree.XMLSchema(schema_doc)
            schema.assertValid(tree)
            messages.append("✅ Faktura je validní podle ISDOC XSD.")
        except Exception as e:
            messages.append(f"❌ Faktura není validní: {e}")
        messages.append("---")
        messages.append("📋 Výpis polí z faktury:")
        for el in tree.xpath("//*"):
            tag = el.tag.split("}")[-1]
            text = (el.text or "").strip()
            if text:
                messages.append(f"**{tag}:** {text}")
    except Exception as e:
        messages.append(f"🚫 Chyba při zpracování XML: {e}")
    return messages

if uploaded_file:
    st.markdown("### 🛠 Zpracovávám soubor...")
    xml_data = None
    file_bytes = uploaded_file.read()

    if uploaded_file.name.lower().endswith(".pdf"):
        xml_data = extract_embedded_file(file_bytes)
        if not xml_data:
            xml_data = extract_isdoc_from_text(file_bytes)
        if not xml_data:
            st.error("❌ ISDOC nebyl v PDF nalezen žádným způsobem.")
        else:
            results = validate_and_parse(xml_data)
            for line in results:
                st.markdown(line)
    else:
        xml_data = file_bytes
        results = validate_and_parse(xml_data)
        for line in results:
            st.markdown(line)
