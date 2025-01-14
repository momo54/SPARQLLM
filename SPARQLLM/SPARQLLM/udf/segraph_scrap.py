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

import time
from search_engines import Google, Duckduckgo, Bing

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module


# Choix du moteur de recherche (Google par défaut)
# engine = Google()
# engine = Duckduckgo()  # semble renvoyer une réponse 202 (acceptée mais retardée)
# engine = Bing()  # Les URL semblent mal formatées

# En-têtes HTTP pour les requêtes
headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}


def SEGRAPH_scrap(keywords, link_to, nb_results=5, response_override=None):
    """
    Fonction pour effectuer une recherche sur un moteur de recherche et stocker les résultats dans un graphe RDF.

    Args:
        keywords (str): Les mots-clés à rechercher.
        link_to (URIRef): L'URI de l'entité à laquelle lier les résultats.
        nb_results (int, optionnel): Nombre de résultats à récupérer. Par défaut à 5.
        response_override (list, optionnel): Résultats simulés pour les tests.

    Returns:
        URIRef: L'URI du graphe RDF contenant les résultats.

    Raises:
        ValueError: Si les mots-clés sont vides ou si `link_to` n'est pas un URIRef.
    """
    global store

    config = ConfigSingleton()  # Récupération de la configuration singleton
    wait_time = int(config.config['Requests']['SLM-SEARCH-WAIT'])  # Temps d'attente entre les requêtes

    nb_results = int(nb_results)  # Conversion du nombre de résultats en entier
    logger.debug(f"SEGRAPH_scrap: (keyword: {keywords}, link to: {link_to}, nb_results: {nb_results})")  # Log des arguments

    # Vérification que `link_to` est bien un URIRef
    if not isinstance(link_to, URIRef):
        raise ValueError("SEGRAPH_scrap 2nd Argument should be an URI")

    # Vérification que les mots-clés ne sont pas vides
    if not keywords.strip():
        raise ValueError("Invalid keywords: keywords cannot be empty or whitespace")

    # Calcul de l'URI unique basé sur les mots-clés
    graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())

    # Vérification si le graphe existe déjà
    if named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists.")  # Log si le graphe existe déjà
        return graph_uri

    logger.debug(f"Waiting for {wait_time} seconds...")  # Log du temps d'attente
    time.sleep(wait_time)  # Attente avant de continuer

    named_graph = store.get_context(graph_uri)  # Création du graphe nommé
    try:
        # Utilisation des résultats simulés si fournis
        if response_override is not None:
            links = response_override
        else:
            # Appel du moteur de recherche réel (Google par défaut)
            engine = Google()
            results = engine.search(keywords, pages=1)  # Recherche des résultats
            links = results.links()  # Récupération des liens

        # Ajout des liens au graphe
        for item in links[:nb_results]:
            logger.debug(f"SEGRAPH_scrap found: {item}")  # Log des liens trouvés
            named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(item)))  # Ajout du triplet au graphe

    except Exception as e:
        logger.error(f"SEGRAPH_scrap: Error during search: {e}")  # Log de l'erreur

    return graph_uri  # Retourne l'URI du graphe


# Exécution du module avec : python -m SPARQLLM.udf.segraph_scrap
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/SEGRAPH-SC"), SEGRAPH_scrap)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("university nantes", datatype=XSD.string)))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?uri
        WHERE {
            ?s ?p ?value .
            BIND(ex:SEGRAPH-SC(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value)),?s,5) AS ?graph)
                GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
        }
        """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)