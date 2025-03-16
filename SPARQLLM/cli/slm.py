#!/usr/bin/python
import csv
import click

import rdflib
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib import URIRef
from rdflib.plugins.sparql.operators import register_custom_function


from SPARQLLM.utils.explain import explain
from SPARQLLM.udf.SPARQLLM import store

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

import logging
import configparser
import importlib

slm_timeout = 10
slm_ollama_model = "gpt2"

def configure_udf(config_file):
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case sensitivity for option names
    config.read(config_file)

    # Access the variables by section and key
    slm_timeout = config.getint('Requests', 'SLM-TIMEOUT')        # Read as integer
    slm_ollama_model = config.get('Requests', 'SLM-OLLAMA-MODEL')        # Read as integer 

    associations = config['Associations']
    for uri, full_func_name in associations.items():
        module_name, func_name = full_func_name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
#        func = globals().get(func_name)
        if callable(func):
            full_uri= f"http://example.org/{uri}"
            logging.info(f"Registering {func_name} with URI {full_uri}")
            register_custom_function(URIRef(full_uri), func)
        else:
            logging.error(f"FUnction {func_name} NOT Collable.")

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
@click.option(
"-o", "--output-result", type=click.STRING, default=None,
    help="File to store the result of the query."
)

@click.option(
    "-o", "--output-result", type=click.STRING, default=None,
    help="File to store the result in CSV of the query."
)


def slm_cmd(query, file, config,load,format="xml",debug=False,keep_store=None,output_result=None):
    logging.basicConfig(level=logging.INFO)

    if debug:
        ## seems that urllib3 redefine the logging level...
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.basicConfig(level=logging.DEBUG)
#        logger = logging.getLogger('urllib3')
#        logger.setLevel(logging.DEBUG)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.debug("debugging activated.")
    else:
        logging.basicConfig(level=logging.INFO)
        #logging.info("debugging disabled.")

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
        logging.info(f"loading config from {config}")
        ConfigSingleton(config_file=config)
    else:
        logging.info(f"loading default config.ini")
        config = ConfigSingleton(config_file='config.ini')

    if load is not None:
        store.parse(load, format=format)


    #    explain(query)
    qres = store.query(query_str)
#    print(f"qres:{qres.type}")
    if (qres.type=="CONSTRUCT"):  # Vérifier si c'est un CONSTRUCT
        if output_result is not None:
            if not output_result.endswith(".ttl"):
                output_result += ".ttl"

            qres.serialize(destination=output_result, format="turtle")  # Sauvegarde en Turtle
        else:
            print(qres.serialize(format="turtle").decode("utf-8"))  # Affichage en console
    else:
        if output_result is not None:
            with open(output_result, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(qres.vars)  # En-têtes
                for row in qres:
                    writer.writerow(row)
        else:
            print_result_as_table(qres)

    if keep_store is not None:
        logging.info(f"storing collected data in {keep_store}")
        store.serialize(keep_store, format="nquads")


if __name__ == '__main__':
    slm_cmd()
