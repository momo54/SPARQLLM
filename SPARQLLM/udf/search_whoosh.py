from rdflib import Graph, Literal, URIRef, BNode
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
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

from whoosh.index import open_dir
from whoosh.qparser import QueryParser
from whoosh.qparser import MultifieldParser,WildcardPlugin
import hashlib

import logging
logger = logging.getLogger(__name__)

config = ConfigSingleton()
index_dir = config.config['Requests']['SLM-WHOOSH-INDEX']
if not os.path.exists(index_dir):
    raise ValueError(f"Whoosh index directory {index_dir} does not exist")
else:
    ix = open_dir(index_dir)

# Carefull to return the good types !!
def searchWhoosh(keywords,link_to,nb_results=5):
    global store

    nb_results = int(nb_results)
    logger.debug(f"keyword: {keywords},link to: {link_to}, , nb_results: {nb_results})")

    if not isinstance(link_to,URIRef) :
        raise ValueError("link_to should be an URI")
    
    graph_uri = URIRef("http://whoosh.org/"+hashlib.sha256(keywords.encode()).hexdigest())

    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri

    named_graph = store.get_context(graph_uri)

    with ix.searcher() as searcher:
        parser=MultifieldParser(["content"], ix.schema)
        parser.add_plugin(WildcardPlugin())
        query = parser.parse(keywords+"*")
        results = searcher.search(query, limit=nb_results)  # Limit to top 10 results
        
        if results:
            for i, result in enumerate(results):
                item=URIRef("file://"+result['filename'])
                logger.debug(f"item;{item} score:{result.score}")
                bn=BNode()
                named_graph.add((link_to, URIRef("http://example.org/search_result"), bn)) 
                named_graph.add((bn, URIRef("http://example.org/has_uri"), item))
                named_graph.add((bn, URIRef("http://example.org/has_score"), Literal(result.score, datatype=XSD.float)))  
    return graph_uri 



