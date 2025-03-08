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

import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD

import traceback

import logging

logger = logging.getLogger(__name__)


def slm_csv(file_url):
    logger.debug(f"{file_url}, {str(file_url)}")    
    try:
        df = pd.read_csv(str(file_url))

        # Initialize the RDF graph
        n = Namespace("http://example.org/")

        # Define a generic class for the CSV records
        Record = URIRef(n.Record)

        graph_uri=URIRef(file_url)
        if  named_graph_exists(store, graph_uri):
            logger.debug(f"Graph {graph_uri} already exists (good)")
            return None
        else:
            named_graph = store.get_context(graph_uri)

        # Create properties for each column
        properties = {col: URIRef(n[col]) for col in df.columns}

        # Add triples to the graph
        for index, row in df.iterrows():
            # Create a unique URI for each record
            record_uri = URIRef(n[f"record_{index}"])
            named_graph.add((record_uri, RDF.type, Record))
            
            # Add properties for each column
            for col, value in row.items():
                if pd.notna(value):  # Check for non-null values
                    # Determine the appropriate datatype
                    if isinstance(value, int):
                        datatype = XSD.integer
                    elif isinstance(value, float):
                        datatype = XSD.float
                    else:
                        datatype = XSD.string
                    named_graph.add((record_uri, properties[col], Literal(value, datatype=datatype)))
        return graph_uri

    except Exception as e:
        logger.error(f"Error reading file: {e}")
        traceback.print_exc()
        return None

