# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode, quote, urlparse
from urllib.request import Request, urlopen

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.segraph_scrap import named_graph_exists

import os
import json

import logging
from pathlib import Path

logger = logging.getLogger(__name__)  # Configuration du logger pour ce module


def gettype(path):
    """
    Détecte le type d'un chemin (fichier, répertoire, lien symbolique, inconnu).

    Args:
        path (str): Le chemin à analyser.

    Returns:
        Literal: Le type de chemin sous forme de Literal RDF.
    """
    entry = Path(path)  # Conversion du chemin en objet Path
    if entry.is_file():  # Vérification si c'est un fichier
        return Literal('file', datatype=XSD.string)
    elif entry.is_dir():  # Vérification si c'est un répertoire
        return Literal('directory', datatype=XSD.string)
    elif entry.is_symlink():  # Vérification si c'est un lien symbolique
        return Literal('symlink', datatype=XSD.string)
    else:  # Type inconnu
        return Literal('unknown', datatype=XSD.string)


def list_directory_content(local_dir):
    """
    Liste le contenu d'un répertoire local.

    Args:
        local_dir (str): Le chemin du répertoire à lister.

    Returns:
        list: Une liste des fichiers et répertoires dans le chemin donné.

    Raises:
        Exception: En cas d'erreur lors de la lecture du répertoire.
    """
    try:
        return os.listdir(local_dir)  # Liste le contenu du répertoire
    except Exception as e:
        logger.error(f"Erreur lors de la lecture du répertoire {local_dir}: {e}")  # Log de l'erreur
        raise  # Relance l'exception


def add_triples_to_graph(named_graph, link_to, local_dir, files):
    """
    Ajoute les triplets RDF pour chaque fichier ou répertoire trouvé dans un répertoire donné.

    Args:
        named_graph (Graph): Le graphe RDF où ajouter les triplets.
        link_to (URIRef): L'URI de l'entité à laquelle lier les fichiers.
        local_dir (str): Le chemin du répertoire local.
        files (list): La liste des fichiers et répertoires à ajouter.
    """
    for file in files:
        file_path = os.path.join(local_dir, file)  # Construction du chemin complet du fichier
        file_uri = URIRef("file://" + file_path)  # Création d'un URI pour le fichier
        file_size = os.path.getsize(file_path)  # Récupération de la taille du fichier
        file_type = gettype(file_path)  # Récupération du type de fichier

        # Ajout des triplets au graphe
        named_graph.add((link_to, URIRef("http://example.org/has_path"), file_uri))
        named_graph.add((file_uri, URIRef("http://example.org/has_size"), Literal(file_size, datatype=XSD.integer)))
        named_graph.add((file_uri, URIRef("http://example.org/has_type"), file_type))


def RDIR(dir, link_to):
    """
    Fonction principale pour parcourir un répertoire local et ajouter des métadonnées RDF.

    Args:
        dir (str): Le chemin du répertoire à parcourir.
        link_to (URIRef): L'URI de l'entité à laquelle lier les fichiers.

    Returns:
        URIRef: L'URI du graphe RDF contenant les métadonnées, ou None si le graphe existe déjà.
    """
    logger.debug(f"RDIR called with: {dir}, type: {type(dir)}, link_to: {link_to}, type: {type(link_to)}")  # Log des arguments
    graph_uri = URIRef(dir)  # Création d'un URI pour le graphe

    # Vérifie si le graphe existe déjà
    if named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists.")  # Log si le graphe existe déjà
        return None

    # Crée un graphe nommé
    named_graph = store.get_context(graph_uri)

    try:
        # Conversion du chemin URI en chemin local
        local_dir = urlparse(dir).path
        logger.debug(f"RDIR processing local directory: {local_dir}")  # Log du chemin local

        # Liste les fichiers et répertoires
        files = list_directory_content(local_dir)

        # Ajoute les triplets RDF au graphe
        add_triples_to_graph(named_graph, link_to, local_dir, files)
        logger.debug(f"RDIR added {len(named_graph)} triples to graph {graph_uri}.")  # Log du nombre de triplets ajoutés
    except Exception as e:
        logger.error(f"Error processing directory {dir}: {e}")  # Log de l'erreur
        return Literal(f"Error retrieving {dir}")  # Retourne un message d'erreur

    return graph_uri  # Retourne l'URI du graphe


