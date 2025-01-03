# Importation des modules nécessaires
import unittest
from unittest.mock import MagicMock, patch
from rdflib import URIRef, Dataset
from rdflib.namespace import XSD
from SPARQLLM.udf.segraph import SEGRAPH, add_links_to_graph, fetch_links_from_api, generate_graph_uri, validate_arguments
from SPARQLLM.udf.SPARQLLM import store
import json
import hashlib
import logging

# Configuration du logger pour les tests
logging.basicConfig(level=logging.DEBUG)
test_logger = logging.getLogger("test_segraph")


class TestSEGRAPHFunction(unittest.TestCase):
    """
    Classe de tests unitaires pour la fonction `SEGRAPH` qui effectue une recherche via l'API Google et stocke les résultats dans un graphe RDF.
    """

    def setUp(self):
        """
        Prépare un graphe RDF pour les tests.
        Initialise les variables communes utilisées dans les tests.
        """
        self.keywords = "university nantes"  # Mots-clés fictifs
        self.link_to = URIRef("http://example.org/root")  # URI cible fictive
        self.graph_uri = URIRef("http://google.com/" + hashlib.sha256(self.keywords.encode()).hexdigest())  # Calcul de l'URI du graphe

    @patch('SPARQLLM.udf.segraph.fetch_links_from_api')
    def test_segraph_with_results(self, mock_fetch_links):
        """
        Test de la fonction `SEGRAPH` avec des résultats valides.
        Vérifie que les liens sont correctement ajoutés au graphe RDF.
        """
        mock_fetch_links.return_value = ["http://example.com/link1", "http://example.com/link2"]  # Simule des résultats de recherche

        result = SEGRAPH(self.keywords, self.link_to)  # Appel de la fonction à tester
        named_graph = store.get_context(result)  # Récupération du graphe nommé

        # Vérifications
        self.assertEqual(result, self.graph_uri)  # L'URI du graphe doit être correcte
        self.assertGreater(len(named_graph), 0, "Le graphe nommé est vide après SEGRAPH.")  # Le graphe ne doit pas être vide

        # Vérifie que les triplets attendus sont présents dans le graphe
        expected_triples = [
            (self.link_to, URIRef("http://example.org/has_uri"), URIRef("http://example.com/link1")),
            (self.link_to, URIRef("http://example.org/has_uri"), URIRef("http://example.com/link2")),
        ]
        for triple in expected_triples:
            self.assertIn(triple, named_graph, f"Triplet attendu manquant : {triple}")

    @patch('SPARQLLM.udf.segraph.named_graph_exists', return_value=False)
    @patch('SPARQLLM.udf.segraph.urlopen')
    def test_segraph_no_results(self, mock_urlopen, mock_named_graph_exists):
        """
        Test de la fonction `SEGRAPH` avec une réponse JSON valide mais sans résultats.
        Vérifie que le graphe reste vide en l'absence de résultats.
        """
        # Simule une réponse JSON sans items
        mock_json_response = {"items": []}
        mock_urlopen.return_value.read.return_value = json.dumps(mock_json_response).encode('utf-8')

        result = SEGRAPH(self.keywords, self.link_to)  # Appel de la fonction à tester

        # Vérifications
        self.assertEqual(result, self.graph_uri)  # L'URI du graphe doit être correcte
        named_graph = store.get_context(result)  # Récupération du graphe nommé
        self.assertEqual(len(named_graph), 0)  # Le graphe doit rester vide

    @patch('SPARQLLM.udf.segraph.named_graph_exists', return_value=True)
    def test_segraph_with_existing_graph(self, mock_named_graph_exists):
        """
        Test de la fonction `SEGRAPH` avec un graphe nommé déjà existant.
        Vérifie que la fonction retourne l'URI du graphe existant sans ajouter de nouveaux triplets.
        """
        result = SEGRAPH(self.keywords, self.link_to)  # Appel de la fonction à tester

        # Vérifications
        self.assertEqual(result, self.graph_uri)  # L'URI du graphe doit être correcte

    def test_segraph_invalid_link_to(self):
        """
        Test de la fonction `SEGRAPH` avec un deuxième argument invalide.
        Vérifie que la fonction lève une exception si `link_to` n'est pas une URIRef.
        """
        with self.assertRaises(ValueError) as context:  # Capture l'exception
            SEGRAPH(self.keywords, "invalid_link_to")  # Appel de la fonction à tester

        self.assertEqual(str(context.exception), "SEGRAPH 2nd Argument should be an URI")  # Vérifie le message d'erreur

    @patch('SPARQLLM.udf.segraph.urlopen')
    def test_segraph_http_error(self, mock_urlopen):
        """
        Test de la fonction `SEGRAPH` avec une erreur réseau.
        Vérifie que la fonction lève une exception en cas d'erreur HTTP.
        """
        # Simule une exception lors de la requête HTTP
        mock_urlopen.side_effect = Exception("HTTP Error")

        with self.assertRaises(Exception) as context:  # Capture l'exception
            SEGRAPH(self.keywords, self.link_to)  # Appel de la fonction à tester

        self.assertEqual(str(context.exception), "HTTP Error")  # Vérifie le message d'erreur

    def test_validate_arguments_valid(self):
        """
        Test de la fonction `validate_arguments` avec des arguments valides.
        Vérifie que la fonction retourne `True` si les arguments sont valides.
        """
        self.assertTrue(validate_arguments("university nantes", URIRef("http://example.org/root")))  # Appel de la fonction à tester

    def test_validate_arguments_invalid(self):
        """
        Test de la fonction `validate_arguments` avec un deuxième argument invalide.
        Vérifie que la fonction lève une exception si `link_to` n'est pas une URIRef.
        """
        with self.assertRaises(ValueError):  # Capture l'exception
            validate_arguments("university nantes", "invalid_link_to")  # Appel de la fonction à tester

    def test_generate_graph_uri(self):
        """
        Test de la fonction `generate_graph_uri`.
        Vérifie que la fonction génère correctement l'URI du graphe basée sur les mots-clés.
        """
        uri = generate_graph_uri("university nantes")  # Appel de la fonction à tester
        expected_uri = URIRef("http://google.com/" + hashlib.sha256("university nantes".encode()).hexdigest())  # Calcul de l'URI attendue
        self.assertEqual(uri, expected_uri)  # Vérifie que l'URI générée est correcte

    @patch('SPARQLLM.udf.segraph.urlopen')
    def test_fetch_links_from_api(self, mock_urlopen):
        """
        Test de la fonction `fetch_links_from_api`.
        Vérifie que la fonction extrait correctement les liens depuis une réponse JSON.
        """
        mock_json_response = {
            "items": [
                {"link": "http://example.com/link1"},
                {"link": "http://example.com/link2"}
            ]
        }
        mock_urlopen.return_value.read.return_value = json.dumps(mock_json_response).encode('utf-8')  # Simule une réponse JSON

        links = fetch_links_from_api("http://mocked_url", "university nantes", 2)  # Appel de la fonction à tester
        self.assertEqual(links, ["http://example.com/link1", "http://example.com/link2"])  # Vérifie que les liens sont corrects

    def test_add_links_to_graph(self):
        """
        Test de la fonction `add_links_to_graph`.
        Vérifie que la fonction ajoute correctement les liens au graphe RDF.
        """
        named_graph = store.get_context(URIRef("http://example.org/test"))  # Création d'un graphe nommé
        links = ["http://example.com/link1", "http://example.com/link2"]  # Liens fictifs

        add_links_to_graph(named_graph, URIRef("http://example.org/root"), links)  # Appel de la fonction à tester

        # Vérifie que les triplets attendus sont présents dans le graphe
        expected_triples = [
            (URIRef("http://example.org/root"), URIRef("http://example.org/has_uri"), URIRef("http://example.com/link1")),
            (URIRef("http://example.org/root"), URIRef("http://example.org/has_uri"), URIRef("http://example.com/link2")),
        ]
        for triple in expected_triples:
            self.assertIn(triple, named_graph)  # Vérifie que chaque triplet est présent


# Exécution des tests unitaires
if __name__ == "__main__":
    unittest.main()