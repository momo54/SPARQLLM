# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

from string import Template
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

import os
import json
import hashlib

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module

# Récupération des clés API pour la recherche Google depuis les variables d'environnement
se_api_key = os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key = os.environ.get("SEARCH_CX")

# En-têtes HTTP pour les requêtes
headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}


def validate_arguments(keywords, link_to):
    """
    Valide les arguments passés à la fonction SEGRAPH.

    Args:
        keywords (str): Les mots-clés à rechercher.
        link_to (URIRef): L'URI de l'entité à laquelle lier les résultats.

    Raises:
        ValueError: Si `link_to` n'est pas un URIRef.
    """
    if not isinstance(link_to, URIRef):
        raise ValueError("SEGRAPH 2nd Argument should be an URI")
    return True


def generate_graph_uri(keywords):
    """
    Génère un URI unique pour le graphe basé sur les mots-clés.

    Args:
        keywords (str): Les mots-clés à rechercher.

    Returns:
        URIRef: L'URI unique du graphe.
    """
    return URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())


def fetch_links_from_api(se_url, keywords, max_links):
    """
    Récupère les liens depuis l'API de recherche Google.

    Args:
        se_url (str): L'URL de l'API de recherche.
        keywords (str): Les mots-clés à rechercher.
        max_links (int): Le nombre maximal de liens à récupérer.

    Returns:
        list: Une liste des liens trouvés.

    Raises:
        Exception: En cas d'erreur réseau ou de parsing JSON.
    """
    try:
        full_url = f"{se_url}&q={quote(keywords)}"  # Construction de l'URL complète
        logger.debug(f"Fetching links from URL: {full_url}")  # Log de l'URL
        request = Request(full_url, headers={'Accept': 'application/json'})  # Création de la requête
        response = urlopen(request)  # Envoi de la requête
        json_data = json.loads(response.read().decode('utf-8'))  # Parsing de la réponse JSON
        return [item['link'] for item in json_data.get('items', [])][:max_links]  # Extraction des liens
    except Exception as e:
        logger.error(f"Erreur réseau ou JSON : {e}")  # Log de l'erreur
        raise e  # Relance de l'exception


def add_links_to_graph(named_graph, link_to, links):
    """
    Ajoute les liens au graphe RDF.

    Args:
        named_graph (Graph): Le graphe RDF où ajouter les liens.
        link_to (URIRef): L'URI de l'entité à laquelle lier les liens.
        links (list): La liste des liens à ajouter.

    Returns:
        Graph: Le graphe mis à jour.
    """
    for link in links:
        named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(link)))  # Ajout du triplet au graphe
    logger.debug(f"Graph after adding links: {list(named_graph)}")  # Log du graphe mis à jour
    return named_graph


def SEGRAPH(keywords, link_to):
    """
    Fonction principale pour effectuer une recherche via l'API Google et stocker les résultats dans un graphe RDF.

    Args:
        keywords (str): Les mots-clés à rechercher.
        link_to (URIRef): L'URI de l'entité à laquelle lier les résultats.

    Returns:
        URIRef: L'URI du graphe RDF contenant les résultats.

    Raises:
        ValueError: Si les arguments ne sont pas valides.
    """
    global store

    config = ConfigSingleton()  # Récupération de la configuration singleton
    se_url = config.config['Requests']['SLM-CUSTOM-SEARCH-URL'].format(se_cx_key=se_cx_key, se_api_key=se_api_key)  # Formatage de l'URL de recherche
    max_links = int(config.config['Requests']['SLM-SEARCH-MAX-LINKS'])  # Récupération du nombre maximal de liens

    logger.debug(f"SEGRAPH: ({keywords}, {link_to}, {type(link_to)}, se_url: {se_url}, max_links: {max_links})")  # Log des arguments

    validate_arguments(keywords, link_to)  # Validation des arguments

    graph_uri = generate_graph_uri(keywords)  # Génération de l'URI du graphe
    if named_graph_exists(store, graph_uri):  # Vérification si le graphe existe déjà
        logger.debug(f"Graph {graph_uri} already exists (good)")  # Log si le graphe existe déjà
        return graph_uri

    named_graph = store.get_context(graph_uri)  # Création du graphe nommé
    links = fetch_links_from_api(se_url, keywords, max_links)  # Récupération des liens depuis l'API
    add_links_to_graph(named_graph, link_to, links)  # Ajout des liens au graphe

    logger.debug(f"Final graph content: {list(named_graph)}")  # Log du contenu final du graphe
    return graph_uri  # Retourne l'URI du graphe


# Exécution du module avec : python -m SPARQLLM.udf.segraph
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/SEGRAPH"), SEGRAPH)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("university nantes", datatype=XSD.string)))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?uri
        WHERE {
            ?s ?p ?value .
            BIND(ex:SEGRAPH(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value)),?s) AS ?graph)
            GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
        }
        """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)