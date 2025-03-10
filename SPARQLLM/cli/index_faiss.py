import os
import faiss
import requests
import json
import numpy as np
import click
from tqdm import tqdm
from langchain.text_splitter import RecursiveCharacterTextSplitter

# 📌 Function to normalize vectors for cosine similarity
def normalize(vectors):
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

# 📌 Function to get an embedding via Ollama
def get_embedding(text, model):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": model, "prompt": text}
    )
    response.raise_for_status()
    return np.array(response.json()["embedding"], dtype=np.float32)

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

    # 🔹 Collect .txt files (recursively or not)
    files = []
    if recurse:
        for root, _, filenames in os.walk(txt_folder):
            for f in filenames:
                if f.endswith(".txt"):
                    files.append(os.path.abspath(os.path.join(root, f)))
    else:
        files = [
            os.path.abspath(os.path.join(txt_folder, f))
            for f in os.listdir(txt_folder)
            if f.endswith(".txt") and os.path.isfile(os.path.join(txt_folder, f))
        ]

    if not files:
        print("⚠️ No .txt files found. Exiting.")
        return

    num_dimensions = None
    index = None
    file_mapping = []

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
            embedding = get_embedding(chunk, embedding_model)

            if index is None:
                num_dimensions = len(embedding)
                index = faiss.IndexFlatIP(num_dimensions)  # ✅ Use Cosine Similarity (Inner Product)

            # 🔹 Normalize embedding before adding to FAISS
            embedding = normalize(np.array([embedding]))
            index.add(embedding)

            file_mapping.append((file, chunk))  # Store file + chunk mapping

    # 🔹 Save FAISS index in the specified directory
    faiss_index_path = os.path.join(faiss_dir, "faiss_index.bin")
    faiss.write_index(index, faiss_index_path)

    # 🔹 Save metadata as JSON in the specified directory
    json_path = os.path.join(faiss_dir, "file_mapping.json")
    with open(json_path, "w") as f:
        json.dump(file_mapping, f)

    print(f"✅ Indexing completed. FAISS and metadata saved in '{faiss_dir}'.")

if __name__ == "__main__":
    index_txt_files()
