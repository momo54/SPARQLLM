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


@pytest.fixture(scope="module")
def setup_config():
    """
    Setup function to initialize the ConfigSingleton with an in-memory config.
    This ensures a clean configuration for testing.
    """
    # Création d'un objet ConfigParser en mémoire
    ConfigSingleton.reset_instance()
    reset_store()
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case sensitivity for option names
    config['Associations'] = {
        'SLM-SEARCH': 'SPARQLLM.udf.search_faiss.search_faiss'    
    }
    config['Requests'] = {
        'SLM-FAISS-DBDIR': './data/faiss_store',
        'SLM-FAISS-MODEL': 'nomic-embed-text'    
    }

    # Instanciation de la configuration
    config_instance = ConfigSingleton(config_obj=config)
    config_instance.print_all_values()

    return config_instance  # Retourne l'instance pour une éventuelle utilisation dans les tests



@pytest.mark.skipif(not os.path.exists("./data/faiss_store"), reason="Faiss Index dir './data/faiss_store' not found.")
def test_sparql_faiss_function(setup_config: ConfigSingleton):
    """
    Test that the SPARQL function correctly processes Woosh index.
    """
    query_str = """
    PREFIX ex: <http://example.org/>

    SELECT ?capital ?uri ?score WHERE {
    BIND(ex:Paris AS ?capital)
    BIND(ex:SLM-SEARCH("cinema screening paris", ?capital, 5) AS ?segraph).
        GRAPH ?segraph {
            ?capital ex:is_aligned_with ?bn .
            ?bn ex:has_chunk ?chunk .
            ?bn ex:has_source ?uri .
            ?bn ex:has_score ?score .
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
    # # pytest --log-cli-level=DEBUG tests/test_faiss.py
    pytest.main([sys.argv[0]])
