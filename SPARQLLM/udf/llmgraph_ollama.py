
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
import rdflib.plugins.sparql.operators as operators
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace
from rdflib import URIRef

import logging
import requests
from string import Template


import SPARQLLM.udf.funcSE
import SPARQLLM.udf.uri2text
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, is_valid_uri, clean_invalid_uris

def LLMGRAPH_OLLAMA(prompt, uri):
    """
    Processes a given prompt using the OLLAMA API and updates a named graph with the response.

    Args:
        prompt (str): The prompt to be sent to the OLLAMA API.
        uri (str): The URI of an entity to link to.

    Returns:
        URIRef: The URI of the new fresh immutable named graph.

    Raises:
        ValueError: If the second argument is not a valid URI.

    This function performs the following steps:
    1. Validates the provided URI.
    2. Constructs a payload with the prompt and model information.
    3. Sends a POST request to the OLLAMA API.
    4. Parses the JSON-LD response and updates the named graph.
    5. Adds a new triple to the named graph.
    6. Executes an insert query to link the new triple to a bag of mappings.
    7. Logs the subject, predicate, and object of each triple in the named graph.

    Note:
        The function relies on global variables and configurations defined elsewhere in the code.
    """
    global store

    logger = logging.getLogger('LLMGRAPH_OLLAMA')

    api_url = config.config['Requests']['SLM-OLLAMA-URL']
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])
    model = config.config['Requests']['SLM-OLLAMA-MODEL']

    assert api_url != "", "OLLAMA API URL not set in config.ini"
    assert model != "", "OLLAMA Model not set in config.ini"
    assert timeout > 0, "OLLAMA Timeout not defined nor positive"
    assert prompt != "", "Prompt is empty"
    assert store is not None, "Store is not defined"


    logger.info(f"uri: {uri}")
    logger.debug(f"uri: {uri}, Prompt: {prompt[:100]} <...>, API: {api_url}, Timeout: {timeout}, Model: {model}")

    #print(f"LLMGRAPH_OLLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>")

    if not isinstance(uri,URIRef) or not is_valid_uri(uri):
        logger.debug("invalid URI {uri}")
        return URIRef("http://example.org/invalid_uri")


    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

    # Set up the request payload
    payload = {
        "model": model,
        "prompt": str(prompt),
        "format": "json",
        "stream": False,
    }

    # Send the POST request
    try:
        response = requests.post(api_url, json=payload, timeout=timeout)
        if response.status_code == 200:
            result = response.json()
            logger.debug(f"{result['response']}")
        else:
            logger.debug(f"Response Error: {response.status_code}")
            return graph_uri 
    except requests.exceptions.RequestException as e:
        logger.debug(f"Request Error: {e}")
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal("Error {e}", datatype=XSD.string)))
        return graph_uri

    jsonld_data = result['response']
    try:
        named_graph.parse(data=jsonld_data, format="json-ld")
        clean_invalid_uris(named_graph)
        named_graph.add((uri, URIRef("http://example.org/has_schema_type"), Literal(5, datatype=XSD.integer)))

        #link new triple to bag of mappings
        insert_query_str = f"""
            INSERT  {{
            <{uri}> <http://example.org/has_schema_type> ?subject .}}
                WHERE {{
                    ?subject a ?type .
                }}"""
        named_graph.update(insert_query_str)

        for subj, pred, obj in named_graph:
            logger.debug(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")
    except Exception as e:
        logger.error(f"Error in parsing JSON-LD: {e}")
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal("Error {e}", datatype=XSD.string)))

    return graph_uri 

# OLLAMA server should be running
# run with : python -m SPARQLLM.udf.llmgraph_ollama
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')
    register_custom_function(URIRef("http://example.org/LLMGRAPH-OLLA"), LLMGRAPH_OLLAMA)

    # store is a global variable for SPARQLLM
    # not good, but see that later...
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13955291")))

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?s ?uri ?o  WHERE {
        {
            SELECT ?s ?uri WHERE {
                ?s ?p ?uri .
            }
        }
        BIND(ex:GETTEXT(?uri,1000) AS ?page)  
        BIND(ex:LLMGRAPH-OLLA(REPLACE("[INST]\\n return as JSON-LD  the schema.org representation of text below. Only respond with valid JSON-LD. \\n[/INST] PAGE ","PAGE",STR(?page)),?uri) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o }    
    }
    """

    # Execute the query
    result = store.query(query_str)

    # Print the result as a table
    print_result_as_table(result)