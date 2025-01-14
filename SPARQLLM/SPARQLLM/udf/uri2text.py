# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

import os
import json

import requests
import html
import html2text
import unidecode

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module


def GETTEXT(uri, max_size):
    """
    Fonction pour récupérer le contenu textuel d'une page web et le tronquer à une taille maximale.

    Args:
        uri (str): L'URI de la page web à récupérer.
        max_size (str): La taille maximale du texte retourné.

    Returns:
        Literal: Le contenu textuel tronqué ou un message d'erreur encapsulé dans un Literal RDF.
    """
    config = ConfigSingleton()  # Récupération de la configuration singleton
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])  # Récupération du timeout

    logger.debug(f"uri: {uri}, max_size: {max_size}, timeout: {timeout}")  # Log des arguments

    try:
        headers = {
            'Accept': 'text/html',
            'User-Agent': 'Mozilla/5.0'  # En-tête pour émuler un navigateur
        }

        # Requête HTTP pour récupérer le contenu de la page
        response = requests.get(uri, headers=headers, timeout=timeout)
        response.raise_for_status()  # Vérification des erreurs HTTP

        # Vérification si le contenu est HTML
        if 'text/html' in response.headers.get('Content-Type', ''):
            h = html2text.HTML2Text()  # Initialisation de l'outil de conversion HTML vers texte
            h.ignore_links = True  # Ignorer les liens dans le texte
            uri_text = h.handle(response.text)  # Conversion du HTML en texte
            uri_text_cleaned = unidecode.unidecode(uri_text).strip()  # Suppression des accents et normalisation
            uri_text_cleaned = uri_text_cleaned.lstrip("#").strip()  # Nettoyage des caractères Markdown

            max_size = int(max_size)  # Conversion de la taille maximale en entier
            logger.debug(f"Truncated content to {max_size} characters.")  # Log de la troncation
            return Literal(uri_text_cleaned[:max_size], datatype=XSD.string)  # Retourne le texte tronqué
        else:
            return Literal(f"No HTML content at {uri}", datatype=XSD.string)  # Retourne un message si le contenu n'est pas HTML

    except requests.exceptions.RequestException as e:
        logger.error(f"Error retrieving {uri}: {e}")  # Log de l'erreur
        return Literal(f"Error retrieving {uri}", datatype=XSD.string)  # Retourne un message d'erreur


# Exécution du module avec : python -m SPARQLLM.udf.uri2text
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/GETTEXT"), GETTEXT)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("https://zenodo.org/records/13957372")))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?t
    WHERE {
        ?s ?p ?uri .
        BIND(ex:GETTEXT(?uri,5000) AS ?t)
    }
    """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)