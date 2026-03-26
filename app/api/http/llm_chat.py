"""
LLM Chat – Standalone Endpoints
These endpoints are kept for backward compatibility and standalone
document-to-LLM testing. All workspace-aware chat endpoints have been
moved to app/api/http/student_documents.py.
"""

import os
import shutil
import traceback

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from app.services.extract_text import extract_text
from app.services.llm import call_llm

router = APIRouter()

UPLOAD_DIR = "uploaded_docs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── File Upload & Text Extraction ─────────────────────────────────────────────


@router.post("/upload/", tags=["llm-chat"])
async def upload_file(file: UploadFile = File(...)):
    """Upload a PDF, DOCX, or TXT and receive its content as HTML."""
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    try:
        html = extract_text(file_path)
        return {"html": html}
    except Exception as e:
        return {"error": str(e)}


# ── Standalone Chat (no document context) ────────────────────────────────────


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


@router.post("/chat", tags=["llm-chat"])
async def chat_with_llm(payload: ChatRequest):
    """
    Stateless single-turn chat with GPT-4o.
    For document-aware, workspace-integrated chat use:
    POST /students/chat-sessions/{session_id}/messages
    """
    history = [{"role": m.role, "content": m.content} for m in payload.messages]
    try:
        reply = await call_llm(history=history)
        return {"reply": reply}
    except Exception as e:
        traceback.print_exc()
        return {"error": f"Unexpected error: {str(e)}"}
