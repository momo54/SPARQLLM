import unittest  # Importation du module unittest pour les tests unitaires
from rdflib import URIRef, Dataset, Literal  # Importation des classes URIRef, Dataset et Literal du module rdflib
from SPARQLLM.udf.segraph_scrap import SEGRAPH_scrap  # Importation de la fonction SEGRAPH_scrap du module segraph_scrap
from SPARQLLM.udf.SPARQLLM import store  # Importation de la variable store du module SPARQLLM
import hashlib  # Importation du module hashlib pour les fonctions de hachage

class TestSEGRAPH_scrap(unittest.TestCase):  # Définition de la classe de test pour la fonction SEGRAPH_scrap
    def setUp(self):
        # Nettoyer le graphe avant chaque test
        store.remove((None, None, None))  # Supprime tous les triplets du graphe

        # Réponses simulées pour les tests
        self.valid_links = [
            "http://example.org/link1",
            "http://example.org/link2",
            "http://example.org/link3",
        ]  # Liens valides simulés
        self.empty_links = []  # Aucun résultat

    def test_invalid_link_to(self):
        """Test avec un `link_to` invalide."""
        keywords = "test keywords"  # Mots-clés de test
        link_to = "not_a_uri"  # URI invalide

        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            SEGRAPH_scrap(keywords, link_to)  # Appel de la fonction SEGRAPH_scrap avec l'URI invalide
        self.assertIn("2nd Argument should be an URI", str(context.exception))  # Vérifie que l'exception contient "2nd Argument should be an URI"

    def test_valid_links(self):
        """Test avec des liens valides simulés."""
        keywords = "valid keywords"  # Mots-clés de test
        link_to = URIRef("http://example.org/root")  # URI valide

        result_graph_uri = SEGRAPH_scrap(
            keywords, link_to, nb_results=3, response_override=self.valid_links
        )  # Appel de la fonction SEGRAPH_scrap avec les liens valides
        named_graph = store.get_context(result_graph_uri)  # Récupère le graphe nommé

        self.assertEqual(len(named_graph), 3, "Le graphe nommé doit contenir 3 liens.")  # Vérifie que le graphe contient 3 liens
        for link in self.valid_links:
            self.assertTrue(
                (link_to, URIRef("http://example.org/has_uri"), URIRef(link)) in named_graph,
                f"Le lien {link} devrait être présent dans le graphe.",
            )  # Vérifie que chaque lien est présent dans le graphe

    def test_empty_links(self):
        """Test avec une recherche ne renvoyant aucun résultat."""
        keywords = "no results keywords"  # Mots-clés de test
        link_to = URIRef("http://example.org/root")  # URI valide

        result_graph_uri = SEGRAPH_scrap(
            keywords, link_to, nb_results=5, response_override=self.empty_links
        )  # Appel de la fonction SEGRAPH_scrap avec aucun résultat
        named_graph = store.get_context(result_graph_uri)  # Récupère le graphe nommé

        self.assertEqual(len(named_graph), 0, "Le graphe nommé doit être vide.")  # Vérifie que le graphe est vide

    def test_existing_graph(self):
        """Test avec un graphe existant."""
        keywords = "existing graph"  # Mots-clés de test
        link_to = URIRef("http://example.org/root")  # URI valide
        graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())  # URI du graphe existant

        # Simuler un graphe existant
        store.get_context(graph_uri).add(
            (link_to, URIRef("http://example.org/has_uri"), URIRef("http://example.org/existing_link"))
        )  # Ajoute un triplet au graphe existant

        result_graph_uri = SEGRAPH_scrap(keywords, link_to, nb_results=5)  # Appel de la fonction SEGRAPH_scrap avec le graphe existant
        self.assertEqual(
            result_graph_uri,
            graph_uri,
            "Le même URI de graphe doit être retourné si le graphe existe déjà.",
        )  # Vérifie que le même URI de graphe est retourné
        named_graph = store.get_context(result_graph_uri)  # Récupère le graphe nommé
        self.assertEqual(
            len(named_graph), 1, "Le graphe existant ne doit pas être modifié."
        )  # Vérifie que le graphe existant n'est pas modifié

    def test_nb_results_limit(self):
        """Test avec un nombre de résultats limité."""
        keywords = "limited results"  # Mots-clés de test
        link_to = URIRef("http://example.org/root")  # URI valide

        result_graph_uri = SEGRAPH_scrap(
            keywords, link_to, nb_results=2, response_override=self.valid_links
        )  # Appel de la fonction SEGRAPH_scrap avec un nombre limité de résultats
        named_graph = store.get_context(result_graph_uri)  # Récupère le graphe nommé

        self.assertEqual(len(named_graph), 2, "Le graphe nommé doit contenir 2 liens.")  # Vérifie que le graphe contient 2 liens
        for link in self.valid_links[:2]:
            self.assertTrue(
                (link_to, URIRef("http://example.org/has_uri"), URIRef(link)) in named_graph,
                f"Le lien {link} devrait être présent dans le graphe.",
            )  # Vérifie que chaque lien est présent dans le graphe

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
