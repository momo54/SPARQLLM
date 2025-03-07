import configparser
import logging
import os
import sys
import pytest
from rdflib import URIRef,Dataset

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store,reset_store
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
    ConfigSingleton.reset_instance()
    reset_store()

    # Création d'un objet ConfigParser en mémoire
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case sensitivity for option names
    config['Associations'] = {
        'SLM-LLM': 'SPARQLLM.udf.llmgraph_mistral.llm_graph_mistral'    
    }
    config['Requests'] = {
        'SLM-MISTRALAI-MODEL': 'ministral-8b-latest' 
    }

    # Instanciation de la configuration
    config_instance = ConfigSingleton(config_obj=config)
    config_instance.print_all_values()

    return config_instance  # Retourne l'instance pour une éventuelle utilisation dans les tests


def run_sparql_query():
    """
    Executes the SPARQL query using the custom function and returns the result.
    """

@pytest.mark.skipif(os.getenv("MISTRAL_API_KEY") is None, reason="MISTRAL_API_KEY environment variable is set.")
def test_mistral_graph_function(setup_config):
    """
    Test that the mistral calling is working.
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
    result= store.query(query_str)
    print_result_as_table(result)

    # Ensure result is not empty
    assert result is not None, "SPARQL query returned None"

    # Convert result to a list for assertion checks
    rows = list(result)

    # Ensure that some rows are returned
    assert len(rows) > 0, "SPARQL query returned no results"


if __name__ == "__main__":
    # to see test with logs...
    # pytest --log-cli-level=DEBUG tests/test_mistral.py
    pytest.main([sys.argv[0]])
