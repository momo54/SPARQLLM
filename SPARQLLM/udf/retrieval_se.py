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
import logging
logger = logging.getLogger(__name__)

#load configuration
config = ConfigSingleton()
embedding_model=config.config['Requests']['SLM-EMBEDDING-MODEL']

# Check if the FAISS model is specified in the config file

if embedding_model is None:
    raise ValueError("No FAISS embedding model specified in the config file")
else:
    embeddings = OllamaEmbeddings(model=embedding_model)

# Verify the existence of the FAISS database
db_name = config.config['Requests']['SLM-FAISS-DBDIR']
if not os.path.exists(db_name):
    raise ValueError(f"FAISS DB directory {db_name} does not exist")

logger.debug(f"Embedding model: {embedding_model} - FAISS DB directory: {db_name}")

# we could pass the model and faiss db dir as parameters
def retrieval_se(query,link_to, nb_result=10):  
    config = ConfigSingleton()
    n = int(nb_result)
    logger.debug(f"Query: {query} - Number of results: {n}")

    # Create a unique URI for the graph
    graph_uri = URIRef(link_to)
    if named_graph_exists(store, graph_uri):
        return graph_uri
    # Extract the objective from the query using a regular expression
    match = re.search(r'Label: (.*?) Objectif:', query)
    if match:
        objectif = match.group(1)
    else:
        print("Objectif not found")
        objectif = "Objectif not found"
    # Load the local vector store if existing
    vector_store = FAISS.load_local(db_name, embeddings=embeddings, allow_dangerous_deserialization=True)
    # Perform similarity search for relevant results
    chunks = vector_store.similarity_search_with_score(
        'clustering: '+objectif, k=n)
    logger.debug(f"chunks ready")

    # Create a named graph
    named_graph = store.get_context(graph_uri)

    # Process the retrieved results from FAISS
    for chunk, score in chunks:
        logger.debug(f"Score: {score}")
        # Extract the label from the query
        match = re.search(r'Label: (.*?) Objectif:', query)
        if match:
            label = match.group(1)
        else:
            logger.debug("Label not found")
            label = "Label not found"

        # Clean and transform file paths for RDF URIs
        source_path = chunk.metadata['source'].replace('\\', '/').replace(' ','_')
        ku_unit = os.path.basename(source_path).replace('.txt','')
        source_uri = URIRef('file://' + source_path)
        key = link_to.replace('http://example.org/course/','')
        # Create a blank RDF node to store document information
        bn = BNode()
        folder_name = os.path.basename(os.path.dirname(source_uri))
        # Add RDF triples to the named graph
        named_graph.add((link_to, URIRef("http://example.org/is_aligned_with"), bn))
        named_graph.add((bn, URIRef("http://example.org/has_ku"), Literal(chunk.page_content)))
        named_graph.add((bn, URIRef("http://example.org/has_source"), Literal(ku_unit)))
        named_graph.add((bn, URIRef("http://example.org/has_score"), Literal(score,datatype=XSD.float)))
        named_graph.add((bn, URIRef("http://example.org/has_ka"), Literal(folder_name)))
        named_graph.add((bn, URIRef("http://example.org/has_key"), Literal(key)))

    logger.debug(f"Named graph created: " + str(named_graph))
    return graph_uri
#Execute script if run as a standalone program
if __name__ == "__main__":
    query = "Recherche Opérationnelle"
    retrieval_se(query)