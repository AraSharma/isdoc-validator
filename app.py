import streamlit as st
from lxml import etree
from pathlib import Path
import fitz
import pikepdf
from PyPDF2 import PdfReader
import re
import json

st.set_page_config(page_title="ISDOC Validátor", layout="centered")
st.title("🧾 ISDOC Validátor")

choice = st.radio("Vyber společnost nebo akci:", ["TV Nova s.r.o.", "Jiná společnost (nahrát pravidla)", "Vygenerovat pravidla z faktury"])

# ===== Pomocné funkce =====
def extract_isdoc(data, filename):
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            attachments = doc.attachments()
            for fname, info in attachments.items():
                if fname.lower().endswith((".xml", ".isdoc")):
                    return info["file"], f"fitz global: {fname}"
            for page in doc:
                for f in page.get_files():
                    if f["name"].lower().endswith((".xml", ".isdoc")):
                        return f["file"], f"fitz page: {f['name']}"
    except Exception:
        pass
    try:
        with pikepdf.open("temp.pdf") as pdf:
            ef_names = pdf.Root.get('/Names', {}).get('/EmbeddedFiles', {}).get('/Names', [])
            for i in range(0, len(ef_names), 2):
                name = ef_names[i]
                fs = ef_names[i+1]
                ef = fs.get('/EF')
                if ef and '/F' in ef:
                    stream = ef['/F']
                    content = stream.read_bytes()
                    if name.lower().endswith((".xml", ".isdoc")):
                        return content, f"pikepdf: {name}"
    except Exception:
        pass
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

        for path in rules.get("optional_fields", []):
            xp = "//" + "/".join([f"ns:{p}" for p in path.split("/")])
            result = tree.xpath(xp, namespaces=ns)
            if result and hasattr(result[0], "text"):
                values[path] = result[0].text.strip()
            else:
                values[path] = "–"

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

def generate_rules(xml_data):
    rules = {"required_fields": [], "optional_fields": [], "expected_values": {}}
    try:
        root = etree.fromstring(xml_data)
        tree = etree.ElementTree(root)
        nsmap = root.nsmap.copy()
        ns = {"ns": nsmap.get(None, "")}
        for el in root.xpath(".//*", namespaces=ns):
            if not el.getchildren() and el.text and el.text.strip():
                path = tree.getpath(el).replace("/", "").replace("[1]", "").replace("Invoice", "", 1).strip()
                path_parts = [e for e in path.split("ns:") if e]
                clean_path = "/".join(path_parts)
                rules["expected_values"][clean_path] = el.text.strip()
    except Exception as e:
        st.error(f"Chyba při generování pravidel: {e}")
    return rules

# ===== Funkce podle volby =====

if choice == "Vygenerovat pravidla z faktury" and one_file:
    xml_data, method = None, None
    if one_file.name.lower().endswith(".pdf"):
        data = one_file.read()
        with open("temp.pdf", "wb") as f:
            f.write(data)
        xml_data, method = extract_isdoc(data, one_file.name)
    else:
        xml_data = one_file.read()
        method = "přímý soubor"

    if xml_data:
        st.success(f"✅ ISDOC extrahován metodou: {method}")
        generated = generate_rules(xml_data)
        st.download_button("💾 Stáhnout rules.json", json.dumps(generated, indent=2), file_name="rules_generated.json")
    else:
        st.error("❌ Nepodařilo se extrahovat ISDOC.")

elif choice != "Vygenerovat pravidla z faktury" and uploaded_file:
    xml_data, method = None, None
    if uploaded_file.name.lower().endswith(".pdf"):
        data = uploaded_file.read()
        with open("temp.pdf", "wb") as f:
            f.write(data)
        xml_data, method = extract_isdoc(data, uploaded_file.name)
    else:
        xml_data = uploaded_file.read()
        method = "přímý soubor"

    if xml_data:
        st.success(f"✅ ISDOC extrahován metodou: {method}")
        if choice == "TV Nova s.r.o.":
            try:
                rules = json.loads(Path("rules_nova.json").read_text())
            except Exception as e:
                st.error(f"Chyba při načítání pravidel: {e}")
                rules = None
        else:
            rule_file = st.file_uploader("Nahraj vlastní rules.json", type="json")
            if rule_file:
                rules = json.load(rule_file)
            else:
                rules = None

        if rules:
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
    else:
        st.error("❌ Nepodařilo se extrahovat ISDOC.")
