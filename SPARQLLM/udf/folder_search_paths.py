import os
import hashlib
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import Graph, URIRef, Literal, XSD
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists, print_result_as_table
import logging
logger = logging.getLogger(__name__)


def folder_search_paths(keywords, link_to, nb_results=5):
    config = ConfigSingleton()
    wait_time = int(config.config['Requests']['SLM-SEARCH-WAIT'])
    logger.debug(f"Searching for {keywords} in folder")
    graph_uri = URIRef("http://localfolder.com/" + hashlib.sha256(keywords.encode()).hexdigest())
    if named_graph_exists(store, graph_uri):
        return graph_uri

    nb_results = int(nb_results)
    named_graph = store.get_context(graph_uri)
    folder_path = r'C:\Users\Denez\Desktop\M1\S2\TER\LocalWeb\untitled\LLM4SchemaOrg\data\WDC\Pset\pset_length'
    relevant_file_paths = []

    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if filename.endswith(".html"):
                file_path = os.path.join(root, filename)
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    if any(keyword.lower() in content.lower() for keyword in keywords):
                        relevant_file_paths.append(file_path)
    for file_path in relevant_file_paths[:nb_results]:
        logger.debug(f"Adding {file_path} to the graph")
        named_graph.add((link_to, URIRef("http://example.org/has_uri"), Literal(file_path)))
    return graph_uri


# Example usage



# run with python -m SPARQLLM.udf.folder_search_paths
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/SEGRAPH-SC"), folder_search_paths)

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("university nantes", datatype=XSD.string)))

    query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?uri
        WHERE {
            ?s ?p ?value .
            BIND(ex:SEGRAPH-SC(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value)),?s,5) AS ?graph)
                GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
        }
        """

    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)

