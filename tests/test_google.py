import configparser
import logging
import sys
import os
import pytest
from rdflib import URIRef,Dataset

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store,reset_store
from SPARQLLM.utils.utils import print_result_as_table
from rdflib.plugins.sparql.operators import register_custom_function

# Set up logging
logging.basicConfig(level=logging.DEBUG)

se_api_key = os.environ.get("GOOGLE_API_KEY")
se_cx_key = os.environ.get("GOOGLE_CX")

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
        'SLM-SEARCH': 'SPARQLLM.udf.search_google.search_google'    
    }
    config['Requests'] = {
        'SLM-CUSTOM-SEARCH-URL': 'https://customsearch.googleapis.com/customsearch/v1?cx={se_cx_key}&key={se_api_key}' 
    }

    # Instanciation de la configuration
    config_instance = ConfigSingleton(config_obj=config)
    config_instance.print_all_values()

    return config_instance  # Retourne l'instance pour une éventuelle utilisation dans les tests

@pytest.mark.skipif((os.getenv("GOOGLE_API_KEY") is None or os.environ.get("GOOGLE_CX") is None), reason="MISTRAL_API_KEY environment variable is set.")
def test_google(setup_config):
    """
    Test that the SPARQL function correctly processes with Google Search index.
    """
    query_str = """
    PREFIX ex: <http://example.org/>

    SELECT ?capital ?uri ?score WHERE {
        BIND(ex:Paris AS ?capital)
        BIND(ex:SLM-SEARCH("cinema screening paris", ?capital, 5) AS ?segraph).
        GRAPH ?segraph {
            ?capital ex:has_uri ?uri .
        }
    }
    """
    result= store.query(query_str)

    # Ensure result is not empty
    assert result is not None, "SPARQL query returned None"

    # Convert result to a list for assertion checks
    rows = list(result)

    # Ensure that some rows are returned
    assert len(rows) > 0, "SPARQL query returned no results"


if __name__ == "__main__":
    # # pytest --log-cli-level=DEBUG tests/test_google.py
    pytest.main([sys.argv[0]])
