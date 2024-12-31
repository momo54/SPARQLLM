# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.segraph_scrap import named_graph_exists
from SPARQLLM.udf.readdir import gettype, RDIR

import os
import json

import logging
import traceback

from pathlib import Path

rec_logger = logging.getLogger("recurse")  # Configuration du logger pour ce module


def recurse(query_str, gin, ginit, max_depth=10):
    """
    Fonction récursive pour parcourir des graphes RDF et ajouter des relations entre eux.

    Args:
        query_str (str): La requête SPARQL à exécuter pour obtenir les graphes suivants.
        gin (str): Le nom de la variable de graphe dans la requête SPARQL.
        ginit (URIRef): L'URI du graphe initial à partir duquel commencer la récursion.
        max_depth (int, optional): La profondeur maximale de récursion. Par défaut à 10.

    Returns:
        URIRef: L'URI du graphe contenant toutes les relations entre les graphes parcourus.
    """
    rec_logger.debug(f"RECURSE enter : {query_str}, gin: {gin},{type(gin)}, ginit: {ginit},{type(ginit)}")  # Log des arguments
    all_graph_uri = URIRef("http://example.org/allg")  # URI du graphe contenant toutes les relations

    ## Vérification si le graphe de sortie existe déjà
    if named_graph_exists(store, all_graph_uri):
        rec_logger.debug(f"Recurse Graph {all_graph_uri} already exists (good)")  # Log si le graphe existe déjà
        return None
    else:
        named_graph = store.get_context(all_graph_uri)  # Création du graphe de sortie

    def func_recurse_on(gin_rec, depth=0):
        """
        Fonction récursive interne pour parcourir les graphes.

        Args:
            gin_rec (URIRef): L'URI du graphe courant.
            depth (int, optional): La profondeur actuelle de récursion. Par défaut à 0.
        """
        print(f"RECURSE Recurse on : {gin_rec}")  # Log du graphe courant
        result = store.query(query_str, initBindings={gin: gin_rec})  # Exécution de la requête SPARQL
        for row in result:
            rec_logger.debug(f"REcurse row: {row}")  # Log des résultats de la requête
            if row['gout'] == None:
                rec_logger.debug(f"REcurse row: get None")  # Log si aucun graphe suivant n'est trouvé
                continue
            else:
                gout = URIRef(row['gout'])  # Conversion du graphe suivant en URIRef
                print(f"RECURSE Recurse on : {gin_rec} -> {gout}")  # Log de la relation entre les graphes
                named_graph.add((gin_rec, URIRef("http://example.org/has_graph"), gout))  # Ajout de la relation au graphe
                named_graph.add((gout, URIRef("http://example.org/has_depth"), Literal(depth, datatype=XSD.integer)))  # Ajout de la profondeur
                if depth <= max_depth:
                    func_recurse_on(gout, depth + 1)  # Appel récursif sur le graphe suivant
                else:
                    rec_logger.debug(f"RECURSE max depth :  {max_depth} reached")  # Log si la profondeur maximale est atteinte

    try:
        func_recurse_on(ginit, 0)  # Démarrage de la récursion
    except Exception as e:
        rec_logger.debug(f"RECURSE Exception {e}")  # Log de l'erreur
        traceback.print_exc()  # Impression de la trace de l'erreur

    rec_logger.debug(f"RECURSE end: graph {all_graph_uri} has {len(all_graph_uri)} triples")  # Log du nombre de triplets ajoutés
    return all_graph_uri  # Retourne l'URI du graphe contenant toutes les relations


def testrec():
    """
    Fonction de test pour vérifier le fonctionnement de la récursion avec une requête SPARQL.
    """
    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT (MAX(?s) AS ?max_s)  WHERE {
        ## init recursion
        BIND(URI("file:///Users/molli-p/SPARQLLM") AS ?root)
        BIND(ex:RDIR(?root,?root) AS ?ginit)
        BIND(\"\"\"
        PREFIX ex: <http://example.org/>
        SELECT DISTINCT ?gout WHERE {
            GRAPH ?gin {
                ?root ex:has_path ?p1 .
                ?p1 ex:has_type ?t1.
                ?p1 ex:has_size ?s1 .
                filter (str(?t1)="directory")
            } 
            BIND(ex:RDIR(?p1,?p1) as ?gout)
            OPTIONAL {
                GRAPH ?gout {
                    ?p1 ex:has_path ?p2 .
                    ?p2 ex:has_type ?t2.
                    ?p2 ex:has_size ?s2 .
                }
            }
        } \"\"\" AS ?query_str)
        BIND(ex:RECURSE(?query_str,'?gin',?ginit,3) AS ?allg)
        GRAPH ?allg {?init ex:has_graph ?g }
        GRAPH ?g {?p ex:has_size ?s .}
    }"""

    # Exécution de la requête
    result = store.query(query_str)
    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}")  # Affichage des résultats


# Exécution du module avec : python -m SPARQLLM.udf.recurse
if __name__ == "__main__":
    rec_logger = logging.getLogger("recurse")  # Configuration du logger pour ce module
    # logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG (désactivé)
    rec_logger.setLevel(logging.DEBUG)  # Configuration du niveau de log

    # Enregistrement des fonctions avec des URI personnalisés
    register_custom_function(URIRef("http://example.org/RECURSE"), recurse)
    register_custom_function(URIRef("http://example.org/RDIR"), RDIR)

    testrec()  # Exécution de la fonction de test