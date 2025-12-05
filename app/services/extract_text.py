import os

import fitz  # PyMuPDF
import mammoth


def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        doc = fitz.open(file_path)
        html = ""
        for page in doc:
            text = page.get_text("html")
            html += text
        return html

    elif ext == ".docx":
        with open(file_path, "rb") as docx_file:
            result = mammoth.convert_to_html(docx_file)
            return result.value  # this is HTML string

    elif ext == ".txt":
        html = ""
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                html += f"<p>{line.strip()}</p>"
        return html

    else:
        raise ValueError("Unsupported file type")
