import uuid

import gradio as gr

import memory


def _uid():
    return uuid.uuid4().hex


def chat(message, _history, provider, temperature, user_id, llm):
    memory.bind(user_id)
    try:
        reply, llm, traces = memory.run_turn(
            llm or [], message, provider or "GROQ", temperature=temperature
        )
    except Exception as e:
        return f"Could not complete that turn: {e}", llm or []
    if traces:
        reply = "\n".join(f"_{line}_" for line in traces) + ("\n\n" + (reply or "") if reply else "")
    return reply or "", llm


def docs_md(user_id):
    memory.bind(user_id)
    docs = memory.list_documents()
    if not docs:
        return "No stored documents yet."
    return f"**{len(docs)} stored documents**\n\n" + "\n\n".join(f"**{i}**\n{t}" for i, t in docs)


def clear_llm():
    return []


with gr.Blocks(title="Memory") as demo:
    user_id = gr.State(_uid)
    llm = gr.State([])
    with gr.Sidebar():
        gr.Markdown("## Memory")
        provider = gr.Radio(["GROQ", "OPENROUTER"], value="GROQ", label="Provider")
        temperature = gr.Slider(0, 2, value=0.7, step=0.05, label="Temperature")
        docs = gr.Markdown("Click refresh to list documents for this session.")
        refresh = gr.Button("Refresh documents")
        refresh.click(docs_md, inputs=user_id, outputs=docs)
    chat_ui = gr.ChatInterface(
        chat,
        title="Memory",
        description="Ask about stored facts, or tell me something to remember. Clear the chat to start a new conversation.",
        examples=[
            ["What is my favourite food?"],
            ["Remember that I drink espresso in the morning"],
            ["What do you already know about me?"],
        ],
        additional_inputs=[provider, temperature, user_id, llm],
        additional_outputs=[llm],
        autofocus=True,
    )
    chat_ui.chatbot.clear(clear_llm, outputs=llm)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, show_error=True)
