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
        'SLM-CSV': 'SPARQLLM.udf.mycsv.slm_csv',
        'SLM-FILE': 'SPARQLLM.udf.absPath.absPath'   
    }

    # Instanciation de la configuration
    config_instance = ConfigSingleton(config_obj=config)
    config_instance.print_all_values()   
   
    return config_instance  # Retourne l'instance pour une éventuelle utilisation dans les tests

@pytest.mark.skipif(not os.path.exists("./data/results.csv"), reason="CSV file './data/results.csv' not found.")
def test_sparql_csv_function(setup_config):
    """
    Test that the SPARQL function correctly processes CSV data.
    """
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?x ?z WHERE {
        BIND(ex:SLM-FILE("./data/results.csv") AS ?value)
        BIND(ex:SLM-CSV(?value) AS ?g)
        graph ?g {
            ?x <http://example.org/city> ?z .
        }
    } limit 10
    """
    result = store.query(query_str)

    # Ensure result is not empty
    assert result is not None, "SPARQL query returned None"

    # Convert result to a list for assertion checks
    rows = list(result)

    # Ensure that some rows are returned
    assert len(rows) > 0, "SPARQL query returned no results"


    # Debug output (optional)
    #print_result_as_table(result)


if __name__ == "__main__":
    # to see test with logs...
    # pytest --log-cli-level=DEBUG tests/test_slm_csv.py
    pytest.main([sys.argv[0]])
