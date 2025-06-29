import streamlit as st
from lxml import etree
from pathlib import Path
import fitz
import re
import json

st.set_page_config(page_title="ISDOC Validátor", layout="centered")
st.title("🧾 ISDOC Validátor")

uploaded_file = st.file_uploader("Nahraj fakturu:", type=["pdf", "xml", "isdoc"])
xsd_path = Path("ISDOC_2013.xsd")
rules_path = Path("rules.json")

def extract_from_pdf(pdf_bytes):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for name, file in doc.attachments().items():
                if name.lower().endswith((".xml", ".isdoc")):
                    return file["file"], f"fitz attachment: {name}"
            for page in doc:
                for f in page.get_files():
                    if f["name"].lower().endswith((".xml", ".isdoc")):
                        return f["file"], f"fitz page: {f['name']}"
    except Exception as e:
        return None, f"fitz error: {e}"
    return None, None

def extract_from_text(pdf_bytes):
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        full_text = "".join(page.get_text() for page in doc)
    match = re.search(r'(<Invoice.*?</Invoice>)', full_text, re.DOTALL)
    if match:
        return match.group(1).encode(), "text match"
    return None, None

def validate_xml(xml_data: bytes, rules: dict):
    errors = []
    values = {}
    try:
        root = etree.fromstring(xml_data)
        tree = etree.ElementTree(root)
        nsmap = root.nsmap.copy()
        ns = {"ns": nsmap.get(None, "")}

        for path in rules.get("required_fields", []):
            xp = "//" + "/".join([f"ns:{p}" for p in path.split("/")])
            result = tree.xpath(xp, namespaces=ns)
            if not result:
                errors.append(f"Chybí požadované pole: `{path}`")
            elif hasattr(result[0], "text"):
                values[path] = result[0].text.strip()

        for path, expected in rules.get("expected_values", {}).items():
            xp = "//" + "/".join([f"ns:{p}" for p in path.split("/")])
            result = tree.xpath(xp, namespaces=ns)
            found = result[0].text.strip() if result else None
            if found != expected:
                errors.append(f"Neshoda v hodnotě `{path}`: očekáváno `{expected}`, nalezeno `{found}`")
            values[path] = found or "–"
    except Exception as e:
        errors.append(f"Chyba při zpracování XML: {e}")
    return errors, values

if uploaded_file:
    st.markdown("### 🔍 Zpracovávám soubor...")
    xml_data, method = None, None

    if uploaded_file.name.lower().endswith(".pdf"):
        data = uploaded_file.read()
        xml_data, method = extract_from_pdf(data)
        if not xml_data:
            xml_data, method = extract_from_text(data)
    else:
        xml_data = uploaded_file.read()
        method = "přímý soubor"

    if xml_data:
        st.success(f"✅ ISDOC extrahován metodou: {method}")
        try:
            rules = json.loads(rules_path.read_text())
            errors, values = validate_xml(xml_data, rules)
            if errors:
                st.error("❌ Faktura nesplňuje požadavky:")
                for e in errors:
                    st.markdown(f"- {e}")
            else:
                st.success("✅ Faktura splňuje všechny požadavky.")
            st.markdown("---")
            st.markdown("### 📋 Výpis hodnot:")
            for k, v in values.items():
                st.markdown(f"**{k}**: {v}")
        except Exception as e:
            st.error(f"Chyba při načítání pravidel: {e}")
    else:
        st.error("❌ Nepodařilo se extrahovat ISDOC.")
