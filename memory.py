import json, logging, os, re, subprocess, sys, threading, warnings
from contextvars import ContextVar
from functools import lru_cache
from typing import Annotated

os.environ.update(dict(HF_HUB_DISABLE_PROGRESS_BARS="1", HF_HUB_DISABLE_TELEMETRY="1", TRANSFORMERS_VERBOSITY="error", TOKENIZERS_PARALLELISM="false", TQDM_DISABLE="1", ANONYMIZED_TELEMETRY="False"))
warnings.filterwarnings("ignore"); logging.disable(logging.WARNING)

import langcodes
from dotenv import load_dotenv
from pydantic import Field
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.messages import ModelResponse, ToolCallPart
from translate import Translator

load_dotenv()
db_lock, translate_lock, translators = threading.Lock(), threading.Lock(), {}
current_user = ContextVar("user_id", default="local"); bind = current_user.set

DocId = Annotated[str, Field(min_length=1, description="Non-empty document id.")]
DocText = Annotated[str, Field(min_length=1, description="Non-empty document text.")]

@lru_cache(maxsize=1)
def load_db():
    import hashlib
    import chromadb
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

    class HashEmbed(EmbeddingFunction[Documents]):
        def __init__(self):
            pass
        def __call__(self, input: Documents) -> Embeddings:
            out = []
            for text in input:
                digest = hashlib.sha256(text.encode("utf-8")).digest()
                out.append([((digest[i % 32] / 127.5) - 1.0) for i in range(384)])
            return out

    return chromadb.PersistentClient("./chroma_data"), HashEmbed()

def collection():
    client, embedder = load_db()
    raw = f"user_{current_user.get()}"
    name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)[:63]
    return client.get_or_create_collection(name=name, embedding_function=embedder)

def resolve_language(value):
    text = str(value or "").strip()
    if not text: return None
    for fn in (lambda: langcodes.get(text.replace("_", "-")), lambda: langcodes.find(text)):
        try:
            if (tag := fn()).language and getattr(tag, "is_valid", lambda: True)(): return tag.language
        except Exception: continue
    raise ValueError(f"Unknown language: {value!r}")

def translate_text(text, to_lang):
    with translate_lock: data = translators.setdefault(to_lang, Translator(to_lang=to_lang)).provider._make_request(text)
    payload = data.get("responseData") or {}; out = payload.get("translatedText") or ""
    try: detected = resolve_language(str(payload.get("detectedLanguage") or ""))
    except ValueError: detected = None
    blob = f"{data.get('responseDetails')} {out}".upper()
    return text if detected == to_lang or "DISTINCT LANGUAGES" in blob or not out else out

def get_by_id(doc_id):
    with db_lock: result = collection().get(ids=[doc_id], include=["documents"])
    return result["documents"][0] if result["ids"] else None

def get_document(
    question: Annotated[str, Field(min_length=1, description="Non-empty search query against stored documents.")],
    language: Annotated[str, Field(description="Translate hits into this language (name or code). Use empty string to keep originals.")] = "",
    max_results: Annotated[int, Field(ge=1, le=50, description="How many hits to return. Integer from 1 to 50. Default 10. Never use 0 or negative.")] = 10,
) -> dict:
    """Search memory by relevance. Requires a non-empty question and max_results between 1 and 50."""
    question = str(question or "").strip()
    if not question: return {"error": "question must be a non-empty string"}
    try: n = int(max_results)
    except (TypeError, ValueError): return {"error": "max_results must be an integer from 1 to 50"}
    if n < 1 or n > 50: return {"error": "max_results must be an integer from 1 to 50"}
    try: to_lang = resolve_language(language)
    except ValueError as e: return {"error": str(e)}
    with db_lock: result = collection().query(query_texts=[question], n_results=n)
    return {"language": to_lang or "", "hits": [{"id": i, "document": translate_text(d, to_lang) if to_lang else d, "distance": dist} for i, d, dist in zip(result["ids"][0], result["documents"][0], result["distances"][0])]}

def _write(kind, id, document=""):
    id = str(id or "").strip()
    if not id: return {"error": "id must be a non-empty string"}
    if kind != "delete":
        document = str(document or "")
        if not document.strip(): return {"error": "document must be a non-empty string"}
    old = get_by_id(id)
    if kind == "new" and old is not None: return {"error": f"document already exists: {id}"}
    if kind != "new" and old is None: return {"error": f"document not found: {id}"}
    with db_lock:
        col = collection()
        if kind == "new": col.add(ids=[id], documents=[document])
        elif kind == "delete": col.delete(ids=[id]); return {"ok": True, "id": id, "deleted": True}
        else: document = document if kind == "overwrite" else old + document; col.update(ids=[id], documents=[document])
    return {"ok": True, "id": id, "document": document}

def new_document(id: DocId, document: DocText) -> dict:
    """Create a document. Fails if id already exists. Both id and document must be non-empty."""
    return _write("new", id, document)

def overwrite_document(id: DocId, document: DocText) -> dict:
    """Replace an existing document's full text. Fails if id is missing. Both id and document must be non-empty."""
    return _write("overwrite", id, document)

