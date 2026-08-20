import streamlit as st

import app_common as app
import memory


def _bind():
    return app.bind(st.session_state.user_id)


_bind()

st.header("Editor")

docs = memory.list_documents()
doc_ids = app.ids(docs)

st.session_state.setdefault("editor_status", "")

# Deferred widget updates must run before keyed widgets are created.
_pending = st.session_state.pop("_editor_pending", None) or {}
for key, value in _pending.items():
    st.session_state[key] = value

if not st.session_state.get("editor_bootstrapped"):
    preferred = (st.session_state.get("edit_id") or "").strip()
    if preferred in doc_ids:
        st.session_state.editor_selected = preferred
        st.session_state.editor_picker = preferred
        st.session_state.editor_id_box = preferred
        st.session_state.editor_text = memory.get_by_id(preferred, touch=True) or ""
    elif doc_ids:
        st.session_state.editor_selected = doc_ids[0]
        st.session_state.editor_picker = doc_ids[0]
        st.session_state.editor_id_box = doc_ids[0]
        st.session_state.editor_text = memory.get_by_id(doc_ids[0], touch=True) or ""
    else:
        st.session_state.editor_selected = ""
        st.session_state.editor_picker = ""
        st.session_state.editor_id_box = ""
        st.session_state.editor_text = ""
    st.session_state.editor_bootstrapped = True

picker_col, new_col = st.columns([3, 1], vertical_alignment="bottom")
with picker_col:
    if st.session_state.get("editor_picker") not in ([""] + doc_ids):
        st.session_state.editor_picker = st.session_state.get("editor_selected") or ""
    picked = st.selectbox(
        "Document",
        options=[""] + doc_ids,
        format_func=lambda x: x or "—",
        key="editor_picker",
    )
with new_col:

    def _on_new():
        st.session_state.editor_selected = ""
        st.session_state.editor_picker = ""
        st.session_state.editor_id_box = ""
        st.session_state.editor_text = ""
        st.session_state.edit_id = ""
        st.session_state.editor_status = "New document."

    st.button("New", key="editor_new", on_click=_on_new)

if picked != st.session_state.get("editor_selected"):
    _bind()
    st.session_state.editor_selected = picked
    pending = {"editor_selected": picked}
    if picked:
        text = memory.get_by_id(picked, touch=True)
        if text is None:
            pending.update(
                {
                    "editor_id_box": picked,
                    "editor_text": "",
                    "editor_status": f"No document `{picked}`.",
                }
            )
        else:
            pending.update(
                {
                    "editor_id_box": picked,
                    "editor_text": text,
                    "edit_id": picked,
                    "editor_status": "",
                }
            )
    else:
        pending.update({"editor_id_box": "", "editor_text": ""})
    st.session_state._editor_pending = pending
    st.rerun()

doc_id = st.text_input("Id", placeholder="document_id", key="editor_id_box")
body = st.text_area(
    "Text",
    placeholder="Document text…",
    height=440,
    key="editor_text",
)

save_col, reload_col = st.columns(2)
with save_col:

    def _on_save():
        _bind()
        new_id, new_body, status = app.editor_save(
            st.session_state.get("editor_id_box", ""),
            st.session_state.get("editor_text", ""),
        )
        st.session_state.editor_id_box = new_id
        st.session_state.editor_text = new_body
        st.session_state.editor_selected = new_id
        st.session_state.editor_picker = new_id
        st.session_state.edit_id = new_id
        st.session_state.editor_status = status

    st.button("Save", type="primary", key="editor_save", on_click=_on_save)
with reload_col:

    def _on_reload():
        _bind()
        rid = (st.session_state.get("editor_id_box") or "").strip()
        if not rid:
            st.session_state.editor_status = "Select a document."
            return
        text = memory.get_by_id(rid, touch=True)
        if text is None:
            st.session_state.editor_status = f"No document `{rid}`."
            st.session_state.editor_text = ""
        else:
            st.session_state.editor_id_box = rid
            st.session_state.editor_text = text
            st.session_state.edit_id = rid
            st.session_state.editor_status = ""

    st.button("Reload", key="editor_reload", on_click=_on_reload)

if st.session_state.editor_status:
    st.markdown(st.session_state.editor_status)
