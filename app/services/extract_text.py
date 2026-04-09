import asyncio
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


_CLEAN_PDF_SYSTEM = (
    "You receive HTML produced by extracting text from a PDF. "
    "Clean it for a rich-text editor: fix broken line breaks and duplicate spans, "
    "normalize headings and lists where obvious, and remove PDF extraction noise. "
    "Preserve meaning and reading order. Output ONLY an HTML fragment (no markdown, no preamble)."
)


async def process_document_import_async(
    file_path: str, *, clean_pdf: bool = True
) -> str:
    """
    Extract document HTML off the event loop; optionally LLM-clean PDF extraction noise.
    """
    html = await asyncio.to_thread(extract_text, file_path)
    ext = os.path.splitext(file_path)[1].lower()
    if not clean_pdf or ext != ".pdf":
        return html

    from app.services.llm import call_llm

    cleaned = await call_llm(
        history=[{"role": "user", "content": html}],
        system_extra=_CLEAN_PDF_SYSTEM,
        model_choice="gpt-4o",
    )
    return cleaned.strip()
