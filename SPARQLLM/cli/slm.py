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

import logging

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
    "-l", "--load", type=click.STRING, default=None,
    help="RDF data file to load"
)
@click.option(
    "-fo", "--format", type=click.STRING, default="xml",
    help="Format of RDF data file"
)

@click.option('-d', '--debug', is_flag=True, help="turn on debug.")


def slm_cmd(query, file,load,format="xml",debug=False):

    query_str = ""

    if query is None and file is None:
        print("Error: you must specificy a query to execute, either with --query or --file. See explain --help for more informations.")
        exit(1)

    if file is not None:
        with open(file) as query_file:
            query_str = query_file.read()
    else:
        query_str = query


    if load is not None:
        store.parse(load, format=format)

    if debug:
        logging.basicConfig(level=logging.DEBUG)
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

if __name__ == '__main__':
    slm_cmd()
