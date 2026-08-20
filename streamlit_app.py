import streamlit as st

import app_common as app

st.set_page_config(
    page_title="NoteGPT",
    page_icon=":material/note:",
    layout="centered",
    initial_sidebar_state="collapsed",
)

if "user_id" not in st.session_state:
    st.session_state.user_id = app.ensure_uid()
if "edit_id" not in st.session_state:
    st.session_state.edit_id = ""
if "status" not in st.session_state:
    st.session_state.status = ""
if "llm" not in st.session_state:
    st.session_state.llm = []
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
app.bind(st.session_state.user_id)

documents = st.Page(
    "app_pages/documents.py",
    title="Documents",
    icon=":material/description:",
    default=True,
)
editor = st.Page(
    "app_pages/editor.py",
    title="Editor",
    icon=":material/edit_note:",
)
chat = st.Page(
    "app_pages/chat.py",
    title="Chat",
    icon=":material/chat:",
)

page = st.navigation([documents, editor, chat], position="top")
page.run()
