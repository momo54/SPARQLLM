import configparser
import logging
import sys
import os
import pytest
from rdflib import URIRef

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import reset_store, store
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
        'SLM-SEARCH': 'SPARQLLM.udf.search_whoosh.searchWhoosh'    
    }
    config['Requests'] = {
        'SLM-WHOOSH-INDEX': './data/whoosh_store' 
    }

    # Instanciation de la configuration
    config_instance = ConfigSingleton(config_obj=config)
    config_instance.print_all_values()

    return config_instance  # Retourne l'instance pour une éventuelle utilisation dans les tests


@pytest.mark.skipif(not os.path.exists("./data/whoosh_store"), reason="Whoosh Index dir './data/whoosh_store' not found.")
def test_sparql_woosh_function(setup_config):
    """
    Test that the SPARQL function correctly processes Woosh index.
    """
    query_str = """
    PREFIX ex: <http://example.org/>

    SELECT ?capital ?uri ?score WHERE {
        BIND(ex:Paris AS ?capital)
        BIND(ex:SLM-SEARCH("cinema screening paris", ?capital, 5) AS ?segraph).
        GRAPH ?segraph {
            ?capital ex:search_result ?bn .
            ?bn ex:has_uri ?uri .
            ?bn ex:has_score ?score .
        }
    }
    """
    result=store.query(query_str)

    # Ensure result is not empty
    assert result is not None, "SPARQL query returned None"

    # Convert result to a list for assertion checks
    rows = list(result)

    # Ensure that some rows are returned
    assert len(rows) == 1, "SPARQL query returned no results"

def test_sparql_woosh2_function(setup_config):
    """
    just test if it can run 2 times returning values.
    """
    query_str = """
    PREFIX ex: <http://example.org/>

    SELECT ?capital ?uri ?score WHERE {
        BIND(ex:Paris AS ?capital)
        BIND(ex:SLM-SEARCH("cinema screening paris", ?capital, 5) AS ?segraph).
        GRAPH ?segraph {
            ?capital ex:search_result ?bn .
            ?bn ex:has_uri ?uri .
            ?bn ex:has_score ?score .
        }
    }
    """
    result=store.query(query_str)

    # Ensure result is not empty
    assert result is not None, "SPARQL query returned None"

    # Convert result to a list for assertion checks
    rows = list(result)

    # Ensure that some rows are returned
    assert len(rows) == 1, "SPARQL query returned no results"


if __name__ == "__main__":
    pytest.main([sys.argv[0]])
