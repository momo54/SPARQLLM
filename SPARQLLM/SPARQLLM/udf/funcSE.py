from rdflib import Graph, Literal, URIRef  # Importation des classes Graph, Literal et URIRef du module rdflib
from rdflib.namespace import XSD  # Importation du namespace XSD de rdflib
from rdflib.plugins.sparql import prepareQuery  # Importation de la fonction prepareQuery du module sparql
from rdflib.plugins.sparql.operators import register_custom_function  # Importation de la fonction register_custom_function du module operators

from string import Template  # Importation de la classe Template du module string
from urllib.parse import urlencode, quote  # Importation des fonctions urlencode et quote du module urllib.parse
from urllib.request import Request, urlopen  # Importation des classes Request et urlopen du module urllib.request

import os  # Importation du module os
import json  # Importation du module json

# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key = os.environ.get("SEARCH_API_SOBIKE44")  # Récupération de la clé API de recherche depuis les variables d'environnement
se_cx_key = os.environ.get("SEARCH_CX")  # Récupération de la clé CX de recherche depuis les variables d'environnement

from bs4 import BeautifulSoup  # Importation de la classe BeautifulSoup du module bs4
import requests  # Importation du module requests
import html  # Importation du module html
import html2text  # Importation du module html2text
import unidecode  # Importation du module unidecode

from SPARQLLM.config import ConfigSingleton  # Importation de la classe ConfigSingleton du module config
from SPARQLLM.utils.utils import print_result_as_table  # Importation de la fonction print_result_as_table du module utils
from SPARQLLM.udf.SPARQLLM import store  # Importation de la variable store du module SPARQLLM

import logging  # Importation du module logging
logger = logging.getLogger(__name__)  # Création d'un logger

headers = {
    'Accept': 'text/html',  # Définition de l'en-tête Accept
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}

def BS4(uri):
    """
    Fonction pour extraire le texte d'une page HTML en utilisant BeautifulSoup.
    """
    config = ConfigSingleton()  # Création d'une instance de ConfigSingleton
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])  # Récupération du timeout depuis la configuration
    truncate = int(config.config['Requests']['SLM-TRUNCATE'])  # Récupération de la longueur de troncature depuis la configuration

    logger.debug(f"BS4: {uri}")  # Log de l'URI
    try:
        # Faire la requête HTTP pour obtenir le contenu de la page
        response = requests.get(uri, headers=headers, timeout=timeout)  # Requête HTTP GET
        response.raise_for_status()  # Vérifie les erreurs HTTP
        if 'text/html' in response.headers['Content-Type']:  # Vérifie si le contenu est du HTML

            h = html2text.HTML2Text()  # Création d'une instance de HTML2Text
            text = h.handle(response.text)  # Conversion du HTML en texte
            text = unidecode.unidecode(text)  # Conversion des caractères Unicode en ASCII
            return Literal(text.strip()[:truncate])  # Retourne le texte tronqué
        else:
            return Literal(f"No HTML content at {uri}")  # Retourne un message d'erreur si le contenu n'est pas du HTML

    except requests.exceptions.RequestException as e:
        # En cas d'erreur HTTP ou de connexion
        return Literal(f"Error retreiving {uri}")  # Retourne un message d'erreur
    
def BS4HTML(uri):
    """
    Fonction pour extraire le texte d'une page HTML en utilisant BeautifulSoup.
    """
    config = ConfigSingleton()  # Création d'une instance de ConfigSingleton
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])  # Récupération du timeout depuis la configuration
    truncate = int(config.config['Requests']['SLM-TRUNCATE'])  # Récupération de la longueur de troncature depuis la configuration

    logger.debug(f"BS4: {uri}")  # Log de l'URI
    try:
        # Faire la requête HTTP pour obtenir le contenu de la page
        response = requests.get(uri, headers=headers, timeout=timeout)  # Requête HTTP GET
        response.raise_for_status()  # Vérifie les erreurs HTTP
        if 'text/html' in response.headers['Content-Type']:  # Vérifie si le contenu est du HTML

            # Envoie du HTML
            html_content = response.text
            return Literal(html_content)
        else:
            return Literal(f"No HTML content at {uri}")  # Retourne un message d'erreur si le contenu n'est pas du HTML

    except requests.exceptions.RequestException as e:
        # En cas d'erreur HTTP ou de connexion
        return Literal(f"Error retreiving {uri}")  # Retourne un message d'erreur

def Google(keywords):
    """
    Fonction pour effectuer une recherche Google Custom Search.
    """
    config = ConfigSingleton()  # Création d'une instance de ConfigSingleton
    se_url = config.config['Requests']['SLM-CUSTOM-SEARCH-URL'].format(se_cx_key=se_cx_key, se_api_key=se_api_key)  # Récupération de l'URL de recherche depuis la configuration

    logger.debug(f"search: {keywords}, se_url: {se_url}")  # Log des mots-clés et de l'URL de recherche

    se_url = f"{se_url}&q={quote(keywords)}"  # Ajout des mots-clés à l'URL de recherche
    headers = {'Accept': 'application/json'}  # Définition de l'en-tête Accept
    request = Request(se_url, headers=headers)  # Création de la requête HTTP

    try:
        response = urlopen(request)  # Envoi de la requête HTTP
        json_data = json.loads(response.read().decode('utf-8'))  # Lecture et décodage de la réponse JSON

        # Extract the URLs from the response
        links = [item['link'] for item in json_data.get('items', [])]  # Extraction des liens de la réponse

        if not links:  # Si aucun résultat n'est trouvé
            return URIRef("")  # Retourner un URIRef vide pour indiquer l'absence de résultat

        return URIRef(links[0])  # Retourne le premier lien trouvé

    except Exception as e:
        logger.error(f"Error retrieving results for {keywords}: {e}")  # Log de l'erreur
        return URIRef("")  # Retourne un URIRef vide en cas d'erreur

# run with : python -m SPARQLLM.udf.funcSE
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging
    config = ConfigSingleton(config_file='config.ini')  # Création d'une instance de ConfigSingleton avec le fichier de configuration

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/BS4"), BS4)  # Enregistrement de la fonction BS4 avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/Google"), Google)  # Enregistrement de la fonction Google avec un URI personnalisé

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("univ nantes", datatype=XSD.string)))  # Ajout de données d'exemple au graphe

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value))) AS ?result)
    }
    """

    # Execute the query
    result = store.query(query_str)  # Exécution de la requête SPARQL
    print_result_as_table(result)  # Affichage du résultat sous forme de tableau

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("Je veux savoir le nombre d'étudiants à UNIV ","UNIV",STR(?value))) AS ?uri)
        BIND(ex:BS4(?uri) AS ?result)
    }
    """
    # Execute the query
    result = store.query(query_str)  # Exécution de la requête SPARQL
    print_result_as_table(result)  # Affichage du résultat sous forme de tableau
