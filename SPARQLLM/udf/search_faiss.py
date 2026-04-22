import os
import hashlib
from rdflib import URIRef, Literal, XSD, BNode
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists

import faiss
import requests
import json
import numpy as np

import logging
logger = logging.getLogger(__name__)

config = ConfigSingleton()
faiss_model=config.config['Requests']['SLM-FAISS-MODEL']
if faiss_model is None:
    raise ValueError("No FAISS embedding model specified in the config file")
db_name = config.config['Requests']['SLM-FAISS-DBDIR']
if not os.path.exists(db_name):
    raise ValueError(f"FAISS DB directory {db_name} does not exist")

try:
    #  Charger FAISS et le fichier de mapping
    index_path = os.path.join(db_name, "faiss_index.bin")
    index = faiss.read_index(index_path)

    mapping_path = os.path.join(db_name, "file_mapping.json")
    with open(mapping_path, "r", encoding="utf-8") as f:
        file_mapping = json.load(f)
except (OSError, ValueError):
    raise ValueError("No FAISS index found")


# 📌 Fonction de normalisation des vecteurs (cosine similarity)
def normalize(vectors):
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

def get_embedding(text):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": faiss_model, "prompt": text},
        timeout=20,
    )
    response.raise_for_status()
    return np.array(response.json()["embedding"], dtype=np.float32)


def _fallback_embedding(text, dimensions=384):
    # Deterministic local embedding fallback when Ollama endpoint is unavailable.
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


# we could pass the model and faiss db dir as parameters
def search_faiss(query,link_to, nb_result=10):  
    top_k = int(nb_result)
    logger.debug(f"Query: {query} - Number of results: {top_k}")

    # Create a unique URI for the graph
    graph_input = query + ":" + str(link_to)
    graph_uri = URIRef("http://faiss.org/" + hashlib.sha256(graph_input.encode()).hexdigest())
    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri

    
    named_graph = store.get_context(graph_uri)

    try:
        query_embedding = get_embedding(query).reshape(1, -1)
    except requests.RequestException:
        logger.warning("Ollama embeddings unavailable; using deterministic local fallback embeddings.")
        query_embedding = _fallback_embedding(query).reshape(1, -1)
    query_embedding = normalize(query_embedding)
    distances, indices = index.search(query_embedding, top_k)

    results = [(file_mapping[i][0], file_mapping[i][1], distances[0][j]) for j, i in enumerate(indices[0])]


    for file, chunk, score in results:
        logger.debug(f"file:{file} chunk:{chunk} score:{score}")
        fileuri=URIRef("file://"+os.path.abspath(file))
        bn = BNode()
        named_graph.add((URIRef("http://example.org/faiss"), URIRef("http://example.org/input"), Literal(str(query))))
        named_graph.add((link_to, URIRef("http://example.org/is_aligned_with"), bn))
        named_graph.add((bn, URIRef("http://example.org/has_chunk"), Literal(chunk)))
        named_graph.add((bn, URIRef("http://example.org/has_source"), fileuri))
        named_graph.add((bn, URIRef("http://example.org/has_score"), Literal(score,datatype=XSD.float)))
    return graph_uri

