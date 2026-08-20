import streamlit as st

import app_common as app
import transcribe


def _bind():
    return app.bind(st.session_state.user_id)


_bind()

st.header("NoteGPT Documents")

# Apply deferred widget updates before any keyed widgets are instantiated.
_pending = st.session_state.pop("_doc_pending", None) or {}
for key, value in _pending.items():
    st.session_state[key] = value

filter_query = st.text_input(
    "Search",
    placeholder="Match id or text…",
    key="doc_filter",
)

if st.session_state.status:
    st.markdown(st.session_state.status)

st.text_area(
    "Add",
    placeholder="Write or paste text, or import a file.",
    height=140,
    key="add_bar",
)
add_text = st.session_state.get("add_bar", "")

uploads = st.file_uploader(
    "Import files",
    type=app.upload_types(),
    accept_multiple_files=True,
    key="add_files",
)

# Auto-transcribe audio when imported via the file uploader (matches Gradio behavior).
_prev = st.session_state.get("_audio_import_names", ())
_names = tuple(
    sorted(f.name for f in (uploads or []) if transcribe.is_audio_path(f.name))
)
if _names and _names != _prev:
    _bind()
    _, audio_files = app.split_audio_uploads(uploads)
    if audio_files:
        merged, notes = app.transcribe_uploads(audio_files, add_text)
        st.session_state._doc_pending = {
            "add_bar": merged,
            "status": "\n".join(notes),
            "_audio_import_names": _names,
        }
        st.rerun()
st.session_state._audio_import_names = _names


def _on_save():
    _bind()
    status = app.add_item(
        st.session_state.get("add_bar", ""),
        st.session_state.get("add_files"),
    )
    st.session_state.status = status
    st.session_state.add_bar = ""
    if "add_files" in st.session_state:
        del st.session_state["add_files"]


st.button("Save", type="primary", key="save_add", on_click=_on_save)

audio = st.audio_input("Record or upload audio", key="audio_mic")


def _on_transcribe():
    _bind()
    audio_val = st.session_state.get("audio_mic")
    if not audio_val:
        st.session_state.status = "Record or upload audio first."
        return
    merged, note = app.transcribe_audio(audio_val, st.session_state.get("add_bar", ""))
    st.session_state.add_bar = merged
    st.session_state.status = note


st.button("Transcribe", key="transcribe_btn", on_click=_on_transcribe)

docs = app.filter_docs(filter_query)
doc_ids = app.ids(docs)
long_docs, memories = app.split_docs(docs)

picker_col, delete_col, open_col = st.columns([3, 1, 1], vertical_alignment="bottom")
with picker_col:
    selected = st.selectbox(
        "Select item",
        options=[""] + doc_ids,
        format_func=lambda x: x or "—",
        key="doc_picker",
    )
with delete_col:

    def _on_delete():
        _bind()
        st.session_state.status = app.delete_doc(st.session_state.get("doc_picker"))

    st.button("Delete", key="delete_btn", on_click=_on_delete)
with open_col:
    if st.button("Open in editor", key="open_editor"):
        st.session_state.edit_id = (st.session_state.get("doc_picker") or "").strip()
        st.session_state.editor_bootstrapped = False
        st.switch_page("app_pages/editor.py")

st.subheader("Documents")
if not long_docs:
    st.markdown("_No documents yet._")
else:
    for doc_id, text in long_docs:
        with st.expander(str(doc_id), expanded=False):
            st.markdown(text)

st.subheader("Memories")
if not memories:
    st.markdown("_No memories yet._")
else:
    for doc_id, text in memories:
        with st.expander(str(doc_id), expanded=False):
            st.markdown(text)
