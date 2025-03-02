import os
import hashlib
import re
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
def retrieval_se(query,link_to, nb_result=10):
    config = ConfigSingleton()
    n = int(nb_result)
    logger.debug(f"Query: {query} - Number of results: {n}")

    # Create a unique URI for the graph
    graph_uri = URIRef(link_to)
    if named_graph_exists(store, graph_uri):
        return graph_uri

    # Load the local vector store if existing
    vector_store = FAISS.load_local(db_name, embeddings=embeddings, allow_dangerous_deserialization=True)
    chunks = vector_store.similarity_search_with_score(
        query, k=n)
    logger.debug(f"chunks ready")

    # Create a named graph
    named_graph = store.get_context(graph_uri)

    for chunk, score in chunks:
        print("========================================================================"
              "Page content: ")
        print(chunk.page_content)
        print("========================================================================")
        print("Score: ")
        print(score)
        match = re.search(r'Label: (.*?) Objectif:', query)
        if match:
            label = match.group(1)
        else:
            print("Label not found")
            label = "Label not found"
        print("Label: ",label)

        source_path = chunk.metadata['source'].replace('\\', '/').replace(' ','_')
        ku_unit = os.path.basename(source_path)
        source_uri = URIRef('file://' + source_path)
        label_score = label + ' ' + str(score) + ' ' + ku_unit
        print(label_score)
        #has_ku is for course.sparql
        if score > 0.3:
            named_graph.add((link_to, URIRef("http://example.org/has_ku"), Literal(chunk.page_content)))
            named_graph.add((link_to, URIRef("http://example.org/has_source"), source_uri))
            named_graph.add((link_to, URIRef("http://example.org/has_score"),Literal(label_score)))
            #has_uri is for retrieval_se.parql
            #named_graph.add((source_uri, URIRef("http://example.org/has_uri"), Literal(chunk.page_content)))

    logger.debug(f"Named graph created: " + str(named_graph))
    return graph_uri

if __name__ == "__main__":
    query = "Recherche Opérationnelle"
    retrieval_se(query)