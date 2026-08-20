import os
import re
import uuid
from functools import lru_cache

import gradio as gr
from markitdown import (
    FileConversionException,
    MarkItDown,
    MissingDependencyException,
    UnsupportedFormatException,
)

import memory
import transcribe

_MEMORY_MAX = 200
_THEME = gr.themes.Soft(
    primary_hue=gr.themes.Color(
        c50="#eef1fd",
        c100="#dce3fb",
        c200="#b9c7f7",
        c300="#96abf3",
        c400="#5f7eeb",
        c500="#3b60e4",
        c600="#2f4db6",
        c700="#243a89",
        c800="#19265b",
        c900="#0f1736",
        c950="#080c1c",
        name="slate_indigo",
    ),
    secondary_hue=gr.themes.Color(
        c50="#f2f0fc",
        c100="#e5e1f9",
        c200="#cbc3f3",
        c300="#b1a5ed",
        c400="#9485e8",
        c500="#7765e3",
        c600="#5f51b6",
        c700="#473d88",
        c800="#30285b",
        c900="#1c1836",
        c950="#0e0c1b",
        name="medium_slate_blue",
    ),
    neutral_hue=gr.themes.Color(
        c50="#edd3c4",
        c100="#e6c8b8",
        c200="#c8adc0",
        c300="#b094a8",
        c400="#8e7588",
        c500="#6c5a68",
        c600="#50424d",
        c700="#382e36",
        c800="#221c21",
        c900="#110e10",
        c950="#080708",
        name="powder_petal",
    ),
).set(
    body_background_fill="#edd3c4",
    body_background_fill_dark="#080708",
    background_fill_primary="#edd3c4",
    background_fill_primary_dark="#080708",
    background_fill_secondary="#c8adc0",
    background_fill_secondary_dark="#221c21",
    block_background_fill="#c8adc0",
    block_background_fill_dark="#221c21",
    block_border_color="#c8adc0",
    block_border_color_dark="#382e36",
    border_color_primary="#c8adc0",
    border_color_primary_dark="#382e36",
    button_primary_background_fill="#3b60e4",
    button_primary_background_fill_hover="#2f4db6",
    button_primary_text_color="#edd3c4",
    button_secondary_background_fill="#7765e3",
    button_secondary_background_fill_hover="#5f51b6",
    button_secondary_text_color="#edd3c4",
    input_background_fill="#edd3c4",
    input_background_fill_dark="#221c21",
    input_border_color="#c8adc0",
    input_border_color_dark="#382e36",
    body_text_color="#080708",
    body_text_color_dark="#edd3c4",
)
_UPLOAD_EXTS = [
    ".txt",
    ".text",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
    ".csv",
    ".html",
    ".htm",
    ".xml",
    ".rss",
    ".atom",
    ".log",
    ".rst",
    ".py",
    ".docx",
    ".pdf",
    ".pptx",
    ".xlsx",
    ".xls",
    ".epub",
    ".ipynb",
    ".msg",
    ".zip",
    ".jpg",
    ".jpeg",
    ".png",
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".webm",
    ".ogg",
    ".flac",
    ".mpeg",
    ".mpga",
]


def _ensure_uid(saved):
    return (saved or "").strip() or uuid.uuid4().hex


def _bind(user_id):
    user_id = _ensure_uid(user_id)
    memory.bind(user_id)
    return user_id


def _slug(text, fallback="note"):
    parts = re.findall(r"[a-z0-9]+", (text or "").lower())
    return ("_".join(parts[:6]) or fallback)[:48]


def _unique_id(text, fallback):
    base = _slug(text, fallback)
    if memory.get_by_id(base) is None:
        return base
    return f"{base}_{uuid.uuid4().hex[:6]}"


@lru_cache(maxsize=1)
def _markitdown():
    return MarkItDown()


def _file_path(path):
    return str(getattr(path, "name", path) or "")


def _file_list(files):
    if not files:
        return []
    if not isinstance(files, (list, tuple)):
        return [files]
    return list(files)


def _split_audio_uploads(files):
    docs, audio_files = [], []
    for f in _file_list(files):
        (audio_files if transcribe.is_audio_path(f) else docs).append(f)
    return docs, audio_files


