
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
import rdflib.plugins.sparql.operators as operators
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace
from rdflib import URIRef

import requests
from string import Template


import bs4
from SPARQLLM.udf.uri2text import GETTEXT
from SPARQLLM.udf.readfile import readhtmlfile

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, is_valid_uri, clean_invalid_uris

import logging
logger = logging.getLogger(__name__)

def llmollama_text(prompt):
    global store

    config = ConfigSingleton()
    api_url = config.config['Requests']['SLM-OLLAMA-URL']
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])
    model = config.config['Requests']['SLM-OLLAMA-MODEL']

    assert api_url != "", "OLLAMA API URL not set in config.ini"
    assert model != "", "OLLAMA Model not set in config.ini"
    assert timeout > 0, "OLLAMA Timeout not defined nor positive"
    assert prompt != "", "Prompt is empty"
    assert store is not None, "Store is not defined"
    logger.debug("\n =============================================================")
    logger.debug(f"Prompt: {prompt[:300]} <...>, API: {api_url}, Timeout: {timeout}, Model: {model}")
    logger.debug("\n =============================================================")
    #print(f"LLMGRAPH_OLLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>")


    # Set up the request payload
    payload = {
        "model": model,
        "prompt": str(prompt),
        "stream": False,
    }

    # Send the POST request
    try:
        response = requests.post(api_url, json=payload, timeout=timeout)
        if response.status_code == 200:
            print("===================================================")
            print(f"Response: {response.text['response']}")
            result = response.text['response']
            logger.debug(f"{result['response']}")
        else:
            logger.debug(f"Response Error: {response.status_code}")
            return Literal(f"error: {response.reason}")
    except requests.exceptions.RequestException as e:
        logger.debug(f"Request Error: {e}")
        return Literal(f"error: {e}")
    print("===================================================")
    logger.debug(f"Result: {result}")
    print("================================================")

    return Literal(result)

# OLLAMA server should be running
# run with : python -m SPARQLLM.udf.llmgraph_ollama
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    register_custom_function(URIRef("http://example.org/LLMGRAPH-OLLA"), LLMGRAPH_OLLAMA)


    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?o ?p ?x  WHERE {
        BIND(\"\"\"
            A MusicComposition Example. The following JSON-LD models
            the composition A Day in the Life by Lennon and McCartney,
            regardless of who performs or records the song.
         \"\"\" AS ?page)  
        BIND(ex:LLMGRAPH-OLLA(CONCAT(\"\"\"
            [INST]\\n return as JSON-LD  the schema.org representation of text below. 
            Only respond with valid JSON-LD. \\n[/INST]\"\"\",
            STR(?page)),<http://example.org/myentity>) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o . 
                    ?o a <http://schema.org/Person> .
                    ?o ?p ?x}    
    }
    """

    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)