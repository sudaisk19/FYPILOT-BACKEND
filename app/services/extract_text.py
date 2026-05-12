import asyncio
import logging
import os

import fitz  # PyMuPDF
import mammoth

logger = logging.getLogger(__name__)

# Above this size, PDF "clean" via LLM is skipped (context limits / timeouts).
_MAX_PDF_HTML_CHARS_FOR_LLM_CLEAN = 80_000


def _read_plaintext_file(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise ValueError(f"Could not read PDF: {exc}") from exc
        html = ""
        for page in doc:
            text = page.get_text("html")
            html += text
        return html

    elif ext == ".docx":
        try:
            with open(file_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
            return result.value  # this is HTML string
        except Exception as exc:
            raise ValueError(f"Could not read DOCX: {exc}") from exc

    elif ext == ".txt":
        text = _read_plaintext_file(file_path)
        html = ""
        for line in text.splitlines():
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

    Cleaning is skipped when HTML is very large (API limits) or when the LLM call
    fails (missing keys, HTTP errors); raw extraction is returned instead.
    """
    html = await asyncio.to_thread(extract_text, file_path)
    ext = os.path.splitext(file_path)[1].lower()
    if not clean_pdf or ext != ".pdf":
        return html

    if len(html) > _MAX_PDF_HTML_CHARS_FOR_LLM_CLEAN:
        logger.info(
            "Skipping PDF LLM clean: extracted HTML length %s exceeds limit %s",
            len(html),
            _MAX_PDF_HTML_CHARS_FOR_LLM_CLEAN,
        )
        return html

    from app.services.llm import call_llm

    try:
        cleaned = await call_llm(
            history=[{"role": "user", "content": html}],
            system_extra=_CLEAN_PDF_SYSTEM,
            model_choice="gpt-4o",
        )
        return cleaned.strip()
    except Exception as exc:
        logger.warning(
            "PDF LLM clean failed; returning raw extraction: %s",
            exc,
            exc_info=True,
        )
        return html
