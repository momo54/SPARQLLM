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

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

from bs4 import BeautifulSoup
import requests
import html
import html2text
import unidecode

from search_engines import Google

# Initialisation du moteur de recherche Google
engine = Google()

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module


def SearchEngine(keywords):
    """
    Fonction pour effectuer une recherche sur un moteur de recherche (Google) et retourner le premier lien trouvé.

    Args:
        keywords (str): Les mots-clés à rechercher.

    Returns:
        URIRef: L'URI du premier lien trouvé.

    Raises:
        ValueError: Si les mots-clés sont vides, trop longs ou si aucun lien n'est trouvé.
        Exception: En cas d'erreur lors de la recherche.
    """
    config = ConfigSingleton()  # Récupération de la configuration singleton
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])  # Récupération du timeout depuis la configuration

    # Vérification que les mots-clés ne sont pas vides
    if not keywords.strip():
        raise ValueError("Les mots-clés ne peuvent pas être vides.")

    # Vérification que les mots-clés ne dépassent pas 1000 caractères
    if len(keywords) > 1000:
        raise ValueError("Les mots-clés sont trop longs.")

    logger.debug(f"keywords: {keywords}, timeout: {timeout}")  # Log des mots-clés et du timeout

    try:
        # Recherche des résultats sur Google (1 page)
        results = engine.search(keywords, pages=1)  # Suppression de `timeout`
        links = results.links()  # Récupération des liens des résultats

        # Vérification qu'au moins un lien a été trouvé
        if not links:
            raise ValueError("Aucun lien trouvé pour les mots-clés.")

        return URIRef(links[0])  # Retourne le premier lien trouvé sous forme d'URI
    except Exception as e:
        logger.error(f"Erreur lors de la recherche : {e}")  # Log de l'erreur
        raise  # Relance l'exception


# Exécution du module avec : python -m SPARQLLM.udf.funcSE_scrap
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/SE"), SearchEngine)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("univ nantes", datatype=XSD.string)))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:SE(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value))) AS ?result)
    }
    """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)