def _read_upload(path):
    name = _file_path(path)
    basename = os.path.basename(name)
    try:
        result = _markitdown().convert_local(name)
        body = (result.markdown or "").strip()
    except UnsupportedFormatException:
        return None, f"Skipped {basename} (unsupported format)."
    except MissingDependencyException:
        return None, f"Skipped {basename} (missing converter dependency)."
    except FileConversionException:
        return None, f"Skipped {basename} (could not convert)."
    except Exception as e:
        return None, f"Skipped {basename}: {e}"
    if not body:
        return None, f"Skipped {basename} (empty)."
    return body, None


def _split(docs):
    items = []
    for row in docs or []:
        if isinstance(row, dict):
            items.append((row.get("id"), row.get("document") or row.get("text") or ""))
        else:
            items.append((row[0], row[1]))
    memories = [(i, t) for i, t in items if t is not None and len(t) <= _MEMORY_MAX]
    long_docs = [(i, t) for i, t in items if t is not None and len(t) > _MEMORY_MAX]
    return long_docs, memories


def _ids(docs):
    return [row[0] if not isinstance(row, dict) else row.get("id") for row in (docs or [])]


def _picker(docs):
    return gr.Dropdown(choices=_ids(docs), value=None)


def _refresh(user_id, tick, status, docs=None):
    user_id = _bind(user_id)
    if docs is None:
        docs = memory.list_documents()
    return user_id, user_id, tick + 1, docs, status, _picker(docs)


def chat(message, _history, provider, temperature, user_id, llm):
    user_id = _bind(user_id)
    try:
        reply, llm, traces = memory.run_turn(
            llm or [], message, provider or "GROQ", temperature=temperature
        )
    except Exception as e:
        return f"Could not complete that turn: {e}", llm or [], user_id
    if traces:
        reply = "\n".join(f"_{line}_" for line in traces) + ("\n\n" + (reply or "") if reply else "")
    return reply or "", llm, user_id


def boot(user_id, tick):
    return _refresh(user_id, tick, "")


def smart_search(query, user_id, tick):
    user_id = _bind(user_id)
    query = (query or "").strip()
    if not query:
        return _refresh(user_id, tick, "")
    result = memory.get_document(query, max_results=20)
    if result.get("error"):
        return _refresh(user_id, tick, result["error"], [])
    hits = result.get("hits") or []
    docs = [(h["id"], h["document"]) for h in hits]
    return _refresh(user_id, tick, "" if docs else "No matching documents.", docs)


def filter_docs(query, user_id, tick):
    user_id = _bind(user_id)
    query = (query or "").strip().lower()
    docs = memory.list_documents()
    if query:
        docs = [(i, t) for i, t in docs if query in i.lower() or query in t.lower()]
    return _refresh(user_id, tick, "" if docs else "No matching documents.", docs)


def _save_texts(texts, user_id, tick, fallback="note"):
    user_id = _bind(user_id)
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
        doc_id = _unique_id(source, kind if fallback == "note" else fallback)
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
    return _refresh(user_id, tick, status)


def on_transcribe(audio_path, current_text):
    current_text = current_text or ""
    try:
        text = transcribe.transcribe_audio(audio_path)
    except transcribe.TranscribeError as e:
        return current_text, str(e)
    except Exception as e:
        return current_text, f"Transcription failed: {e}"
    if text and text in current_text:
        return current_text, f"Transcribed {len(text)} characters. Edit if needed, then Save."
    merged = text if not current_text.strip() else current_text.rstrip() + "\n\n" + text
    return merged, f"Transcribed {len(text)} characters. Edit if needed, then Save."


def _transcribe_uploads(audio_files, current_text):
    merged = current_text or ""
    notes = []
    last_path = None
    for f in audio_files:
        last_path = _file_path(f)
        merged, note = on_transcribe(last_path, merged)
        notes.append(note)
    return merged, last_path, notes


def on_import_files(files, current_text):
    docs, audio_files = _split_audio_uploads(files)
    if not audio_files:
        return current_text, gr.update(), gr.update(), gr.update()
    merged, last_path, notes = _transcribe_uploads(audio_files, current_text)
    return merged, last_path, docs or None, "\n".join(notes)


def add_item(text, files, user_id, tick):
    bodies = []
    notes = []
    docs, audio_files = _split_audio_uploads(files)
    if audio_files:
        text, _, extra = _transcribe_uploads(audio_files, text)
        notes.extend(extra)
    if text and text.strip():
        bodies.append((text.strip(), "note"))
    for f in docs:
        body, err = _read_upload(f)
        if err:
            notes.append(err)
        elif body:
            stem = os.path.splitext(os.path.basename(_file_path(f)))[0]
            bodies.append((body, stem or "document"))
    stored, uid, tick, catalog, status, picker = _save_texts(bodies, user_id, tick)
    if notes:
        status = (status + "\n" if status else "") + "\n".join(notes)
    return stored, uid, tick, catalog, status, picker, None, ""


