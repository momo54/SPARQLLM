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
from urllib.parse import urlparse


from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

import logging
logger = logging.getLogger(__name__)

config = ConfigSingleton()


# carefull, max_size is a string
def readhtmlfile(path_uri,max_size=-1):
    """
        Reads an HTML file from the given URI, converts it to plain text, and returns it as an RDF Literal.

        Args:
            path_uri (str): The URI of the HTML file to read.
            max_size (int, optional): The maximum number of characters to return. If -1, returns the entire content. Defaults to -1.

        Returns:
            Literal: The plain text content of the HTML file as an RDF Literal. If an error occurs, returns an error message as an RDF Literal.
    """
    max_size = int(max_size)

    logger.debug(f"uri: {path_uri}, max_size: {max_size}")    
    try:
        with open(urlparse(path_uri).path, 'r') as file:
            data = file.read()
            h = html2text.HTML2Text()
            uri_text = h.handle(data)
            uri_text_uni= unidecode.unidecode(uri_text).strip()
            logger.debug(f"result={uri_text_uni[:max_size]}")
            if max_size > 0:
                return Literal(uri_text_uni[:max_size], datatype=XSD.string)
            else:
                return Literal(uri_text_uni, datatype=XSD.string)
    except requests.exceptions.RequestException as e:
        return  Literal("Error reading {uri}")

# run with : python -m SPARQLLM.udf.readfile
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/FILE-HTML"), readhtmlfile)


    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?t
    WHERE {
        BIND("file:///Users/molli-p/SPARQLLM/data/zenodo.html" AS ?uri)
        BIND(ex:FILE-HTML(?uri,100) AS ?t)
    }
    """
    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)
