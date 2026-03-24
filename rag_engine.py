"""
rag_engine.py

Lightweight Retrieval-Augmented Generation (RAG) engine
for the GL Assistant project.

This implementation uses:
- knowledge files from knowledge/raw/
- Gemini embeddings over REST
- a simple file-backed local vector store in JSON

It avoids native vector DB dependencies so it works in this repo
without extra compiler toolchains.
"""

import glob
import json
import math
import os

import requests


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge", "raw")
VECTORSTORE_DIR = os.path.join(BASE_DIR, "vectorstore")
VECTORSTORE_PATH = os.path.join(VECTORSTORE_DIR, "gl_knowledge.json")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
GEMINI_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"

_vectorstore_cache = None


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cleaned = value.strip()
            if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
                cleaned = cleaned[1:-1]
            os.environ.setdefault(key.strip(), cleaned)


load_dotenv(os.path.join(BASE_DIR, ".env"))


def get_gemini_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment or .env file.")
    return api_key


def load_knowledge_files():
    """Read all markdown/text files from the knowledge directory."""
    patterns = ["*.md", "*.txt"]
    files = []

    for pattern in patterns:
        files.extend(glob.glob(os.path.join(KNOWLEDGE_DIR, pattern)))

    documents = []
    ids = []
    metadatas = []

    for idx, file_path in enumerate(sorted(files)):
        with open(file_path, "r", encoding="utf-8") as handle:
            text = handle.read().strip()

        if text:
            documents.append(text)
            ids.append(f"{os.path.basename(file_path)}_{idx}")
            metadatas.append({"source": os.path.basename(file_path)})

    return ids, documents, metadatas


def embed_text_batch(text_list, task_type="RETRIEVAL_DOCUMENT"):
    """
    Embed text strings using the Gemini embedContent REST API.
    Returns a list of vectors, one per input string.
    """
    api_key = get_gemini_api_key()
    session = requests.Session()
    session.trust_env = False
    embeddings = []

    for text in text_list:
        payload = {
            "model": f"models/{GEMINI_EMBED_MODEL}",
            "content": {
                "parts": [{"text": text}],
            },
            "taskType": task_type,
        }
        response = session.post(
            GEMINI_EMBED_URL.format(model=GEMINI_EMBED_MODEL),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        vector = (data.get("embedding") or {}).get("values")
        if not vector:
            raise RuntimeError(f"Gemini embedding response missing vector: {data}")
        embeddings.append(vector)

    return embeddings


def save_vectorstore(payload: dict) -> None:
    global _vectorstore_cache
    os.makedirs(VECTORSTORE_DIR, exist_ok=True)
    with open(VECTORSTORE_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    _vectorstore_cache = payload


def load_vectorstore() -> dict | None:
    global _vectorstore_cache
    if _vectorstore_cache is not None:
        return _vectorstore_cache
    if not os.path.exists(VECTORSTORE_PATH):
        return None
    with open(VECTORSTORE_PATH, encoding="utf-8") as handle:
        _vectorstore_cache = json.load(handle)
    return _vectorstore_cache


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if not mag_a or not mag_b:
        return 0.0
    return dot / (mag_a * mag_b)


def build_vectorstore(force_rebuild=False):
    """
    Build or rebuild the local JSON vector store.
    Safe to call at startup; skips rebuild if vectors already exist.
    """
    existing = load_vectorstore()
    if existing and not force_rebuild:
        count = len(existing.get("documents", []))
        return f"Vectorstore already initialized with {count} documents."

    ids, docs, metadatas = load_knowledge_files()
    if not docs:
        return "No knowledge files found."

    embeddings = embed_text_batch(docs, task_type="RETRIEVAL_DOCUMENT")
    payload = {
        "embedding_model": GEMINI_EMBED_MODEL,
        "documents": [
            {
                "id": doc_id,
                "text": doc_text,
                "metadata": metadata,
                "embedding": embedding,
            }
            for doc_id, doc_text, metadata, embedding in zip(ids, docs, metadatas, embeddings)
        ],
    }
    save_vectorstore(payload)
    return f"Indexed {len(docs)} knowledge documents."


def retrieve_relevant_context(query_text, top_k=3):
    """
    Run semantic search over the knowledge base and return
    the top matching text chunks.
    """
    store = load_vectorstore()
    if not store or not store.get("documents"):
        return []

    query_embedding = embed_text_batch([query_text], task_type="RETRIEVAL_QUERY")[0]
    scored = []
    for document in store["documents"]:
        score = cosine_similarity(query_embedding, document["embedding"])
        scored.append((score, document["text"]))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in scored[:top_k]]


def build_rag_context(user_query):
    """
    Return a merged context block suitable for sending into an LLM prompt.
    """
    retrieved_chunks = retrieve_relevant_context(user_query, top_k=3)
    return "\n\n".join(
        f"[Retrieved Snippet {index + 1}]\n{chunk}"
        for index, chunk in enumerate(retrieved_chunks)
    )
