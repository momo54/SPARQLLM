from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

from bs4 import BeautifulSoup
import requests
import html
import html2text
import unidecode


from search_engines import Google
engine = Google()

import logging
logger = logging.getLogger(__name__)


# Carefull to return the good types !!
def SearchEngine(keywords):
    config = ConfigSingleton()
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])

    logger.debug(f"keywords: {keywords}, timeout: {timeout}")
    results = engine.search(keywords,pages=1)
    links = results.links()
    return URIRef(links[0]) 


#  python -m SPARQLLM.udf.funcSE_scrap
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/SE"), SearchEngine)
    
    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("univ nantes", datatype=XSD.string)))  

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:SE(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value))) AS ?result)
    }
    """

    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)

