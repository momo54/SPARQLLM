import configparser
import logging
import os
import sys
import pytest
from rdflib import URIRef
import requests

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import print_result_as_table
from rdflib.plugins.sparql.operators import register_custom_function

# Set up logging
logging.basicConfig(level=logging.DEBUG)

@pytest.fixture(scope="module")
def setup_config():
    """
    Setup function to initialize the ConfigSingleton with an in-memory config.
    This ensures a clean configuration for testing.
    """
    # Création d'un objet ConfigParser en mémoire
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case sensitivity for option names
    config['Associations'] = {
        'SLM-LLM': 'SPARQLLM.udf.llmgraph_ollama.LLMGRAPH_OLLAMA'    
    }
    config['Requests'] = {
        'SLM-OLLAMA-MODEL': 'llama3.1:latest',
        'SLM-OLLAMA-URL' : 'http://localhost:11434/api/generate',
        'SLM-TIMEOUT' : '120'
        
    }

    # Instanciation de la configuration
    config_instance = ConfigSingleton(config_obj=config)
    config_instance.print_all_values()
    
    # Check if the Ollama server is runnîing
    ollama_url = config['Requests']['SLM-OLLAMA-URL'].rsplit('/', 1)[0] + '/tags'
    try:
        response = requests.get(ollama_url)
        if response.status_code != 200:
            pytest.skip(f"Ollama server not running at {ollama_url}")
    except requests.ConnectionError:
        pytest.skip(f"Ollama server not running at {ollama_url}")

    return config_instance  # Retourne l'instance pour une éventuelle utilisation dans les tests


def run_sparql_query():
    """
    Executes the SPARQL query using the custom function and returns the result.
    """
    query_str = """
        PREFIX ex: <http://example.org/>

        SELECT ?capital ?p ?o WHERE {
            BIND(<ex:Paris> AS ?capital)
            BIND("Generate in JSON-LD a schema.org event describing a theater representation in paris. Answer only with JSON-LD (No ```json)." AS ?prompt)
            BIND(ex:SLM-LLM(?prompt, ?capital) AS ?g).
            GRAPH ?g {
                ?capital ?p ?o
            }
        }
    """
    return store.query(query_str)

def test_ollama_graph(setup_config):
    """
    Test that the mistral calling is working.
    """
    result = run_sparql_query()
    print_result_as_table(result)

    # Ensure result is not empty
    assert result is not None, "SPARQL query returned None"

    # Convert result to a list for assertion checks
    rows = list(result)

    # Ensure that some rows are returned
    assert len(rows) > 0, "SPARQL query returned no results"


if __name__ == "__main__":
    # to see test with logs...
    # pytest --log-cli-level=DEBUG tests/test_ollama.py
    pytest.main([sys.argv[0]])
