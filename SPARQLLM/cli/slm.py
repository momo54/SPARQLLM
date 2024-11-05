#!/usr/bin/python
import click
import pprint

from rdflib.plugins.sparql.algebra import translateQuery, translateUpdate
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate
from rdflib.plugins.sparql.algebra import pprintAlgebra
from rdflib.plugins.sparql.parserutils import prettify_parsetree

from SPARQLLM.utils.explain import explain
from SPARQLLM.udf.SPARQLLM import store

import SPARQLLM.udf.funcSE 
import SPARQLLM.udf.funcLLM 
import SPARQLLM.udf.llmgraph
import SPARQLLM.udf.segraph
import SPARQLLM.udf.segraph_scrap
import SPARQLLM.udf.llmgraph_llama
import SPARQLLM.udf.funcSE_scrap
import SPARQLLM.udf.uri2text
import SPARQLLM.udf.llmgraph_ollama

import logging
import json
import configparser

from rdflib import URIRef
from rdflib.plugins.sparql.operators import register_custom_function
 
#
# [Associations]
#http://example.org/SE = SearchEngine
# http://example.org/DB = DatabaseConnector

import importlib

def configure_udf(config_file):
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case sensitivity for option names
    config.read(config_file)

    # Access the variables by section and key
    slm_timeout = config.getint('Requests', 'SLM-TIMEOUT')        # Read as integer

    associations = config['Associations']
    for uri, full_func_name in associations.items():
        module_name, func_name = full_func_name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
#        func = globals().get(func_name)
        if callable(func):
            full_uri= f"http://example.org/{uri}"
            print(f"Registering {func_name} with URI {full_uri}")
            register_custom_function(URIRef(full_uri), func)
        else:
            print(f"FUnction {func_name} NOT Collable.")

@click.command()
@click.option(
    "-q", "--query", type=click.STRING, default=None,
    help="SPARQL query to execute (passed in command-line)"
)
@click.option(
    "-f", "--file", type=click.STRING, default=None,
    help="File containing a SPARQL query to execute"
)

@click.option(
    "-c", "--config", type=click.STRING, default=None,
    help="Config File for User Defined Functions"
)


@click.option(
    "-l", "--load", type=click.STRING, default=None,
    help="RDF data file to load"
)
@click.option(
    "-fo", "--format", type=click.STRING, default="xml",
    help="Format of RDF data file"
)

@click.option('-d', '--debug', is_flag=True, help="turn on debug.")

@click.option(
    "-k", "--keep-store", type=click.STRING, default=None,
    help="File to store the RDF data collected during the query"
)



def slm_cmd(query, file, config,load,format="xml",debug=False,keep_store=None):

    query_str = ""

    if query is None and file is None:
        print("Error: you must specificy a query to execute, either with --query or --file. See explain --help for more informations.")
        exit(1)

    if file is not None:
        with open(file) as query_file:
            query_str = query_file.read()
    else:
        query_str = query

    if config is not None:
        configure_udf(config)

    if load is not None:
        store.parse(load, format=format)

    if debug:
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger('urllib3')
        logger.setLevel(logging.DEBUG)
        logging.debug("debugging activated.")
    else:
        logging.basicConfig(level=logging.INFO)
        #logging.info("debugging disabled.")

    #    explain(query)
    qres = store.query(query_str)
    for row in qres:
        for var in qres.vars:  # results.vars contient les noms des variables
            print(f"{var}: {row[var]}")  # Afficher nom de colonne et valeur
        print()  # Séparation entre les lignes

    if keep_store is not None:
        logging.info(f"storing collected data in {keep_store}")
        store.serialize(keep_store, format="nquads")


if __name__ == '__main__':
    slm_cmd()
