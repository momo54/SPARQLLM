#!/usr/bin/python
import csv
import json
import os
import time
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
from SPARQLLM.udf.read_rdf import load_rdf_file
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate



import logging
import configparser
import importlib

slm_timeout = 10
slm_ollama_model = "gpt2"


def is_update_query(sparql_query: str) -> bool:
    try:
        # Si le parsing via parseUpdate réussit, c'est une requête d'update
        parseUpdate(sparql_query)
        return True
    except Exception:
        return False

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
@click.option('--metrics', is_flag=True, help="Print basic I/O metrics for this slm-run execution.")
@click.option('--metrics-out', type=click.STRING, default=None, help="Write I/O metrics as JSON to a file.")


def slm_cmd(query, file, config,load,format="xml",debug=False,keep_store=None,output_result=None, metrics=False, metrics_out=None):
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("SPARQLLM").setLevel(logging.INFO)
    total_started = time.perf_counter()


    if debug:
        ## seems that urllib3 redefine the logging level...
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
#        logging.basicConfig(level=logging.DEBUG)
#        logger = logging.getLogger('urllib3')
#        logger.setLevel(logging.DEBUG)
#        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("SPARQLLM").setLevel(logging.DEBUG)
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

    io_metrics = {
        "call_count": 1,
        "query_input_bytes": len(query_str.encode("utf-8")),
        "result_output_bytes": None,
        "result_type": None,
        "output_target": "stdout" if output_result is None else output_result,
        "load_wall_time_s": 0.0,
        "execution_wall_time_s": None,
        "total_wall_time_s": None,
        "loaded_graph_uri": None,
    }


    if config is not None:
        logging.info(f"loading config from {config}")
        ConfigSingleton(config_file=config)
    else:
        logging.info(f"loading default config.ini")
        config = ConfigSingleton(config_file='config.ini')

    if load is not None:
        load_started = time.perf_counter()
        loaded_graph_uri = load_rdf_file(load, format)
        io_metrics["load_wall_time_s"] = round(time.perf_counter() - load_started, 6)
        io_metrics["loaded_graph_uri"] = str(loaded_graph_uri)
        logging.debug(f"loading data from {load} (format={format}), store size is now {len(store)} triples")


    #    explain(query)
    execution_started = time.perf_counter()
    if is_update_query(query_str):
        logging.info("Executing update query")
        store.update(query_str)
        io_metrics["result_type"] = "UPDATE"
        io_metrics["result_output_bytes"] = 0
    else:
        qres = store.query(query_str)
#    print(f"qres:{qres.type}")
        io_metrics["result_type"] = str(qres.type)
        if (qres.type=="CONSTRUCT"):  # Vérifier si c'est un CONSTRUCT
            turtle_data = qres.serialize(format="turtle")
            if isinstance(turtle_data, bytes):
                turtle_text = turtle_data.decode("utf-8")
            else:
                turtle_text = str(turtle_data)
            io_metrics["result_output_bytes"] = len(turtle_text.encode("utf-8"))

            if output_result is not None:
                if not output_result.endswith(".ttl"):
                    output_result += ".ttl"
                with open(output_result, "w", encoding="utf-8") as f:
                    f.write(turtle_text)
            else:
                print(turtle_text)
        else:
            if output_result is not None:
                with open(output_result, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(qres.vars)  # En-têtes
                    for row in qres:
                        writer.writerow(row)
                io_metrics["result_output_bytes"] = os.path.getsize(output_result)
            else:
                print_result_as_table(qres)
    io_metrics["execution_wall_time_s"] = round(time.perf_counter() - execution_started, 6)
    io_metrics["total_wall_time_s"] = round(time.perf_counter() - total_started, 6)

    if keep_store is not None:
        logging.info(f"storing collected data in {keep_store}")
        store.serialize(keep_store, format="nquads")

    if metrics or metrics_out is not None:
        metrics_json = json.dumps(io_metrics, ensure_ascii=False)
        if metrics:
            click.echo(metrics_json, err=True)
        if metrics_out is not None:
            with open(metrics_out, "w", encoding="utf-8") as mf:
                mf.write(json.dumps(io_metrics, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    slm_cmd()
