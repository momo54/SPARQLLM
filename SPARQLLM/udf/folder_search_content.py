import os
import hashlib
from rdflib import Graph, URIRef, Literal
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import print_result_as_table
from rdflib.plugins.sparql.operators import register_custom_function

import logging
logger = logging.getLogger(__name__)

def folder_search_content(filepath):
    relevant_files_content = []
    logger.debug(f"Searching for content in {filepath}")
    with open(filepath, 'r', encoding='utf-8') as file:
        content = file.read()
        relevant_files_content.append((filepath, content))
        logger.debug("Content found: ", content)
    return relevant_files_content

# run with python -m SPARQLLM.udf.folder_search_content
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')
    filepath = r"C:\Users\Denez\Desktop\M1\S2\TER\LocalWeb\untitled\LLM4SchemaOrg\data\WDC\Pset\pset_length\stratum_0\corpus\1b8ba337d560f8fef91fb58e0696dfda.html"

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/FOLDER-SC"), folder_search_content)

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal(filepath)))
    query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?content
        WHERE {
        ?s ?p ?value .
        FILTER(?s = <http://example.org/subject1>)
        BIND(ex:FOLDER-SC(?value) AS ?content)
    }
        """

    result = store.query(query_str)
    print_result_as_table(result)

