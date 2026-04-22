#!/usr/bin/python
import csv
import os
from pathlib import Path
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
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate



import logging
import configparser
import importlib

slm_timeout = 10
slm_ollama_model = "gpt2"
SOURCE_CHOICES = {"hal", "openalex", "dblp", "serpapi"}


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
    "--rml-mapping", type=click.STRING, default=None,
    help="Override mapping path used by ggf:RML calls in query execution."
)
@click.option(
    "-df", "--rml-data-file", "rml_data_files", multiple=True, type=click.STRING,
    help="RML data file override. Repeat -d for multiple files."
)
@click.option(
    "-dd", "--rml-data-folder", type=click.STRING, default=None,
    help="RML data folder override used to resolve relative rml:source values."
)
@click.option(
    "--author", type=click.STRING, default=None,
    help="Author value used by dynamic service queries (mapped to SLM_AUTHOR)."
)
@click.option(
    "--year-start", type=click.STRING, default=None,
    help="Start year used by dynamic service queries (mapped to SLM_YEAR_START)."
)
@click.option(
    "--year-end", type=click.STRING, default=None,
    help="End year used by dynamic service queries (mapped to SLM_YEAR_END)."
)
@click.option(
    "--source", "selected_sources", multiple=True,
    type=click.Choice(sorted(SOURCE_CHOICES), case_sensitive=False),
    help="Enable a source for dynamic service queries. Repeat flag for multiple sources."
)
@click.argument("extra_sources", nargs=-1)


def slm_cmd(
    query,
    file,
    config,
    load,
    format="xml",
    debug=False,
    keep_store=None,
    output_result=None,
    rml_mapping=None,
    rml_data_files=(),
    rml_data_folder=None,
    author=None,
    year_start=None,
    year_end=None,
    selected_sources=(),
    extra_sources=(),
):
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("SPARQLLM").setLevel(logging.INFO)


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


    if config is not None:
        logging.info(f"loading config from {config}")
        ConfigSingleton(config_file=config)
    else:
        logging.info(f"loading default config.ini")
        config = ConfigSingleton(config_file='config.ini')

    if load is not None:
        store.parse(load, format=format)
        logging.debug(f"loading data from {load} (format={format}), store size is now {len(store)} triples")


    #    explain(query)
    env_updates = {}
    previous_env = {}
    if rml_mapping:
        env_updates["SPARQLLM_RML_MAPPING"] = str(Path(rml_mapping).resolve())
    if rml_data_folder:
        env_updates["SPARQLLM_RML_DATA_FOLDER"] = str(Path(rml_data_folder).resolve())
    if rml_data_files:
        resolved_files = [str(Path(p).resolve()) for p in rml_data_files]
        env_updates["SPARQLLM_RML_DATA_FILES"] = os.pathsep.join(resolved_files)
    if author is not None:
        env_updates["SLM_AUTHOR"] = str(author)
    if year_start is not None:
        env_updates["SLM_YEAR_START"] = str(year_start)
    if year_end is not None:
        env_updates["SLM_YEAR_END"] = str(year_end)
    merged_sources = [str(s).lower() for s in selected_sources]
    if extra_sources:
        if not selected_sources:
            raise click.UsageError(
                "Unexpected positional values. To pass multiple sources, use: --source hal dblp"
            )
        for value in extra_sources:
            src = str(value).lower()
            if src not in SOURCE_CHOICES:
                raise click.BadParameter(
                    f"Invalid source '{value}'. Allowed values: {', '.join(sorted(SOURCE_CHOICES))}",
                    param_hint="source",
                )
            merged_sources.append(src)

    if merged_sources:
        # Deduplicate while preserving order.
        unique_sources = list(dict.fromkeys(merged_sources))
        env_updates["SLM_SOURCES"] = ",".join(unique_sources)

    for key, value in env_updates.items():
        previous_env[key] = os.environ.get(key)
        os.environ[key] = value

    #    explain(query)
    if is_update_query(query_str):
        logging.info("Executing update query")
        store.update(query_str)
    else:
        qres = store.query(query_str)
#    print(f"qres:{qres.type}")
        if (qres.type=="CONSTRUCT"):  # Vérifier si c'est un CONSTRUCT
            if output_result is not None:
                if not output_result.endswith(".ttl"):
                    output_result += ".ttl"

                output_path = Path(output_result)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                qres.serialize(destination=str(output_path), format="turtle")  # Sauvegarde en Turtle
            else:
                print(qres.serialize(format="turtle").decode("utf-8"))  # Affichage en console
        else:
            if output_result is not None:
                output_path = Path(output_result)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(qres.vars)  # En-têtes
                    for row in qres:
                        writer.writerow(row)
            else:
                print_result_as_table(qres)

    for key in env_updates:
        old_value = previous_env.get(key)
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value

    if keep_store is not None:
        logging.info(f"storing collected data in {keep_store}")
        store.serialize(keep_store, format="nquads")


if __name__ == '__main__':
    slm_cmd()