def delete_doc(doc_id, user_id, tick):
    user_id = _bind(user_id)
    doc_id = str(doc_id or "").strip()
    if not doc_id:
        return _refresh(user_id, tick, "Select an item to delete.")
    out = memory.delete_document(doc_id)
    status = f"Deleted `{doc_id}`." if out.get("ok") else (out.get("error") or "Could not delete.")
    return _refresh(user_id, tick, status)


def stash_edit_id(doc_id):
    return str(doc_id or "").strip()


def editor_boot(user_id, selected, request: gr.Request):
    user_id = _bind(user_id)
    query = dict(request.query_params) if request else {}
    selected = str(query.get("id") or selected or "").strip()
    docs = memory.list_documents()
    ids = _ids(docs)
    if selected not in ids:
        selected = ids[0] if ids else ""
    text = memory.get_by_id(selected, touch=True) if selected else ""
    return (
        user_id,
        user_id,
        gr.Dropdown(choices=ids, value=selected or None),
        selected,
        text or "",
        selected,
        "",
    )


def editor_load(doc_id, user_id):
    user_id = _bind(user_id)
    doc_id = str(doc_id or "").strip()
    if not doc_id:
        return user_id, "", "", "", "Select a document."
    text = memory.get_by_id(doc_id, touch=True)
    if text is None:
        return user_id, doc_id, "", doc_id, f"No document `{doc_id}`."
    return user_id, doc_id, text, doc_id, ""


def editor_new(user_id):
    user_id = _bind(user_id)
    docs = memory.list_documents()
    return gr.Dropdown(choices=_ids(docs), value=None), "", "", "", "New document."


def editor_save(doc_id, text, user_id):
    user_id = _bind(user_id)
    doc_id = str(doc_id or "").strip() or _slug(text, "document")
    text = (text or "").strip()
    if not doc_id:
        return user_id, doc_id, text, doc_id, "Id is required.", _picker(memory.list_documents())
    if not text:
        return user_id, doc_id, text, doc_id, "Text is required.", _picker(memory.list_documents())
    if memory.get_by_id(doc_id) is None:
        out = memory.new_document(doc_id, text)
        verb = "Created"
    else:
        out = memory.overwrite_document(doc_id, text)
        verb = "Saved"
    docs = memory.list_documents()
    if not out.get("ok"):
        return user_id, doc_id, text, doc_id, out.get("error") or "Could not save.", _picker(docs)
    return user_id, doc_id, text, doc_id, f"{verb} `{doc_id}`.", gr.Dropdown(choices=_ids(docs), value=doc_id)


def clear_llm():
    return []


with gr.Blocks(title="NoteGPT - Documents", theme=_THEME) as document_menu:
    stored_uid = gr.BrowserState("", storage_key="ragai_user_id", secret="ragai-memory-user")
    edit_id = gr.BrowserState("", storage_key="ragai_edit_id", secret="ragai-memory-user")
    uid_box = gr.Textbox(visible=False, show_label=False)
    tick = gr.State(0)
    catalog = gr.State([])
    gr.Markdown("## NoteGPT Documents")
    with gr.Row():
        filter_bar = gr.Textbox(label="Search", placeholder="Match id or text…")
    status = gr.Markdown()
    add_bar = gr.Textbox(
        label="Add",
        placeholder="Write or paste text, or import a file.",
        lines=5,
    )
    add_files = gr.File(
        label="Import files",
        file_count="multiple",
        type="filepath",
        file_types=_UPLOAD_EXTS,
    )
    add_btn = gr.Button("Save", variant="primary")
    audio = gr.Audio(
        sources=["microphone", "upload"],
        type="filepath",
        label="Record or upload audio",
    )
    transcribe_btn = gr.Button("Transcribe")
    with gr.Row():
        picker = gr.Dropdown(label="Select item", choices=[], interactive=True)
        delete_btn = gr.Button("Delete", variant="stop")
        open_editor_btn = gr.Button("Open in editor", link="/editor")
    gr.Markdown("### Documents")

    @gr.render(inputs=[catalog], triggers=[tick.change])
    def render_documents(docs):
        long_docs, _ = _split(docs or [])
        if not long_docs:
            gr.Markdown("_No documents yet._")
            return
        for doc_id, text in long_docs:
            with gr.Accordion(str(doc_id), open=False):
                gr.Markdown(text)

    gr.Markdown("### Memories")

    @gr.render(inputs=[catalog], triggers=[tick.change])
    def render_memories(docs):
        _, memories = _split(docs or [])
        if not memories:
            gr.Markdown("_No memories yet._")
            return
        for doc_id, text in memories:
            with gr.Accordion(str(doc_id), open=False):
                gr.Markdown(text)

    lib_out = [stored_uid, uid_box, tick, catalog, status, picker]
    document_menu.load(boot, inputs=[stored_uid, tick], outputs=lib_out)
    filter_bar.submit(filter_docs, inputs=[filter_bar, uid_box, tick], outputs=lib_out)
    transcribe_btn.click(on_transcribe, inputs=[audio, add_bar], outputs=[add_bar, status])
    add_files.change(
        on_import_files,
        inputs=[add_files, add_bar],
        outputs=[add_bar, audio, add_files, status],
    )
    add_btn.click(
        add_item,
        inputs=[add_bar, add_files, uid_box, tick],
        outputs=lib_out + [add_files, add_bar],
    )
    add_bar.submit(
        add_item,
        inputs=[add_bar, add_files, uid_box, tick],
        outputs=lib_out + [add_files, add_bar],
    )
    delete_btn.click(delete_doc, inputs=[picker, uid_box, tick], outputs=lib_out)
    picker.change(stash_edit_id, inputs=picker, outputs=edit_id)
    open_editor_btn.click(stash_edit_id, inputs=picker, outputs=edit_id)


