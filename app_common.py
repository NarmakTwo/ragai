"""Shared helpers for the Streamlit NoteGPT UI."""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from functools import lru_cache

from markitdown import (
    FileConversionException,
    MarkItDown,
    MissingDependencyException,
    UnsupportedFormatException,
)

import memory
import transcribe

_MEMORY_MAX = 200
_UPLOAD_EXTS = [
    "txt",
    "text",
    "md",
    "markdown",
    "json",
    "jsonl",
    "csv",
    "html",
    "htm",
    "xml",
    "rss",
    "atom",
    "log",
    "rst",
    "py",
    "docx",
    "pdf",
    "pptx",
    "xlsx",
    "xls",
    "epub",
    "ipynb",
    "msg",
    "zip",
    "jpg",
    "jpeg",
    "png",
    "wav",
    "mp3",
    "m4a",
    "mp4",
    "webm",
    "ogg",
    "flac",
    "mpeg",
    "mpga",
]


def upload_types():
    return list(_UPLOAD_EXTS)


def ensure_uid(user_id: str | None = None) -> str:
    return (user_id or "").strip() or uuid.uuid4().hex


def bind(user_id: str | None = None) -> str:
    user_id = ensure_uid(user_id)
    memory.bind(user_id)
    return user_id


def slug(text, fallback="note"):
    parts = re.findall(r"[a-z0-9]+", (text or "").lower())
    return ("_".join(parts[:6]) or fallback)[:48]


def unique_id(text, fallback):
    base = slug(text, fallback)
    if memory.get_by_id(base) is None:
        return base
    return f"{base}_{uuid.uuid4().hex[:6]}"


@lru_cache(maxsize=1)
def _markitdown():
    return MarkItDown()


def persist_upload(uploaded) -> str:
    """Write an UploadedFile (or similar) to a temp path and return it."""
    name = getattr(uploaded, "name", None) or "upload.bin"
    suffix = os.path.splitext(name)[1] or ".bin"
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as out:
        if hasattr(uploaded, "getvalue"):
            out.write(uploaded.getvalue())
        else:
            out.write(uploaded.read())
    return path


def file_path(path) -> str:
    return str(getattr(path, "name", path) or "")


def file_list(files):
    if not files:
        return []
    if not isinstance(files, (list, tuple)):
        return [files]
    return list(files)


def split_audio_uploads(files):
    docs, audio_files = [], []
    for f in file_list(files):
        name = file_path(f) if not hasattr(f, "name") else f.name
        path = f if isinstance(f, str) else None
        check = path or name
        (audio_files if transcribe.is_audio_path(check) else docs).append(f)
    return docs, audio_files


def read_upload(path_or_file):
    if hasattr(path_or_file, "getvalue"):
        path = persist_upload(path_or_file)
        basename = getattr(path_or_file, "name", None) or os.path.basename(path)
        cleanup = True
    else:
        path = file_path(path_or_file)
        basename = os.path.basename(path)
        cleanup = False
    body, err = None, None
    try:
        result = _markitdown().convert_local(path)
        body = (result.markdown or "").strip()
    except UnsupportedFormatException:
        err = f"Skipped {basename} (unsupported format)."
    except MissingDependencyException:
        err = f"Skipped {basename} (missing converter dependency)."
    except FileConversionException:
        err = f"Skipped {basename} (could not convert)."
    except Exception as e:
        err = f"Skipped {basename}: {e}"
    finally:
        if cleanup:
            try:
                os.unlink(path)
            except OSError:
                pass
    if err:
        return None, err
    if not body:
        return None, f"Skipped {basename} (empty)."
    return body, None

def split_docs(docs):
    items = []
    for row in docs or []:
        if isinstance(row, dict):
            items.append((row.get("id"), row.get("document") or row.get("text") or ""))
        else:
            items.append((row[0], row[1]))
    memories = [(i, t) for i, t in items if t is not None and len(t) <= _MEMORY_MAX]
    long_docs = [(i, t) for i, t in items if t is not None and len(t) > _MEMORY_MAX]
    return long_docs, memories


def ids(docs):
    return [row[0] if not isinstance(row, dict) else row.get("id") for row in (docs or [])]


