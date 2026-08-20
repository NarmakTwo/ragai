import streamlit as st

import app_common as app

app.bind(st.session_state.user_id)

st.header("NoteGPT")
st.caption(
    "Ask about stored facts, or tell me something to remember. "
    "Clear the chat to start a new conversation."
)

with st.sidebar:
    st.subheader("Settings")
    provider = st.radio(
        "Provider",
        ["GROQ", "OPENROUTER"],
        index=0 if st.session_state.get("provider", "GROQ") == "GROQ" else 1,
        key="provider",
    )
    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=float(st.session_state.get("temperature", 0.7)),
        step=0.05,
        key="temperature",
    )

SUGGESTIONS = {
    "What is my favourite food?": "What is my favourite food?",
    "Remember that I drink espresso in the morning": "Remember that I drink espresso in the morning",
    "What do you already know about me?": "What do you already know about me?",
}

if st.button("Clear chat", key="clear_chat"):
    st.session_state.chat_messages = []
    st.session_state.llm = []
    st.rerun()

for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = None
if not st.session_state.chat_messages:
    selected = st.pills(
        "Try asking:",
        list(SUGGESTIONS.keys()),
        label_visibility="collapsed",
        key="chat_suggestions",
    )
    if selected:
        prompt = SUGGESTIONS[selected]

chat_in = st.chat_input("Message NoteGPT…", submit_mode="disable")
if chat_in:
    prompt = chat_in

if prompt:
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        reply, llm = app.chat_turn(
            prompt,
            st.session_state.llm,
            provider,
            temperature,
        )
        st.markdown(reply)
    st.session_state.llm = llm
    st.session_state.chat_messages.append({"role": "assistant", "content": reply})
    st.rerun()