def test1():
    """
    Fonction de test pour vérifier le fonctionnement de RDIR avec une requête SPARQL simple.
    """
    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("file:///Users/molli-p/SPARQLLM")))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?s ?root ?g ?p1 ?t1 ?s1 ?p2 ?t2 ?p3 ?t3
    WHERE {
        ?s ?p ?root .
        BIND(ex:RDIR(?root,?root) AS ?g)
        GRAPH ?g {
            ?root ex:has_path ?p1 .
            ?p1 ex:has_type ?t1.
            ?p1 ex:has_size ?s1 .
            filter (str(?t1)="directory")
        } 
        BIND(ex:RDIR(?p1,?p1) as ?g2)
        OPTIONAL {
            GRAPH ?g2 {
                ?p1 ex:has_path ?p2 .
                ?p2 ex:has_type ?t2.
                ?p2 ex:has_size ?s2 .
                filter (str(?t2)="directory")
           }
            BIND(ex:RDIR(?p2,?p2) as ?g3)
            OPTIONAL {
                GRAPH ?g3 {
                    ?p2 ex:has_path ?p3 .
                    ?p3 ex:has_type ?t3.
                    ?p3 ex:has_size ?s3 .
                    filter (str(?t3)="directory")
                }
           }
       }
    }
    """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats
    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}")


def testrec():
    """
    Fonction de test pour vérifier le fonctionnement récursif de RDIR avec des requêtes SPARQL.
    """
    query_init_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?ginit
    WHERE {
        BIND(URI("file:///Users/molli-p/SPARQLLM") AS ?root)
        BIND(ex:RDIR(?root,?root) AS ?ginit)
        GRAPH ?gin {
            ?root ex:has_path ?p1 .
            ?p1 ex:has_type ?t1.
            ?p1 ex:has_size ?s1 .
        } 
    }
    """

    # Requête SPARQL récursive utilisant la fonction personnalisée
    query_rec_str = """
    PREFIX ex: <http://example.org/>
    SELECT distinct ?gout 
    WHERE {
        GRAPH <#gin#> {
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
    }
    """

    query_final_str = """
        PREFIX ex: <http://example.org/>
        SELECT (MAX(?s) AS ?max_s) 
        WHERE {
            graph ?g {?p ex:has_size ?s .}
        }
    """

    # Exécution de la requête initiale
    result = store.query(query_init_str)
    first_result = list(result)[0] if len(result) > 0 else None
    ginit = first_result['ginit']
    print(f"ginit : {ginit}")

    def recurse_on(gin):
        """
        Fonction récursive pour parcourir les répertoires et ajouter des métadonnées RDF.

        Args:
            gin (URIRef): L'URI du graphe à parcourir.
        """
        print(f"Recurse on : {gin}")
        query_rec = query_rec_str.replace("#gin#", str(gin))  # Remplacement du placeholder par l'URI du graphe
        result = store.query(query_rec)  # Exécution de la requête
        for row in result:
            recurse_on(row['gout'])  # Appel récursif sur les sous-répertoires

    recurse_on(ginit)  # Démarrage de la récursion

    # Affichage des graphes créés
    graph_names = [str(ctx.identifier) for ctx in store.contexts()]
    print("Liste des graphes :", graph_names)

    # Exécution de la requête finale
    result = store.query(query_final_str)
    print(f"Final query : {query_final_str}")
    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}")


# Exécution du module avec : python -m SPARQLLM.udf.readdir
if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG (désactivé)

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/RDIR"), RDIR)

    # test1()  # Exécution du premier test (désactivé)
    testrec()  # Exécution du test récursif