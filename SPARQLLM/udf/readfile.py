from rdflib import Graph, Literal, URIRef  # Importation des classes Graph, Literal et URIRef du module rdflib
from rdflib.namespace import XSD  # Importation du namespace XSD de rdflib
from rdflib.plugins.sparql import prepareQuery  # Importation de la fonction prepareQuery du module sparql
from rdflib.plugins.sparql.operators import register_custom_function  # Importation de la fonction register_custom_function du module operators

from string import Template  # Importation de la classe Template du module string
from urllib.parse import urlencode, quote  # Importation des fonctions urlencode et quote du module urllib.parse
from urllib.request import Request, urlopen  # Importation des classes Request et urlopen du module urllib.request

import os  # Importation du module os
import json  # Importation du module json

import requests  # Importation du module requests
import html  # Importation du module html
import html2text  # Importation du module html2text
import unidecode  # Importation du module unidecode
from urllib.parse import urlparse  # Importation de la fonction urlparse du module urllib.parse

from SPARQLLM.udf.SPARQLLM import store  # Importation de la variable store du module SPARQLLM
from SPARQLLM.config import ConfigSingleton  # Importation de la classe ConfigSingleton du module config
from SPARQLLM.utils.utils import print_result_as_table  # Importation de la fonction print_result_as_table du module utils

import logging  # Importation du module logging
logger = logging.getLogger(__name__)  # Création d'un logger

# carefull, max_size is a string
import re  # Import nécessaire pour le nettoyage

def readhtmlfile(path_uri, max_size):
    """
    Fonction pour lire un fichier HTML et extraire le texte.
    """
    config = ConfigSingleton()  # Création d'une instance de ConfigSingleton (mocké dans les tests)
    max_size = int(max_size)  # Conversion de max_size en entier

    logger.debug(f"uri: {path_uri}, max_size: {max_size}")  # Log de l'URI et de la taille maximale
    try:
        with open(urlparse(path_uri).path, 'r') as file:  # Ouverture du fichier en mode lecture
            data = file.read()  # Lecture du contenu du fichier
            h = html2text.HTML2Text()  # Création d'une instance de HTML2Text
            h.ignore_links = True  # Ignore les liens
            h.ignore_images = True  # Ignore les images
            uri_text = h.handle(data)  # Conversion du HTML en texte

            # Nettoyage des liens Markdown résiduels (par exemple, "Link")
            uri_text_cleaned = re.sub(r"Link\s*$", "", uri_text)  # Supprime les mots "Link" isolés
            uri_text_cleaned = re.sub(r"\[.*?\]\(.*?\)", "", uri_text_cleaned)  # Supprime les liens Markdown

            # Nettoyage général : espaces, nouvelles lignes
            uri_text_cleaned = (
                unidecode.unidecode(uri_text_cleaned)  # Conversion des caractères Unicode en ASCII
                .lstrip("#")  # Supprime les symboles Markdown au début
                .replace("\n", " ")  # Remplace les nouvelles lignes par des espaces
                .replace("  ", " ")  # Supprime les espaces multiples
                .strip()  # Supprime les espaces en début et fin de chaîne
            )

            logger.debug(f"result={uri_text_cleaned[:max_size]}")  # Log du résultat tronqué
            return Literal(uri_text_cleaned[:max_size], datatype=XSD.string)  # Retourne le texte tronqué
    except (FileNotFoundError, PermissionError) as e:  # Gestion des erreurs de fichier
        return Literal(f"Error reading {path_uri}")  # Retourne un message d'erreur
    except Exception as e:  # Gestion des autres exceptions
        logger.error(f"Unexpected error: {e}")  # Log de l'erreur inattendue
        return Literal(f"Error reading {path_uri}")  # Retourne un message d'erreur

# run with : python -m SPARQLLM.udf.readfile
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging
    config = ConfigSingleton(config_file='config.ini')  # Création d'une instance de ConfigSingleton avec le fichier de configuration

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/FILE-HTML"), readhtmlfile)  # Enregistrement de la fonction readhtmlfile avec un URI personnalisé

    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?t
    WHERE {
        BIND("data/zenodo.html" AS ?uri)
        BIND(ex:FILE-HTML(?uri,100) AS ?t)
    }
    """
    # Execute the query
    result = store.query(query_str)  # Exécution de la requête SPARQL
    print_result_as_table(result)  # Affichage du résultat sous forme de tableau
