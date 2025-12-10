import os
import sys
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from app.services.extract_text import extract_text

# Import mongo_db directly from the mongo module
mongo_module_path = Path(__file__).parent.parent.parent / "db" / "mongo.py"
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "db"))
import datetime
import shutil
import traceback
import uuid

import httpx
from mongo import mongo_db

router = APIRouter()

UPLOAD_DIR = "uploaded_docs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    try:
        html = extract_text(file_path)
        return {"html": html}
    except Exception as e:
        return {"error": str(e)}


import os

OPENAI_API_KEY = os.getenv("GITHUB_OPENAI_TOKEN")
BASE_URL = "https://models.github.ai/inference"


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


@router.post("/chat")
async def chat_with_llm(payload: ChatRequest):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "openai/gpt-4o",
        "messages": [msg.dict() for msg in payload.messages],
        "temperature": 0.7,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/chat/completions", headers=headers, json=body
            )
            response.raise_for_status()
            data = response.json()
            return {"reply": data["choices"][0]["message"]["content"]}
        except Exception as e:
            traceback.print_exc()
            return {"error": f"Unexpected error: {str(e)}"}


class ChatSessionCreate(BaseModel):
    group_id: str
    title: str = "Chat Session"
    tags: list[str] = []
    created_by: str


@router.post("/chat/session/")
async def create_chat_session(data: ChatSessionCreate):
    chat_id = str(uuid.uuid4())
    doc = {
        "chat_id": chat_id,
        "group_id": data.group_id,
        "title": data.title,
        "tags": data.tags,
        "created_by": data.created_by,
        "created_at": datetime.datetime.utcnow(),
        "updated_at": datetime.datetime.utcnow(),
    }
    await mongo_db.proposal_chat_sessions.insert_one(doc)
    return {"chat_id": chat_id}


class ChatMessageCreate(BaseModel):
    chat_session_id: str
    sender_id: str
    sender_type: str  # "student", "supervisor", "system", "llm"
    content: str
    doc_context: dict = None
    version: int = None
    metadata: dict = None


@router.post("/chat/message/")
async def add_message(data: ChatMessageCreate):
    doc = {
        "chat_session_id": data.chat_session_id,
        "sender_id": data.sender_id,
        "sender_type": data.sender_type,
        "content": data.content,
        "doc_context": data.doc_context,
        "version": data.version,
        "metadata": data.metadata,
        "created_at": datetime.datetime.utcnow(),
    }
    result = await mongo_db.proposal_chat_messages.insert_one(doc)
    return {"message_id": str(result.inserted_id)}


@router.get("/chat/messages/{chat_session_id}")
async def get_messages(chat_session_id: str, skip: int = 0, limit: int = 50):
    cursor = (
        mongo_db.proposal_chat_messages.find({"chat_session_id": chat_session_id})
        .sort("created_at", 1)
        .skip(skip)
        .limit(limit)
    )
    messages = await cursor.to_list(length=limit)
    for m in messages:
        m["_id"] = str(m["_id"])
    return {"messages": messages}
