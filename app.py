import streamlit as st
from lxml import etree
from pathlib import Path
import fitz
import pikepdf
from PyPDF2 import PdfReader
import re

st.set_page_config(page_title="ISDOC Validátor", layout="centered")
st.title("🧾 ISDOC Validátor (PDF / ISDOC / XML)")

uploaded_file = st.file_uploader("Nahraj fakturu:", type=["pdf", "xml", "isdoc"])
xsd_path = Path("ISDOC_2013.xsd")

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
            messages.append(f"❌ Validace XSD selhala: {e}")
        messages.append("---\n📋 Výpis polí z faktury:")
        for el in tree.xpath("//*"):
            tag = el.tag.split("}")[-1]
            text = (el.text or "").strip()
            if text:
                messages.append(f"**{tag}:** {text}")
    except Exception as e:
        messages.append(f"🚫 Chyba při zpracování XML: {e}")
    return messages

if uploaded_file:
    st.markdown("### 🔍 Zpracovávám soubor...")
    xml_data = None
    origin = None

    if uploaded_file.name.lower().endswith(".pdf"):
        file_bytes = uploaded_file.read()
        with open("temp.pdf", "wb") as f:
            f.write(file_bytes)

        methods = [
            lambda x: extract_with_fitz(file_bytes),
            lambda x: extract_from_text(file_bytes),
            lambda x: extract_from_binary(file_bytes),
            lambda x: extract_from_xrefs(file_bytes),
            lambda x: extract_with_pikepdf("temp.pdf"),
            lambda x: extract_with_pypdf2("temp.pdf"),
        ]

        for method in methods:
            xml_data, origin = method("temp.pdf")
            if xml_data:
                break

        if xml_data:
            st.success(f"ISDOC nalezen metodou: {origin}")
            for line in validate_and_parse(xml_data):
                st.markdown(line)
        else:
            st.error("❌ ISDOC se nepodařilo najít v PDF žádnou metodou.")

    else:
        xml_data = uploaded_file.read()
        for line in validate_and_parse(xml_data):
            st.markdown(line)
