from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace
import sys
import os

import SPARQLLM.udf.funcSE
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import result_as_table
from SPARQLLM.udf.SPARQLLM import store
import shutil
import time

import logging
logger = logging.getLogger(__name__)

def create_init(config_path):
    actual_folder = os.path.dirname(os.path.abspath(__file__))
    shutil.copy(actual_folder+"/config.ini", config_path)

# run with : python -m query_request 
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Veuillez spécifier un fichier en argument.")
    else:

        try:
            file_path = sys.argv[1]


            folder_path = os.path.dirname(file_path)
            config_path = folder_path+'/config.ini'

            # if no config.ini if the folder
            if not os.path.exists(config_path):
                create_init(config_path)


            with open(file_path, 'r') as file:
                query_str = file.read()
                logging.basicConfig(level=logging.DEBUG)
                config = ConfigSingleton(config_file=folder_path+'/config.ini')

                # Execute the query
                result = store.query(str(query_str))


                # Trouver le répertoire du fichier d'entrée
                dir_path = os.path.dirname(file_path)
                
                # Créer le chemin du fichier de sortie
                output_file_path = os.path.join(dir_path, "output-"+str(time.time())+".txt")
                

                # Écrire dans le fichier de sortie
                with open(output_file_path, 'w') as output_file:
                    output_file.write(result_as_table(result).to_string(index=False))


        except Exception as e:
            print(f"Erreur lors de l'ouverture du fichier: {e}")

        

