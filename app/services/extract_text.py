import os

import fitz  # PyMuPDF
import mammoth
from fastapi.concurrency import run_in_threadpool

from app.services.llm import call_llm


def extract_text(file_path: str) -> str:
    """Synchronous raw extraction without AI cleaning."""
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


async def extract_and_clean_pdf_text_async(file_path: str) -> str:
    """Extract text from PDF using PyMuPDF blocks and send to LLM for clean HTML generation."""

    def _extract_blocks():
        doc = fitz.open(file_path)
        raw_text = ""
        for page in doc:
            text = page.get_text("blocks")
            for b in text:
                if b[6] == 0:  # 0 indicates text
                    raw_text += b[4] + "\n"
        return raw_text

    raw_text = await run_in_threadpool(_extract_blocks)

    system_prompt = (
        "You are an academic document formatter. Here is text extracted from a PDF template. "
        "Restructure it into clean, well-formatted HTML using proper <h1>, <h2>, <p>, and <ul> tags. "
        "Remove page numbers, watermarks, and whitespace noise. Preserve all meaningful content. "
        "Return ONLY the requested HTML, do not wrap in markdown codeblocks like ```html."
    )

    history = [{"role": "user", "content": f"RAW TEXT:\n{raw_text}"}]

    try:
        reply = await call_llm(
            history=history, system_extra=system_prompt, model_choice="gpt-4o"
        )
        # Cleanup any accidental markdown backticks
        reply = reply.strip()
        if reply.startswith("```html"):
            reply = reply[7:]
        if reply.startswith("```"):
            reply = reply[3:]
        if reply.endswith("```"):
            reply = reply[:-3]
        return reply.strip()
    except Exception as e:
        print(f"Warning: LLM pdf cleaning failed, falling back to raw extraction: {e}")
        return await run_in_threadpool(extract_text, file_path)


async def process_document_import_async(file_path: str, clean_pdf: bool = True) -> str:
    """Async wrapper that decides whether to clean PDF via LLM or just run raw extract."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf" and clean_pdf:
        return await extract_and_clean_pdf_text_async(file_path)
    else:
        return await run_in_threadpool(extract_text, file_path)