def append_document(id: DocId, document: DocText) -> dict:
    """Append non-empty text onto an existing document. Fails if id is missing."""
    return _write("append", id, document)

def delete_document(id: DocId) -> dict:
    """Delete a document by id. Fails if id is missing. id must be non-empty."""
    return _write("delete", id)

agent = Agent(
    instructions=(
        "You manage the user's document memory with tools. "
        "When the user asks you to remember, save, store, or note a fact, call new_document immediately with a short snake_case id and the fact as document text. "
        "Do not only search when they asked you to remember. "
        "When they ask what you know or about a fact, call get_document. "
        "Do not overwrite or delete without permission. "
        "Tool rules: never pass an empty question; max_results must be 1-50; never pass empty id or document. "
        "To list broadly, get_document with question \"everything\" and max_results 50. "
        "Never write fake tool XML like <function=...>; only use real tool calls."
    ),
    tools=[get_document, new_document, overwrite_document, append_document, delete_document],
)

def list_documents():
    with db_lock: stored = collection().get(include=["documents"])
    return list(zip(stored["ids"], stored["documents"] or []))

_TOOLS = {
    "get_document": get_document,
    "new_document": new_document,
    "overwrite_document": overwrite_document,
    "append_document": append_document,
    "delete_document": delete_document,
}
_FAKE_TOOL = re.compile(r"<function=(\w+)>\s*(\{.*?\})\s*</function>", re.S)
_VERBS = dict(
    get_document=("querying memory", "question"),
    new_document=("creating document", "id"),
    overwrite_document=("overwriting document", "id"),
    append_document=("appending to document", "id"),
    delete_document=("deleting document", "id"),
)

def _run_fake_tools(output):
    """Some Groq models dump tool calls as plain text XML. Execute those locally."""
    traces, results = [], []
    for name, raw in _FAKE_TOOL.findall(output):
        fn = _TOOLS.get(name)
        if not fn:
            continue
        try:
            args = json.loads(raw.replace("“", '"').replace("”", '"').replace("’", "'"))
        except json.JSONDecodeError:
            results.append({"error": f"could not parse args for {name}"})
            continue
        if not isinstance(args, dict):
            results.append({"error": f"args for {name} must be an object"})
            continue
        out = fn(**args)
        results.append(out)
        verb = _VERBS.get(name)
        traces.append(f"{verb[0]} {args.get(verb[1])!r}" if verb else f"calling {name}")
    return traces, results

_REMEMBER = re.compile(
    r"^\s*(?:please\s+)?(?:remember|save|store|note)(?:\s+that)?\s*[:,]?\s*(.+)$",
    re.I | re.S,
)

def _slug(text, fallback="note"):
    parts = re.findall(r"[a-z0-9]+", text.lower())
    return ("_".join(parts[:6]) or fallback)[:48]

def run_turn(history, prompt, provider, temperature=0.7):
    history = history or []
    # Remember/save intents: write locally first so we never wait on a stuck model call.
    if m := _REMEMBER.match(prompt or ""):
        fact = m.group(1).strip()
        if fact:
            doc_id = _slug(fact)
            saved = new_document(doc_id, fact)
            if not saved.get("ok") and "already exists" in str(saved.get("error", "")):
                saved = overwrite_document(doc_id, fact)
                verb = "overwriting document"
            else:
                verb = "creating document"
            if saved.get("ok"):
                return "Got it — saved.", history, [f"{verb} {doc_id!r}"]
            return f"Couldn't save that: {saved.get('error')}", history, []

    provider = provider if provider in ("GROQ", "OPENROUTER") else "GROQ"
    model = f"{provider.lower()}:{os.getenv(f'{provider}_MODEL')}"
    try:
        temp = float(temperature)
    except (TypeError, ValueError):
        temp = 0.7
    temp = max(0.0, min(2.0, temp))
    result = agent.run_sync(
        prompt,
        message_history=history,
        model=model,
        model_settings=ModelSettings(temperature=temp),
    )
    output = result.output or ""
    traces = [
        f"{v[0]} {p.args_as_dict().get(v[1])!r}" if (v := _VERBS.get(p.tool_name)) else f"calling {p.tool_name}"
        for m in result.new_messages()
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart)
    ]
    if "<function=" in output:
        fake_traces, tool_results = _run_fake_tools(output)
        traces.extend(fake_traces)
        if tool_results:
            oks = [r for r in tool_results if isinstance(r, dict) and r.get("ok")]
            errs = [r for r in tool_results if isinstance(r, dict) and r.get("error")]
            hits = [r for r in tool_results if isinstance(r, dict) and "hits" in r]
            if hits and not oks:
                lines = [f"- {h['id']}: {h['document']}" for r in hits for h in r.get("hits") or []]
                output = "Here's what I found:\n" + ("\n".join(lines) if lines else "(nothing stored yet)")
            elif oks and not errs:
                output = "Got it — saved."
            elif errs and not oks:
                output = "Couldn't save that: " + "; ".join(e["error"] for e in errs)
            else:
                output = str(tool_results)
    return output, result.all_messages(), traces

if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, __file__.replace("memory.py", "gradio_app.py"), *sys.argv[1:]]))
