import os
import hashlib
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import Graph, URIRef, Literal, XSD
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists, print_result_as_table
import logging
logger = logging.getLogger(__name__)

embeddings = OllamaEmbeddings(
    model="jina/jina-embeddings-v2-small-en"
)
db_name = "knowledge_vector_store"
def retrieval_se(query,link_to, nb_result=5):
    config = ConfigSingleton()
    n = int(nb_result)
    logger.debug(f"Query: {query} - Number of results: {n}")

    # Create a unique URI for the graph
    graph_uri = URIRef(link_to)
    if named_graph_exists(store, graph_uri):
        return graph_uri

    # Load the local vector store if existing
    vector_store = FAISS.load_local(db_name, embeddings=embeddings, allow_dangerous_deserialization=True)
    retriever = vector_store.as_retriever(search_type="mmr",
                                          search_kwargs={'k': n,
                                                         'fetch_k': 100,
                                                         'lambda_mult': 1})
    chunks = retriever.invoke(query)
    logger.debug(f"chunks ready")

    # Create a named graph
    named_graph = store.get_context(graph_uri)

    for chunk in chunks:
        print("========================================================================"
              "Page content: ")
        print(chunk.page_content)

        source_path = chunk.metadata['source'].replace('\\', '/').replace(' ','_')
        source_uri = URIRef('file://' + source_path)
        named_graph.add((link_to, URIRef("http://example.org/has_ku"), Literal(chunk.page_content)))
        named_graph.add((link_to, URIRef("http://example.org/has_source"), source_uri))

    logger.debug(f"Named graph created: " + str(named_graph))
    return graph_uri

if __name__ == "__main__":
    query = "Recherche Opérationnelle"
    retrieval_se(query)