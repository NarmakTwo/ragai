import os
import re
import uuid

import gradio as gr

import memory
import transcribe

_MEMORY_MAX = 200
_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".log", ".rst", ".py", ".html", ".xml"}
_UPLOAD_ICON = os.path.join(os.path.dirname(__file__), "assets", "upload.svg")


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


def _read_upload(path):
    name = getattr(path, "name", path)
    ext = os.path.splitext(str(name))[1].lower()
    if ext and ext not in _TEXT_EXTS:
        return None, f"Skipped {os.path.basename(str(name))} (not a text file)."
    with open(name, encoding="utf-8", errors="replace") as f:
        body = f.read().strip()
    if not body:
        return None, f"Skipped {os.path.basename(str(name))} (empty)."
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
        if not text or not str(text).strip():
            continue
        body = str(text).strip()
        kind = "memory" if len(body) <= _MEMORY_MAX else "document"
        doc_id = _unique_id(body, kind if fallback == "note" else fallback)
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
    merged = text if not current_text.strip() else current_text.rstrip() + "\n\n" + text
    return merged, f"Transcribed {len(text)} characters. Edit if needed, then Save."


def add_item(text, files, user_id, tick):
    bodies = []
    notes = []
    if text and text.strip():
        bodies.append(text.strip())
    if files and not isinstance(files, (list, tuple)):
        files = [files]
    for f in files or []:
        body, err = _read_upload(f)
        if err:
            notes.append(err)
        elif body:
            bodies.append(body)
    stored, uid, tick, docs, status, picker = _save_texts(bodies, user_id, tick)
    if notes:
        status = (status + "\n" if status else "") + "\n".join(notes)
    return stored, uid, tick, docs, status, picker, None, ""


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
    text = memory.get_by_id(selected) if selected else ""
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
    text = memory.get_by_id(doc_id)
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


with gr.Blocks(title="NoteGPT - Documents") as document_menu:
    stored_uid = gr.BrowserState("", storage_key="ragai_user_id", secret="ragai-memory-user")
    edit_id = gr.BrowserState("", storage_key="ragai_edit_id", secret="ragai-memory-user")
    uid_box = gr.Textbox(visible=False, show_label=False)
    tick = gr.State(0)
    catalog = gr.State([])
    gr.Markdown("## NoteGPT Documents")
    with gr.Row():
        filter_bar = gr.Textbox(label="Search", placeholder="Match id or text…")
    status = gr.Markdown()
    add_files = gr.UploadButton(
        "",
        file_count="multiple",
        type="filepath",
        size="sm",
        icon=_UPLOAD_ICON,
        file_types=[".txt", ".md", ".csv", ".json", ".log", ".rst", ".py", ".html", ".xml"],
        render=False,
    )
    add_bar = gr.Textbox(
        label="Add",
        placeholder="Write or paste text, or transcribe audio first.",
        lines=5,
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
    document_menu.launch(server_name="0.0.0.0", server_port=7860, share=True, footer_links=["settings"])
