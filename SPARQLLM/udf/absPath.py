from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

import os
import json


import logging

logger = logging.getLogger("abs")


def absPath(filePath):
    logger.debug(f"{filePath}")    
    return URIRef("file://"+os.path.abspath(filePath))



# run with python -m SPARQLLM.udf.absPath
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Create a sample RDF graph
    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/SLM-FILE"), absPath)

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?x 
    WHERE {
        BIND(ex:SLM-FILE("./data/results.csv") AS ?x)
    }
    """

    result = store.query(query_str)
    print_result_as_table(result)

