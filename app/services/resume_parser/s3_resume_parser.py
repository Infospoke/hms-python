import re
from typing import Dict, Any
from io import BytesIO
import logging
import pdfplumber
from pypdf import PdfReader
from docx import Document
import zipfile
from docx.document import Document as _Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import _Cell, Table
from docx.text.paragraph import Paragraph
import xml.etree.ElementTree as ET
import app.core.config as consts
from app.core import messages
from app.services import minio_helper as aws_helper

# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- S3 RESUME PARSER ---


class S3ResumeParser:

    def __init__(self):
        self.supported_formats = consts.SUPPORTED_FORMATS

    def parse_resume(self, file_path: str) -> Dict[str, Any]:
        if not file_path:
            return {
                "success": False,
                "error": "file_stream cannot be None",
                "file_name": file_path,
                "text": "",
                "metadata": {},
            }
        response = {}
        try:
            response = aws_helper.fetch_resume(file_path)
            if not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error"),
                    "file_path": file_path,
                    "text": "",
                    "metadata": {},
                }
            raw_text = self._extract_text(
                response.get("file_stream"), response.get("file_extension")
            )
            structured_text = self._clean_text_preserve_layout(raw_text)
            metadata = self._extract_metadata(structured_text)
            # Flag low-content resumes so scoring can produce a deterministic fallback.
            metadata["insufficient_text"] = metadata.get("word_count", 0) < 20
            metadata["file_size"] = response.get("file_size_mb")
            metadata["file_name"] = response.get("file_name")
            return {
                "success": True,
                "filename": response.get("file_name"),
                "text": structured_text,
                "metadata": metadata,
                "file_size": response.get("file_size_mb"),
                "file_type": response.get("file_extension"),
            }
        except Exception as e:
            logger.error(f"Error parsing {response.get('file_name')}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "filename": response.get("file_name"),
                "text": "",
                "metadata": {},
            }

    def extract_text(self, file_path: str) -> str:
        response = aws_helper.fetch_resume(file_path)
        if not response.get("success"):
            return {
                "success": False,
                "error": response.get("error"),
                "file_path": file_path,
                "text": "",
                "metadata": {},
            }
        raw_text = self._extract_text(
            response.get("file_stream"), response.get("file_extension")
        )
        structured_text = self._clean_text_preserve_layout(raw_text)
        return structured_text

    def _extract_text(self, file_stream: BytesIO, extension: str) -> str:
        ext = extension.lower()
        file_stream.seek(0)
        if ext == ".pdf":
            return self._extract_from_pdf(file_stream)
        elif ext in [".docx", ".doc"]:
            return self._extract_from_docx(file_stream)
        else:
            raise ValueError(messages.UNSUPPORTED_FILE_FORMAT(extension))

    def _extract_from_pdf(self, file_stream: BytesIO) -> str:
        text = self._extract_from_pdf_fallback(file_stream).strip()
        if text:
            return text

        if pdfplumber is None:
            raise ImportError(messages.PDFPLUMBER_IMPORT_ERROR)

        text_chunks = []
        try:
            file_stream.seek(0)
            with pdfplumber.open(file_stream) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text(x_tolerance=2, y_tolerance=3)
                    if not extracted:
                        extracted = page.extract_text(layout=True)
                    if extracted:
                        text_chunks.append(extracted)
        except Exception as e:
            raise Exception(messages.ERROR_READING_PDF_FILE(e))

        text = "\n".join(text_chunks).strip()
        return text

    def _extract_from_pdf_fallback(self, file_stream: BytesIO) -> str:
        try:
            file_stream.seek(0)
            reader = PdfReader(file_stream)
            pages_text = []
            for page in reader.pages:
                extracted = page.extract_text() or ""
                if extracted:
                    pages_text.append(extracted)
            return "\n".join(pages_text)
        except Exception as e:
            logger.warning(f"PDF fallback extraction failed: {e}")
        return ""

    def _extract_from_docx(self, file_stream: BytesIO) -> str:
        try:
            doc = Document(file_stream)
            full_text = []
            for element in doc.element.body:
                if isinstance(element, CT_P):
                    para = Paragraph(element, doc)
                    if para.text.strip():
                        full_text.append(para.text)
                elif isinstance(element, CT_Tbl):
                    table = Table(element, doc)
                    full_text.append("")
                    for row in table.rows:
                        row_data = []
                        for cell in row.cells:
                            clean_cell = cell.text.strip().replace("\n", " ")
                            row_data.append(clean_cell)
                        if any(row_data):
                            full_text.append("| " + " | ".join(row_data) + " |")
                    full_text.append("")
            return "\n".join(full_text)
        except Exception as e:
            logger.warning(
                f"Standard DOCX parsing failed: {e}. Retrying with XML fallback."
            )
            try:
                return self._extract_from_docx_xml_fallback(file_stream)
            except Exception as fallback_error:
                raise Exception(
                    messages.ERROR_READING_DOCX_FILE(
                        f"{e} | Fallback: {fallback_error}"
                    )
                )

    def _extract_from_docx_xml_fallback(self, file_stream: BytesIO) -> str:
        try:
            file_stream.seek(0)
            with zipfile.ZipFile(file_stream) as zf:
                xml_content = zf.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            namespace = {
                "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            }
            text_nodes = tree.findall(".//w:t", namespace)
            return "\n".join([node.text for node in text_nodes if node.text])
        except Exception as e:
            logger.error(f"XML Fallback failed: {e}")
            raise e

    def _clean_text_preserve_layout(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            clean_line = re.sub("[ \\t]+", " ", line)
            clean_line = clean_line.strip()
            cleaned_lines.append(clean_line)
        result = "\n".join(cleaned_lines)
        result = re.sub("\\n{3,}", "\n\n", result)
        return result.strip()

    def _extract_metadata(self, text: str) -> Dict[str, Any]:
        email_pattern = "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"
        phone_pattern = (
            "(\\+\\d{1,3}[-.\\s]?)?\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4}"
        )
        metadata = {
            "word_count": len(text.split()),
            "char_count": len(text),
            "has_email": bool(re.search(email_pattern, text)),
            "has_phone": bool(re.search(phone_pattern, text)),
            "has_linkedin": "linkedin" in text.lower(),
            "has_github": "github" in text.lower(),
        }
        extracted_name = self._extract_candidate_name(text)
        metadata["candidate_name"] = extracted_name
        return metadata

    def _extract_candidate_name(self, text: str) -> str:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return messages.NAME_NOT_FOUND
        first_line = lines[0]
        words = first_line.split()
        if 2 <= len(words) <= 4:
            return first_line
        if len(words) >= 2:
            return f"{words[0]} {words[1]}"
        return messages.NAME_NOT_FOUND