with document_menu.route("Editor", "/editor"):
    stored_uid = gr.BrowserState("", storage_key="ragai_user_id", secret="ragai-memory-user")
    edit_id = gr.BrowserState("", storage_key="ragai_edit_id", secret="ragai-memory-user")
    uid_box = gr.Textbox(visible=False, show_label=False)
    gr.Markdown("## Editor")
    with gr.Row():
        doc_picker = gr.Dropdown(label="Document", choices=[], interactive=True, scale=3)
        new_btn = gr.Button("New", scale=1)
    id_box = gr.Textbox(label="Id", placeholder="document_id")
    body = gr.Textbox(label="Text", placeholder="Document text…", lines=22)
    with gr.Row():
        save_btn = gr.Button("Save", variant="primary")
        reload_btn = gr.Button("Reload")
    editor_status = gr.Markdown()
    document_menu.load(
        editor_boot,
        inputs=[stored_uid, edit_id],
        outputs=[stored_uid, uid_box, doc_picker, id_box, body, edit_id, editor_status],
    )
    doc_picker.change(
        editor_load,
        inputs=[doc_picker, uid_box],
        outputs=[uid_box, id_box, body, edit_id, editor_status],
    )
    reload_btn.click(
        editor_load,
        inputs=[id_box, uid_box],
        outputs=[uid_box, id_box, body, edit_id, editor_status],
    )
    new_btn.click(editor_new, inputs=uid_box, outputs=[doc_picker, id_box, body, edit_id, editor_status])
    save_btn.click(
        editor_save,
        inputs=[id_box, body, uid_box],
        outputs=[uid_box, id_box, body, edit_id, editor_status, doc_picker],
    )


with document_menu.route("Chat", "/chat"):
    user_id = gr.BrowserState("", storage_key="ragai_user_id", secret="ragai-memory-user")
    llm = gr.State([])
    document_menu.load(_ensure_uid, inputs=user_id, outputs=user_id)
    with gr.Sidebar(open=False):
        gr.Markdown("## Settings")
        provider = gr.Radio(["GROQ", "OPENROUTER"], value="GROQ", label="Provider")
        temperature = gr.Slider(0, 2, value=0.7, step=0.05, label="Temperature")
    chat_ui = gr.ChatInterface(
        chat,
        title="NoteGPT",
        description="Ask about stored facts, or tell me something to remember. Clear the chat to start a new conversation.",
        examples=[
            ["What is my favourite food?"],
            ["Remember that I drink espresso in the morning"],
            ["What do you already know about me?"],
        ],
        additional_inputs=[provider, temperature, user_id, llm],
        additional_outputs=[llm, user_id],
        autofocus=True,
    )
    chat_ui.chatbot.clear(clear_llm, outputs=llm)

if __name__ == "__main__":
    document_menu.launch(server_name="0.0.0.0", server_port=7860, share=False, footer_links=["settings"])
