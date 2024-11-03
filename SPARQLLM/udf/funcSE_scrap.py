from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key=os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key=os.environ.get("SEARCH_CX")

from bs4 import BeautifulSoup
import requests
import html
import html2text
import unidecode

import logging

from search_engines import Google

engine = Google()


# Carefull to return the good types !!
def SearchEngine(keywords):
    print(f"SE: {keywords}")
    results = engine.search(keywords,pages=1)
    links = results.links()
    return URIRef(links[0]) 

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/SE"), SearchEngine)

#  python -m SPARQLLM.udf.funcSE_scrap
if __name__ == "__main__":

    # Create a sample RDF graph
    g = Graph()

    # Add some sample data to the graph
    g.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("univ nantes", datatype=XSD.string)))  

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
    print(f"Query: {query_str}")
    result = g.query(query_str)
    for row in result:
        print(f"Result : {row}")

