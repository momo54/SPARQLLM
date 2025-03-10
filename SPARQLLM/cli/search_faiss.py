import os
import faiss
import requests
import json
import numpy as np
import click

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

# 📌 FAISS Search Function
@click.command()
@click.option('--faiss-dir', default="./data/faiss_store", help="Directory where FAISS index and metadata are stored")
@click.option('--query', prompt="Enter search query", help="Search query text")
@click.option('--top-k', default=5, help="Number of top similar results to return")
@click.option('--embedding-model', default="nomic-embed-text", help="Ollama model for embeddings")
def search_faiss(faiss_dir, query, top_k, embedding_model):
    """
    Search for similar documents in FAISS with specified parameters.
    """
    # 📌 Load FAISS index from the specified directory
    faiss_index_path = os.path.join(faiss_dir, "faiss_index.bin")
    if not os.path.exists(faiss_index_path):
        print(f"❌ Error: FAISS index not found in '{faiss_dir}'. Run `index_faiss.py` first.")
        return
    
    index = faiss.read_index(faiss_index_path)

    # 📌 Load metadata from the specified directory
    json_path = os.path.join(faiss_dir, "file_mapping.json")
    if not os.path.exists(json_path):
        print(f"❌ Error: Metadata file not found in '{faiss_dir}'. Run `index_faiss.py` first.")
        return

    with open(json_path, "r") as f:
        file_mapping = json.load(f)

    # 📌 Generate embedding for the query
    query_embedding = get_embedding(query, embedding_model).reshape(1, -1)

    # 🔹 Normalize the query embedding before searching
    query_embedding = normalize(query_embedding)

    # 🔹 Search for `top_k` most relevant results
    distances, indices = index.search(query_embedding, top_k)

    # 📌 Display results
    print("\n🔍 Search Results:")
    for j, i in enumerate(indices[0]):
        if i < len(file_mapping):  # Ensure index is within bounds
            file, chunk = file_mapping[i]
            score = distances[0][j]
            print(f"- {file} (score = {score:.4f})\n   ➜ {chunk[:200]}...\n")
        else:
            print(f"⚠️ Skipping invalid index {i} in FAISS search.")

# 📌 Run search function
if __name__ == "__main__":
    search_similar()
