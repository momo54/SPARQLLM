from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

import requests
import html
import html2text
import unidecode

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

import logging
logger = logging.getLogger(__name__)

# carefull, max_size is a string
def GETTEXT(uri,max_size):
    config = ConfigSingleton()
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])

    logger.debug(f"uri: {uri}, max_size: {max_size},timeout: {timeout}")    
    try:

        headers = {
            'Accept': 'text/html',
            'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
        }

        # Faire la requête HTTP pour obtenir le contenu de la page
        response = requests.get(uri,headers=headers,timeout=timeout)
        response.raise_for_status()  # Vérifie les erreurs HTTP
        if 'text/html' in response.headers['Content-Type']:

            h = html2text.HTML2Text()
            uri_text = h.handle(response.text)
            uri_text_uni= unidecode.unidecode(uri_text).strip()
            #print(f"Text: {uri_text_uni},max_size={max_size}")
            logger.debug(f"max_size={max_size}")
            max_size = int(max_size)
            return Literal(uri_text_uni[:max_size], datatype=XSD.string)
        else:
            return  Literal("No HTML content at {uri}")

    except requests.exceptions.RequestException as e:
        return  Literal("Error retreiving {uri}")

# run with : python -m SPARQLLM.udf.uri2text
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/GETTEXT"), GETTEXT)

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("https://zenodo.org/records/13957372")))  

    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?t
    WHERE {
        ?s ?p ?uri .
        BIND(ex:GETTEXT(?uri,5000) AS ?t)
    }
    """
    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)
