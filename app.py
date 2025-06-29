import streamlit as st
from lxml import etree
from pathlib import Path
import fitz
import pikepdf
from PyPDF2 import PdfReader
import re
import json

st.set_page_config(page_title="ISDOC Validátor", layout="centered")
st.title("🧾 ISDOC Validátor (kompletní)")

uploaded_file = st.file_uploader("Nahraj fakturu:", type=["pdf", "xml", "isdoc"])
xsd_path = Path("ISDOC_2013.xsd")
rules_path = Path("rules.json")

def extract_with_fitz(pdf_bytes):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            attachments = doc.attachments()
            for fname, info in attachments.items():
                if fname.lower().endswith((".xml", ".isdoc")):
                    return info["file"], f"fitz global: {fname}"
            for page in doc:
                for f in page.get_files():
                    if f["name"].lower().endswith((".xml", ".isdoc")):
                        return f["file"], f"fitz page: {f['name']}"
    except Exception as e:
        return None, f"fitz error: {e}"
    return None, None

def extract_from_text(pdf_bytes):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            full_text = "".join(page.get_text() for page in doc)
        match = re.search(r'(<Invoice[^>]+xmlns="http://isdoc.cz/namespace/2013"[^>]*>.*?</Invoice>)', full_text, re.DOTALL)
        if match:
            return match.group(1).encode(), "fitz text"
    except Exception as e:
        return None, f"text error: {e}"
    return None, None

def extract_from_binary(pdf_bytes):
    try:
        text = pdf_bytes.decode("utf-8", errors="ignore")
        match = re.search(r'(<Invoice[^>]+xmlns="http://isdoc.cz/namespace/2013"[^>]*>.*?</Invoice>)', text, re.DOTALL)
        if match:
            return match.group(1).encode(), "binary search"
    except Exception as e:
        return None, f"binary error: {e}"
    return None, None

def extract_from_xrefs(pdf_bytes):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i in range(1, doc.xref_length()):
                try:
                    data = doc.xref_stream(i)
                    if data:
                        match = re.search(rb'(<Invoice[^>]+xmlns="http://isdoc.cz/namespace/2013"[^>]*>.*?</Invoice>)', data, re.DOTALL)
                        if match:
                            return match.group(1), f"xref {i}"
                except:
                    continue
    except Exception as e:
        return None, f"xref error: {e}"
    return None, None

def extract_with_pikepdf(pdf_path):
    try:
        with pikepdf.open(pdf_path) as pdf:
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
    except Exception as e:
        return None, f"pikepdf error: {e}"
    return None, None

def extract_with_pypdf2(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        root = reader.trailer['/Root']
        if '/Names' in root and '/EmbeddedFiles' in root['/Names']:
            files = root['/Names']['/EmbeddedFiles']['/Names']
            for i in range(0, len(files), 2):
                name = files[i]
                file_spec = files[i+1].get_object()
                ef = file_spec['/EF']
                stream = ef['/F'].get_object()
                content = stream.get_data()
                if name.lower().endswith((".xml", ".isdoc")):
                    return content, f"pypdf2: {name}"
    except Exception as e:
        return None, f"pypdf2 error: {e}"
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

if uploaded_file:
    st.markdown("### 🔍 Zpracovávám soubor...")
    xml_data, method = None, None

    if uploaded_file.name.lower().endswith(".pdf"):
        data = uploaded_file.read()
        with open("temp.pdf", "wb") as f:
            f.write(data)

        methods = [
            lambda _: extract_with_fitz(data),
            lambda _: extract_from_text(data),
            lambda _: extract_from_binary(data),
            lambda _: extract_from_xrefs(data),
            lambda _: extract_with_pikepdf("temp.pdf"),
            lambda _: extract_with_pypdf2("temp.pdf"),
        ]

        for method_fn in methods:
            xml_data, method = method_fn("temp.pdf")
            if xml_data:
                break
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
        st.error("❌ Nepodařilo se extrahovat ISDOC žádnou metodou.")
