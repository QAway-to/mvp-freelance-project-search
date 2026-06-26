"""Read project attachments and turn them into text for the КП prompt.

Kwork attachments require auth to download (anonymous returns an HTML gate), so
we download through the rate-limited, challenge-aware Kwork request with cookies.
Text documents (docx/pdf/txt) are parsed locally — cheap, no OOM risk. Images
are read by Gemini vision (DeepSeek, our КП model, has no vision).
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.request

from config import config
from utils.logger import log_agent_action

_MAX_FILES = int(os.getenv("ATTACH_MAX_FILES", "3"))
_MAX_BYTES = int(os.getenv("ATTACH_MAX_BYTES", str(5 * 1024 * 1024)))  # skip files > 5MB
_MAX_CHARS_PER_FILE = int(os.getenv("ATTACH_MAX_CHARS", "4000"))
_GEMINI_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")

_IMG_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp"}


def _ext(fname: str) -> str:
    fname = fname or ""
    return fname.rsplit(".", 1)[-1].lower() if "." in fname else ""


def _docx_text(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text and p.text.strip())


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:20])


def _gemini_read_image(data: bytes, mime: str) -> str:
    if not config.GEMINI_API_KEY:
        log_agent_action("Attachments", "GEMINI_API_KEY not set — cannot read image attachment", level="WARNING")
        return ""
    body = {
        "contents": [{"parts": [
            {"text": "Это вложение к заданию с фриланс-биржи. Извлеки весь текст с "
                     "изображения и, если это ТЗ/макет, кратко изложи требования. "
                     "Ответь только по-русски, без вступлений."},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}},
        ]}]
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{_GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}")
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
        return resp["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log_agent_action("Attachments", f"❌ Gemini vision failed: {e}", level="ERROR")
        return ""


def extract_attachments_text(files: list[dict]) -> str:
    """Download up to _MAX_FILES attachments and return their extracted text.

    Synchronous (download + parse + vision are blocking) — call via
    asyncio.to_thread from async code. Returns "" if nothing usable.
    """
    specs = [f for f in (files or []) if (f or {}).get("url")][:_MAX_FILES]
    if not specs:
        return ""

    # Kwork serves files only to a real authenticated browser, so download them
    # with Selenium (one Chrome session for all files), then read the bytes.
    from utils.selenium_download import download_attachments
    blobs = download_attachments(specs)  # {fname: bytes}
    if not blobs:
        log_agent_action("Attachments", "⏭️ no attachments downloaded — generating КП without them")
        return ""

    parts: list[str] = []
    for f in specs:
        fname = (f or {}).get("fname") or "файл"
        data = blobs.get(fname)
        if not data:
            continue
        if len(data) > _MAX_BYTES:
            log_agent_action("Attachments", f"⚠️ «{fname}» too large ({len(data)} bytes) — skipping", level="WARNING")
            continue
        ext = _ext(fname)
        try:
            if ext in _IMG_EXT:
                text = _gemini_read_image(data, _IMG_EXT[ext])
            elif ext == "docx":
                text = _docx_text(data)
            elif ext == "pdf":
                text = _pdf_text(data)
            elif ext in ("txt", "md", "csv"):
                text = data.decode("utf-8", "ignore")
            else:
                text = ""
        except Exception as e:
            log_agent_action("Attachments", f"❌ failed to read {fname}: {e}", level="ERROR")
            text = ""
        text = (text or "").strip()[:_MAX_CHARS_PER_FILE]
        if text:
            parts.append(f"--- Вложение «{fname}» ---\n{text}")
            log_agent_action("Attachments", f"✅ read «{fname}» ({len(text)} chars)")
        else:
            log_agent_action("Attachments", f"⏭️ «{fname}» yielded no text — skipping", level="WARNING")
    return "\n\n".join(parts)
