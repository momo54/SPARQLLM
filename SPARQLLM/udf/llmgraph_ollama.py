
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
import rdflib.plugins.sparql.operators as operators

from urllib.parse import urlencode,quote

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

import SPARQLLM.udf.funcSE
import SPARQLLM.udf.uri2text
from SPARQLLM.udf.SPARQLLM import store

from SPARQLLM.config import ConfigSingleton
import logging

import requests
# Define the API endpoint
#api_url = "http://localhost:11434/api/generate"
api_url = ""

from rdflib import URIRef
from urllib.parse import urlparse

def is_valid_uri(uri):
    parsed_uri = urlparse(str(uri))
    # Check if the URI has a valid scheme and netloc
    return all([parsed_uri.scheme, parsed_uri.netloc])

def clean_invalid_uris(graph):
    to_remove = []
    
    for s, p, o in graph:
        # Check each term for URI validity
        if (isinstance(s, URIRef) and not is_valid_uri(s)) or \
           (isinstance(p, URIRef) and not is_valid_uri(p)) or \
           (isinstance(o, URIRef) and isinstance(o, URIRef) and not is_valid_uri(o)):
            to_remove.append((s, p, o))
    
    # Remove invalid triples
    for triple in to_remove:
        graph.remove(triple)


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

    api_url = config.config['Requests']['SLM-OLLAMA-URL']
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])
    model = config.config['Requests']['SLM-OLLAMA-MODEL']

    assert api_url != "", "OLLAMA API URL not set in config.ini"
    assert model != "", "OLLAMA Model not set in config.ini"
    assert timeout > 0, "OLLAMA Timeout not defined nor positive"
    assert prompt != "", "Prompt is empty"
    assert isinstance(uri, URIRef), "URI is not a URIRef"
    assert store is not None, "Store is not defined"
    assert is_valid_uri(uri), "URI is not valid"


    logging.info(f"LLMGRAPH_OLLAMA  uri: {uri}")
    logging.debug(f"LLMGRAPH_OLLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>, API: {api_url}, Timeout: {timeout}, Model: {model}")

    #print(f"LLMGRAPH_OLLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>")

    if not isinstance(uri,URIRef) :
        raise ValueError("LLMGRAPH_OLLAMA 2nd Argument should be an URI")


    if not is_valid_uri(uri):
        logging.debug("LLMGRAPH_OLLAMA : URI not valid  {uri}")
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
            logging.debug(f"LLMGRAPH_OLLAMA: {result['response']}")
        else:
            logging.debug(f"LLMGRAPH_OLLAMA: Error: {response.status_code}")
            return graph_uri 
    except requests.exceptions.RequestException as e:
        logging.debug(f"LLMGRAPH_OLLAMA: Error: {e}")
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
            logging.debug(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")
    except Exception as e:
        print(f"Error in parsing JSON-LD: {e}")

    return graph_uri 

# OLLAMA server should be running
# run with : python -m SPARQLLM.udf.llmgraph_ollama
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    config = ConfigSingleton(config_file='config.ini')

    # # Access the dictionary of custom functions
    # custom_functions = operators._CUSTOM_FUNCTIONS

    # # Display the registered custom functions
    # for uri, (func, _) in custom_functions.items():
    #     print(f"Function URI: {uri}")
    #     print(f"Function Implementation: {func}")
    #     print()

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

    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}") 
    print() 
