# Importation des modules nécessaires
import unittest
from unittest.mock import MagicMock, patch
from rdflib import URIRef, Literal
from rdflib.namespace import XSD
from SPARQLLM.udf.recurse import recurse, testrec
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.segraph_scrap import named_graph_exists


class TestRecurseFunctions(unittest.TestCase):
    """
    Classe de tests unitaires pour les fonctions `recurse` et `testrec` du module `recurse`.
    """

    def setUp(self):
        """
        Configuration initiale avant chaque test.
        Réinitialise le store RDF et configure les mocks nécessaires.
        """
        # Réinitialiser le store RDF avant chaque test
        self.store = store
        for graph in self.store.contexts():  # Vider tous les graphes nommés
            graph.remove((None, None, None))

        # Simuler le comportement de `named_graph_exists`
        patcher_named_graph_exists = patch('SPARQLLM.udf.recurse.named_graph_exists', return_value=False)
        self.mock_named_graph_exists = patcher_named_graph_exists.start()
        self.addCleanup(patcher_named_graph_exists.stop)  # S'assure que le patch est arrêté après les tests

        # Simuler le logger pour capturer les logs
        self.mock_logger = patch('SPARQLLM.udf.recurse.rec_logger')
        self.mock_logger.start()
        self.addCleanup(self.mock_logger.stop)  # S'assure que le patch est arrêté après les tests

    def test_recurse_valid(self):
        """
        Test du fonctionnement normal de la fonction `recurse`.
        Vérifie que la fonction retourne correctement l'URI du graphe contenant les relations.
        """
        mock_query_result = [
            {'gout': URIRef("http://example.org/graph1")},
            {'gout': URIRef("http://example.org/graph2")},
        ]
        self.store.query = MagicMock(return_value=mock_query_result)  # Simule une requête SPARQL réussie

        query_str = "SELECT ?gout WHERE { ... }"  # Requête SPARQL fictive
        gin = "gin_variable"  # Variable SPARQL fictive
        ginit = URIRef("http://example.org/init_graph")  # URI du graphe initial
        result = recurse(query_str, gin, ginit, max_depth=2)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être un URIRef
        self.assertEqual(str(result), "http://example.org/allg")  # L'URI du graphe doit être correct

    def test_recurse_named_graph_exists(self):
        """
        Test lorsque le graphe nommé existe déjà.
        Vérifie que la fonction retourne `None` si le graphe existe déjà.
        """
        self.mock_named_graph_exists.return_value = True  # Simule un graphe existant

        query_str = "SELECT ?gout WHERE { ... }"  # Requête SPARQL fictive
        gin = "gin_variable"  # Variable SPARQL fictive
        ginit = URIRef("http://example.org/init_graph")  # URI du graphe initial
        result = recurse(query_str, gin, ginit, max_depth=2)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsNone(result)  # Le résultat doit être `None` si le graphe existe déjà

    def test_recurse_exceeds_max_depth(self):
        """
        Test lorsque la profondeur maximale est atteinte.
        Vérifie que la fonction arrête la récursion lorsque la profondeur maximale est atteinte.
        """
        mock_query_result = [{'gout': URIRef("http://example.org/graph1")}]
        self.store.query = MagicMock(return_value=mock_query_result)  # Simule une requête SPARQL réussie

        query_str = "SELECT ?gout WHERE { ... }"  # Requête SPARQL fictive
        gin = "gin_variable"  # Variable SPARQL fictive
        ginit = URIRef("http://example.org/init_graph")  # URI du graphe initial
        result = recurse(query_str, gin, ginit, max_depth=0)  # Appel de la fonction à tester avec une profondeur maximale de 0

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être un URIRef
        self.assertEqual(str(result), "http://example.org/allg")  # L'URI du graphe doit être correct

    def test_recurse_exception_handling(self):
        """
        Test du comportement lorsque la fonction lève une exception.
        Vérifie que la fonction gère correctement les erreurs et retourne un graphe vide.
        """
        self.store.query = MagicMock(side_effect=Exception("Mocked SPARQL error"))  # Simule une exception lors de la requête SPARQL

        query_str = "SELECT ?gout WHERE { ... }"  # Requête SPARQL fictive
        gin = "gin_variable"  # Variable SPARQL fictive
        ginit = URIRef("http://example.org/init_graph")  # URI du graphe initial
        result = recurse(query_str, gin, ginit, max_depth=2)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être un URIRef
        self.assertEqual(str(result), "http://example.org/allg")  # L'URI du graphe doit être correct

    def test_testrec(self):
        """
        Test de la fonction `testrec`.
        Vérifie que la fonction exécute correctement une requête SPARQL et affiche les résultats.
        """
        mock_query_result = MagicMock(vars=["max_s"], __iter__=lambda x: iter([{"max_s": Literal(42)}]))
        self.store.query = MagicMock(return_value=mock_query_result)  # Simule une requête SPARQL réussie

        with patch('builtins.print') as mock_print:  # Capture les appels à `print`
            testrec()  # Appel de la fonction à tester

        # Vérifications
        self.store.query.assert_called_once()  # Vérifie que la requête SPARQL est exécutée
        mock_print.assert_any_call("max_s: 42")  # Vérifie que le résultat est affiché

    def test_testrec_no_results(self):
        """
        Test de `testrec` avec aucun résultat retourné par la requête SPARQL.
        Vérifie que la fonction ne tente pas d'afficher de résultats en l'absence de données.
        """
        mock_query_result = MagicMock(vars=[], __iter__=lambda x: iter([]))  # Simule une requête SPARQL sans résultats
        self.store.query = MagicMock(return_value=mock_query_result)

        with patch('builtins.print') as mock_print:  # Capture les appels à `print`
            testrec()  # Appel de la fonction à tester

        # Vérifications
        self.store.query.assert_called_once()  # Vérifie que la requête SPARQL est exécutée
        mock_print.assert_not_called()  # Vérifie que rien n'est affiché en l'absence de résultats


# Exécution des tests unitaires
if __name__ == "__main__":
    unittest.main()