def filter_docs(query: str):
    query = (query or "").strip().lower()
    docs = memory.list_documents()
    if query:
        docs = [(i, t) for i, t in docs if query in i.lower() or query in t.lower()]
    return docs


def save_texts(texts, fallback="note"):
    notes = []
    saved = []
    for text in texts:
        if isinstance(text, tuple):
            text, hint = text
        else:
            hint = fallback
        if not text or not str(text).strip():
            continue
        body = str(text).strip()
        kind = "memory" if len(body) <= _MEMORY_MAX else "document"
        source = hint if hint and hint != "note" else body
        doc_id = unique_id(source, kind if fallback == "note" else fallback)
        out = memory.new_document(doc_id, body)
        if out.get("ok"):
            saved.append(f"`{doc_id}` ({kind})")
        else:
            notes.append(out.get("error") or f"Could not save {doc_id}.")
    if not saved and not notes:
        notes.append("Paste some text or upload a file first.")
    status = ("Saved " + ", ".join(saved) if saved else "") + (
        ("\n" if saved and notes else "") + "\n".join(notes) if notes else ""
    )
    return status


def transcribe_audio(audio_path_or_file, current_text=""):
    current_text = current_text or ""
    cleanup = False
    path = audio_path_or_file
    if hasattr(audio_path_or_file, "getvalue"):
        path = persist_upload(audio_path_or_file)
        cleanup = True
    try:
        text = transcribe.transcribe_audio(path)
    except transcribe.TranscribeError as e:
        return current_text, str(e)
    except Exception as e:
        return current_text, f"Transcription failed: {e}"
    finally:
        if cleanup:
            try:
                os.unlink(path)
            except OSError:
                pass
    if text and text in current_text:
        return current_text, f"Transcribed {len(text)} characters. Edit if needed, then Save."
    merged = text if not current_text.strip() else current_text.rstrip() + "\n\n" + text
    return merged, f"Transcribed {len(text)} characters. Edit if needed, then Save."


def transcribe_uploads(audio_files, current_text=""):
    merged = current_text or ""
    notes = []
    for f in audio_files:
        merged, note = transcribe_audio(f, merged)
        notes.append(note)
    return merged, notes


def add_item(text, files):
    bodies = []
    notes = []
    docs, audio_files = split_audio_uploads(files)
    if audio_files:
        text, extra = transcribe_uploads(audio_files, text)
        notes.extend(extra)
    if text and text.strip():
        bodies.append((text.strip(), "note"))
    for f in docs:
        body, err = read_upload(f)
        if err:
            notes.append(err)
        elif body:
            name = getattr(f, "name", None) or file_path(f)
            stem = os.path.splitext(os.path.basename(name))[0]
            bodies.append((body, stem or "document"))
    status = save_texts(bodies)
    if notes:
        status = (status + "\n" if status else "") + "\n".join(notes)
    return status


def delete_doc(doc_id):
    doc_id = str(doc_id or "").strip()
    if not doc_id:
        return "Select an item to delete."
    out = memory.delete_document(doc_id)
    return f"Deleted `{doc_id}`." if out.get("ok") else (out.get("error") or "Could not delete.")


def editor_save(doc_id, text):
    doc_id = str(doc_id or "").strip() or slug(text, "document")
    text = (text or "").strip()
    if not doc_id:
        return doc_id, text, "Id is required."
    if not text:
        return doc_id, text, "Text is required."
    if memory.get_by_id(doc_id) is None:
        out = memory.new_document(doc_id, text)
        verb = "Created"
    else:
        out = memory.overwrite_document(doc_id, text)
        verb = "Saved"
    if not out.get("ok"):
        return doc_id, text, out.get("error") or "Could not save."
    return doc_id, text, f"{verb} `{doc_id}`."


def chat_turn(message, llm, provider, temperature):
    try:
        reply, llm, traces = memory.run_turn(
            llm or [], message, provider or "GROQ", temperature=temperature
        )
    except Exception as e:
        return f"Could not complete that turn: {e}", llm or []
    if traces:
        reply = "\n".join(f"_{line}_" for line in traces) + (
            "\n\n" + (reply or "") if reply else ""
        )
    return reply or "", llm
