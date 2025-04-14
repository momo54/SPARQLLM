
import hashlib
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
from SPARQLLM.utils.utils import named_graph_exists, print_result_as_table, is_valid_uri, clean_invalid_uris

from pyshacl import validate




import logging
logger = logging.getLogger(__name__)

def LLMGRAPH_OLLAMA(prompt, uri, triplets_size=4, model=None):
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
    triplets_size = int(triplets_size)
    global store

    config = ConfigSingleton()
    api_url = config.config['Requests']['SLM-OLLAMA-URL']
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])
    if model is None:
        model = config.config['Requests']['SLM-OLLAMA-MODEL']
    
    logger.debug(f"model: {model}")

    assert api_url != "", "OLLAMA API URL not set in config.ini"
    assert model != "", "OLLAMA Model not set in config.ini"
    assert timeout > 0, "OLLAMA Timeout not defined nor positive"
    assert prompt != "", "Prompt is empty"
    assert store is not None, "Store is not defined"
    logger.debug(f"uri: {uri}, Prompt: {prompt[:100]} <...>, API: {api_url}, Timeout: {timeout}, Model: {model}")
    graph_name = model + " " + prompt + ":"+str(uri)
    graph_uri = URIRef("http://ollama.org/"+hashlib.sha256(graph_name.encode()).hexdigest())
    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri
    else:
        named_graph = store.get_context(graph_uri)

    # Set up the request payload
    payload = {
        "model": model,
        "prompt": str(prompt),
        "format": "json",
        "stream": False,
    }

    # Send the POST request
    # Modification in the loop
    i = 1
    while i <= 3 and not validate_named_graph(named_graph):
        named_graph = store.get_context(graph_uri)
        logger.debug(f"Attempt {i} to send request to OLLAMA")
        print(f"Attempt {i} to send request to OLLAMA")
        logger.debug(f"named_graph size: {len(named_graph)}")
        i += 1
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

            # link new triple to bag of mappings
            insert_query_str = f"""
                INSERT  {{
                <{uri}> <http://example.org/has_schema_type> ?subject .}}
                    WHERE {{
                        ?subject a ?type .
                    }}"""
            named_graph.update(insert_query_str)
            named_graph.add((uri, URIRef("http://example.org/has_model"), Literal(model, datatype=XSD.string)))
            # for subj, pred, obj in named_graph:
            #     logger.debug(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")
        except Exception as e:
            logger.error(f"Error in parsing JSON-LD: {e}")
            named_graph.add((uri, URIRef("http://example.org/has_error"), Literal("Error {e}", datatype=XSD.string)))
    if validate_named_graph(named_graph):
        logger.debug(f"Graph {graph_uri} is valid")
        return graph_uri
    else:
        logger.debug(f"Graph {graph_uri} is NOT valid")
        named_graph = store.get_context(graph_uri)
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal("Graph is NOT valid", datatype=XSD.string)))
        return graph_uri



def validate_named_graph(named_graph):
    """
    Validate the named graph against Report type constraints manually.

    Args:
        named_graph (Graph): The RDFLib graph to validate.

    Returns:
        bool: True if the graph is valid, False otherwise.
    """
    logger.debug(f"Validating named graph manually")

    # Vérifier la présence d'un sujet de type Report
    report_query = """
    PREFIX schema: <http://schema.org/>
    SELECT ?report WHERE {
        ?report a schema:Report .
    }
    """
    reports = list(named_graph.query(report_query))
    if not reports:
        logger.debug("No subjects of type schema:Report found.")
        return False
    
    if len(reports) > 1:
        logger.debug(f"Too many schema:Report instances: {len(reports)}")
        return False
    
    report = reports[0]['report']
    logger.debug(f"Report found: {report}")
    # Vérifier la présence de schema:answer
    answer_query = f"""
    PREFIX schema: <http://schema.org/>
    ASK {{
        ?report schema:answer ?answer .
    }}
    """
    if not named_graph.query(answer_query).askAnswer:
        logger.debug("No schema:answer property found.")
        return False
    
    # Vérifier la présence de schema:explain
    explain_query = f"""
    PREFIX schema: <http://schema.org/>
    ASK {{
        ?report schema:explain ?explain .
    }}
    """
    if not named_graph.query(explain_query).askAnswer:
        logger.debug("No schema:explain property found.")
        return False
    
    # Tout est valide
    logger.debug("Named graph is valid.")
    return True

    try:
        # Charger les contraintes SHACL dans un graphe RDF
        shacl_graph = Graph()
        shacl_graph.parse(data=shacl_constraints, format="turtle")

        # Valider le graphe nommé
        conforms, _, _ = validate(named_graph, shacl_graph=shacl_graph)
        logger.debug(f"Validation result: {conforms}")
        return conforms
    except Exception as e:
        logger.error(f"SHACL validation error: {e}", exc_info=True)
        return False


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