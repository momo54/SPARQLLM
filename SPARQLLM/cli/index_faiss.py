import os
import faiss
import requests
import json
import numpy as np
import hashlib
import click
from tqdm import tqdm
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except Exception:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

# 📌 Function to normalize vectors for cosine similarity
def normalize(vectors):
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

# 📌 Function to get an embedding via Ollama
def get_embedding(text, model):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": model, "prompt": text},
        timeout=3,
    )
    response.raise_for_status()
    return np.array(response.json()["embedding"], dtype=np.float32)


def fallback_embedding(text, dimensions=384):
    # Deterministic local embedding fallback when Ollama is unavailable.
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    state = np.frombuffer(seed, dtype=np.uint32).copy()
    values = np.empty(dimensions, dtype=np.float32)
    for i in range(dimensions):
        x = state[i % len(state)]
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= (x >> 17)
        x ^= (x << 5) & 0xFFFFFFFF
        state[i % len(state)] = x
        values[i] = ((x % 10000) / 5000.0) - 1.0
    return values


def _collect_txt_files(txt_folder, recurse):
    if recurse:
        files = []
        for root, _, filenames in os.walk(txt_folder):
            for name in filenames:
                if name.endswith(".txt"):
                    files.append(os.path.abspath(os.path.join(root, name)))
        return files

    return [
        os.path.abspath(os.path.join(txt_folder, name))
        for name in os.listdir(txt_folder)
        if name.endswith(".txt") and os.path.isfile(os.path.join(txt_folder, name))
    ]


def _probe_embedding_backend(embedding_model):
    try:
        _ = get_embedding("healthcheck", embedding_model)
        return False
    except requests.RequestException:
        click.echo("Warning: Ollama embeddings unavailable; using deterministic local fallback embeddings.")
        return True


def _embed_chunk(chunk, embedding_model, using_fallback):
    if using_fallback:
        return fallback_embedding(chunk), using_fallback

    try:
        return get_embedding(chunk, embedding_model), using_fallback
    except requests.RequestException:
        click.echo("Warning: Ollama embeddings became unavailable; switching to deterministic local fallback embeddings.")
        return fallback_embedding(chunk), True


def _append_chunk_to_index(index, num_dimensions, embedding, file_mapping, file_path, chunk_text):
    if index is None:
        num_dimensions = len(embedding)
        index = faiss.IndexFlatIP(num_dimensions)

    index.add(normalize(np.array([embedding])))
    file_mapping.append((file_path, chunk_text))
    return index, num_dimensions


def _save_index_artifacts(index, file_mapping, faiss_dir):
    faiss_index_path = os.path.join(faiss_dir, "faiss_index.bin")
    faiss.write_index(index, faiss_index_path)

    json_path = os.path.join(faiss_dir, "file_mapping.json")
    with open(json_path, "w", encoding="utf-8") as out_file:
        json.dump(file_mapping, out_file)

# 📌 FAISS Indexing Function
@click.command()
@click.option('--txt-folder', default="./data/events", help="Path to the folder containing .txt files")
@click.option('--faiss-dir', default="./data/faiss_store", help="Directory to store FAISS index and metadata")
@click.option('--chunk-size', default=512, help="Size of text chunks")
@click.option('--chunk-overlap', default=50, help="Number of overlapping tokens between chunks")
@click.option('--embedding-model', default="nomic-embed-text", help="Ollama model for embeddings")
@click.option('--recurse/--no-recurse', default=True, help="Enable or disable recursive file search")
def index_faiss(txt_folder, faiss_dir, chunk_size, chunk_overlap, embedding_model, recurse):
    """
    Index text files (optionally including subdirectories) into FAISS with specified parameters.
    """
    os.makedirs(faiss_dir, exist_ok=True)  # Ensure directory exists

    files = _collect_txt_files(txt_folder, recurse)

    if not files:
        print("⚠️ No .txt files found. Exiting.")
        return

    num_dimensions = None
    index = None
    file_mapping = []
    using_fallback = False

    using_fallback = _probe_embedding_backend(embedding_model)

    # 📌 Text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", ".", "?", "!", "\n", " "]
    )

    for file in tqdm(files, desc="Indexing TXT files"):
        with open(file, "r", encoding="utf-8") as f:
            text = f.read()

        # Split text into smaller chunks
        chunks = text_splitter.split_text(text)

        for chunk in chunks:
            embedding, using_fallback = _embed_chunk(chunk, embedding_model, using_fallback)
            index, num_dimensions = _append_chunk_to_index(index, num_dimensions, embedding, file_mapping, file, chunk)

    _save_index_artifacts(index, file_mapping, faiss_dir)

    mode = "fallback" if using_fallback else "ollama"
    print(f"✅ Indexing completed ({mode} embeddings). FAISS and metadata saved in '{faiss_dir}'.")

if __name__ == "__main__":
    index_faiss()
