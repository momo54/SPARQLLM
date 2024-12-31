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

# Récupération des clés API pour la recherche Google depuis les variables d'environnement
se_api_key = os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key = os.environ.get("SEARCH_CX")

from bs4 import BeautifulSoup
import requests
import html
import html2text
import unidecode

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module

# En-têtes HTTP pour les requêtes
headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}


def BS4(uri):
    """
    Fonction pour extraire le texte d'une page web à l'aide de BeautifulSoup (BS4).

    Args:
        uri (str): L'URL de la page web à analyser.

    Returns:
        Literal: Le texte extrait de la page, tronqué selon la configuration, ou un message d'erreur.
    """
    config = ConfigSingleton()  # Récupération de la configuration singleton
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])  # Récupération du timeout depuis la configuration
    truncate = int(config.config['Requests']['SLM-TRUNCATE'])  # Récupération de la limite de troncation

    logger.debug(f"BS4: {uri}")  # Log de l'URI à analyser
    try:
        # Faire la requête HTTP pour obtenir le contenu de la page
        response = requests.get(uri, headers=headers, timeout=timeout)
        response.raise_for_status()  # Vérifie les erreurs HTTP

        # Vérification que le contenu est du HTML
        if 'text/html' in response.headers['Content-Type']:
            h = html2text.HTML2Text()  # Initialisation de l'outil de conversion HTML vers texte
            text = h.handle(response.text)  # Conversion du HTML en texte
            text = unidecode.unidecode(text)  # Normalisation du texte (suppression des accents)
            return Literal(text.strip()[:truncate])  # Retourne le texte tronqué
        else:
            return Literal(f"No HTML content at {uri}")  # Retourne un message si le contenu n'est pas du HTML

    except requests.exceptions.RequestException as e:
        # En cas d'erreur HTTP ou de connexion
        return Literal(f"Error retrieving {uri}")  # Retourne un message d'erreur


def Google(keywords):
    """
    Fonction pour effectuer une recherche sur Google via l'API Custom Search et retourner le premier lien trouvé.

    Args:
        keywords (str): Les mots-clés à rechercher.

    Returns:
        URIRef: L'URI du premier lien trouvé, ou un URIRef vide en cas d'erreur ou d'absence de résultats.
    """
    config = ConfigSingleton()  # Récupération de la configuration singleton
    se_url = config.config['Requests']['SLM-CUSTOM-SEARCH-URL'].format(se_cx_key=se_cx_key, se_api_key=se_api_key)  # Formatage de l'URL de recherche

    logger.debug(f"search: {keywords}, se_url: {se_url}")  # Log des mots-clés et de l'URL de recherche

    se_url = f"{se_url}&q={quote(keywords)}"  # Ajout des mots-clés à l'URL
    headers = {'Accept': 'application/json'}  # En-têtes pour la requête
    request = Request(se_url, headers=headers)  # Création de la requête

    try:
        response = urlopen(request)  # Exécution de la requête
        json_data = json.loads(response.read().decode('utf-8'))  # Lecture et décodage de la réponse JSON

        # Extraction des URLs des résultats
        links = [item['link'] for item in json_data.get('items', [])]

        if not links:  # Si aucun résultat n'est trouvé
            return URIRef("")  # Retourner un URIRef vide pour indiquer l'absence de résultat

        return URIRef(links[0])  # Retourne le premier lien trouvé sous forme d'URI

    except Exception as e:
        logger.error(f"Error retrieving results for {keywords}: {e}")  # Log de l'erreur
        return URIRef("")  # Retourner un URIRef vide en cas d'erreur


# Exécution du module avec : python -m SPARQLLM.udf.funcSE
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement des fonctions avec des URI personnalisés
    register_custom_function(URIRef("http://example.org/BS4"), BS4)
    register_custom_function(URIRef("http://example.org/Google"), Google)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("univ nantes", datatype=XSD.string)))

    # Requête SPARQL utilisant la fonction personnalisée Google
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value))) AS ?result)
    }
    """

    # Exécution de la requête
    result = store.query(query_str)
    print_result_as_table(result)  # Affichage des résultats sous forme de tableau

    # Requête SPARQL utilisant les fonctions personnalisées Google et BS4
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("Je veux savoir le nombre d'étudiants à UNIV ","UNIV",STR(?value))) AS ?uri)
        BIND(ex:BS4(?uri) AS ?result)
    }
    """

    # Exécution de la requête
    result = store.query(query_str)
    print_result_as_table(result)  # Affichage des résultats sous forme de tableau