# Importation des modules nécessaires
import unittest
from unittest.mock import MagicMock, patch
from rdflib import URIRef, Graph
from SPARQLLM.udf.segraph_scrap import SEGRAPH_scrap
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists
import hashlib


class TestSEGRAPHScrapFunction(unittest.TestCase):
    """
    Classe de tests unitaires pour la fonction `SEGRAPH_scrap` qui effectue une recherche via un moteur de recherche et stocke les résultats dans un graphe RDF.
    """

    def setUp(self):
        """
        Configuration initiale avant chaque test.
        Réinitialise le magasin RDF et configure les mocks nécessaires.
        """
        # Réinitialiser le magasin RDF avant chaque test
        self.store = store
        for graph in self.store.contexts():  # Vider tous les graphes nommés
            graph.remove((None, None, None))

        # Simuler le logger pour capturer les logs
        self.mock_logger = patch('SPARQLLM.udf.segraph_scrap.logger')
        self.mock_logger.start()
        self.addCleanup(self.mock_logger.stop)  # S'assure que le patch est arrêté après les tests

        # Simuler le comportement de `named_graph_exists`
        patcher_named_graph_exists = patch('SPARQLLM.udf.segraph_scrap.named_graph_exists', return_value=False)
        self.mock_named_graph_exists = patcher_named_graph_exists.start()
        self.addCleanup(patcher_named_graph_exists.stop)  # S'assure que le patch est arrêté après les tests

    def test_valid_keywords_and_link_to(self):
        """
        Test avec des mots-clés valides et un lien vers une URI valide.
        Vérifie que la fonction ajoute correctement les résultats au graphe RDF.
        """
        # Simuler les résultats du moteur de recherche
        mock_results = MagicMock()
        mock_results.links.return_value = [
            "https://example.com/link1",
            "https://example.com/link2",
            "https://example.com/link3"
        ]
        with patch('SPARQLLM.udf.segraph_scrap.Google') as mock_google:  # Simule le moteur de recherche Google
            mock_google.return_value.search.return_value = mock_results

            keywords = "university nantes"  # Mots-clés fictifs
            link_to = URIRef("http://example.org/link_to")  # URI cible fictive
            result = SEGRAPH_scrap(keywords, link_to, nb_results=2)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être une URIRef
        expected_graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())  # Calcul de l'URI attendue
        self.assertEqual(result, expected_graph_uri)  # Vérifie que l'URI retournée est correcte

        named_graph = self.store.get_context(result)  # Récupération du graphe nommé
        triples = list(named_graph.triples((link_to, URIRef("http://example.org/has_uri"), None)))  # Récupération des triplets
        self.assertEqual(len(triples), 2)  # Vérifie que 2 liens sont ajoutés au graphe

    def test_existing_named_graph(self):
        """
        Test lorsque le graphe nommé existe déjà.
        Vérifie que la fonction retourne l'URI du graphe existant sans ajouter de nouveaux triplets.
        """
        self.mock_named_graph_exists.return_value = True  # Simuler un graphe existant

        keywords = "university nantes"  # Mots-clés fictifs
        link_to = URIRef("http://example.org/link_to")  # URI cible fictive
        result = SEGRAPH_scrap(keywords, link_to, nb_results=2)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être une URIRef
        expected_graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())  # Calcul de l'URI attendue
        self.assertEqual(result, expected_graph_uri)  # Vérifie que l'URI retournée est correcte

    def test_invalid_link_to(self):
        """
        Test avec un `link_to` invalide.
        Vérifie que la fonction lève une exception si `link_to` n'est pas une URIRef.
        """
        keywords = "university nantes"  # Mots-clés fictifs
        link_to = "not-a-valid-uri"  # `link_to` non valide

        with self.assertRaises(ValueError) as context:  # Capture l'exception
            SEGRAPH_scrap(keywords, link_to, nb_results=2)  # Appel de la fonction à tester

        self.assertEqual(str(context.exception), "SEGRAPH_scrap 2nd Argument should be an URI")  # Vérifie le message d'erreur

    def test_search_engine_error(self):
        """
        Test lorsque le moteur de recherche lève une exception.
        Vérifie que la fonction gère correctement les erreurs et retourne un graphe vide.
        """
        with patch('SPARQLLM.udf.segraph_scrap.Google') as mock_google:  # Simule le moteur de recherche Google
            mock_google.return_value.search.side_effect = Exception("Mocked search engine error")  # Simule une exception

            keywords = "university nantes"  # Mots-clés fictifs
            link_to = URIRef("http://example.org/link_to")  # URI cible fictive
            result = SEGRAPH_scrap(keywords, link_to, nb_results=2)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être une URIRef
        expected_graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())  # Calcul de l'URI attendue
        self.assertEqual(result, expected_graph_uri)  # Vérifie que l'URI retournée est correcte

        named_graph = self.store.get_context(result)  # Récupération du graphe nommé
        self.assertEqual(len(named_graph), 0)  # Le graphe doit rester vide

    def test_no_results_from_search_engine(self):
        """
        Test lorsque le moteur de recherche ne retourne aucun résultat.
        Vérifie que la fonction gère correctement l'absence de résultats.
        """
        mock_results = MagicMock()
        mock_results.links.return_value = []  # Aucun résultat

        with patch('SPARQLLM.udf.segraph_scrap.Google') as mock_google:  # Simule le moteur de recherche Google
            mock_google.return_value.search.return_value = mock_results

            keywords = "university nantes"  # Mots-clés fictifs
            link_to = URIRef("http://example.org/link_to")  # URI cible fictive
            result = SEGRAPH_scrap(keywords, link_to, nb_results=2)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être une URIRef
        expected_graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())  # Calcul de l'URI attendue
        self.assertEqual(result, expected_graph_uri)  # Vérifie que l'URI retournée est correcte

        named_graph = self.store.get_context(result)  # Récupération du graphe nommé
        self.assertEqual(len(named_graph), 0)  # Le graphe doit rester vide

    def test_exceeding_nb_results(self):
        """
        Test lorsque `nb_results` dépasse le nombre de liens retournés par le moteur de recherche.
        Vérifie que la fonction ajoute uniquement les résultats disponibles.
        """
        mock_results = MagicMock()
        mock_results.links.return_value = [
            "https://example.com/link1",
            "https://example.com/link2"
        ]  # Seulement 2 résultats disponibles

        with patch('SPARQLLM.udf.segraph_scrap.Google') as mock_google:  # Simule le moteur de recherche Google
            mock_google.return_value.search.return_value = mock_results

            keywords = "university nantes"  # Mots-clés fictifs
            link_to = URIRef("http://example.org/link_to")  # URI cible fictive
            result = SEGRAPH_scrap(keywords, link_to, nb_results=5)  # Demande de 5 résultats

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être une URIRef
        expected_graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())  # Calcul de l'URI attendue
        self.assertEqual(result, expected_graph_uri)  # Vérifie que l'URI retournée est correcte

        named_graph = self.store.get_context(result)  # Récupération du graphe nommé
        triples = list(named_graph.triples((link_to, URIRef("http://example.org/has_uri"), None)))  # Récupération des triplets
        self.assertEqual(len(triples), 2)  # Vérifie que seulement 2 résultats sont ajoutés


# Exécution des tests unitaires
if __name__ == "__main__":
    unittest.main()