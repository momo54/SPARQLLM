import os
import hashlib
import re
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import Graph, URIRef, Literal, XSD, BNode
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists, print_result_as_table

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

try :
    #  Charger FAISS et le fichier de mapping
    #index_path = os.path.join(db_name, "index.faiss")
    #index = faiss.read_index(index_path)
    index = FAISS.load_local(db_name, embeddings=OLLAMA_MODEL, allow_dangerous_deserialization=True)

    #mapping_path = os.path.join(db_name, "file_mapping.ttl")
    #with open(mapping_path, "r") as f:
    #    file_mapping = json.load(f)
except:
    raise ValueError("No FAISS index found")


# 📌 Fonction de normalisation des vecteurs (cosine similarity)
def normalize(vectors):
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

def get_embedding(text):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": faiss_model, "prompt": text}
    )
    response.raise_for_status()
    return np.array(response.json()["embedding"], dtype=np.float32)


# we could pass the model and faiss db dir as parameters
def search_faiss(query,link_to, nb_result=10):  
    top_k = int(nb_result)
    logger.debug(f"Query: {query} - Number of results: {top_k}")

    # Create a unique URI for the graph
    graph_uri = URIRef(link_to)
    if named_graph_exists(store, graph_uri):
        return graph_uri
    
    named_graph = store.get_context(graph_uri)

    query_embedding = get_embedding(query).reshape(1, -1)
    query_embedding = normalize(query_embedding)
    distances, indices = index.search(query_embedding, top_k)

    #results = [(file_mapping[i][0], file_mapping[i][1], distances[0][j]) for j, i in enumerate(indices[0])]
    results = index.similarity_search_with_score(
        'clustering: ' + query_embedding, k=top_k)

    for file, chunk, score in results:
        logger.debug(f"file:{file} chunk:{chunk} score:{score}")
        fileuri=URIRef("file://"+os.path.abspath(file))
        bn = BNode()
        named_graph.add((link_to, URIRef("http://example.org/is_aligned_with"), bn))
        named_graph.add((bn, URIRef("http://example.org/has_chunk"), Literal(chunk)))
        named_graph.add((bn, URIRef("http://example.org/has_source"), fileuri))
        named_graph.add((bn, URIRef("http://example.org/has_score"), Literal(score,datatype=XSD.float)))
    return graph_uri

