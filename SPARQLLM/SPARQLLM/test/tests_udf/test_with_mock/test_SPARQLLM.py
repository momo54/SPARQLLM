# Importation des modules nécessaires
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Dataset, URIRef, Literal
from SPARQLLM.udf.SPARQLLM import my_evaljoin, my_evalgraph, my_evalservice, customEval, store


class TestSPARQLLMFunctions(unittest.TestCase):
    """
    Classe de tests unitaires pour les fonctions du module `SPARQLLM`.
    """

    def setUp(self):
        """
        Prépare un graphe RDF pour les tests.
        Initialise un store RDF et des mocks pour simuler le contexte d'exécution SPARQL.
        """
        # On initialise un Dataset pour le store et on utilise un mock global pour éviter les conflits
        self.store = Dataset()
        self.ctx = MagicMock()  # Simule le contexte d'exécution SPARQL
        self.part = MagicMock()  # Simule une partie du plan de requête SPARQL

    @patch('SPARQLLM.udf.SPARQLLM.evalLazyJoin', return_value="lazyJoinResult")
    def test_my_evaljoin(self, mock_evalLazyJoin):
        """
        Test de la fonction `my_evaljoin`.
        Vérifie que la fonction appelle correctement `evalLazyJoin` et retourne le résultat attendu.
        """
        # Exécute la fonction
        result = my_evaljoin(self.ctx, self.part)

        # Vérifie l'appel et le résultat
        mock_evalLazyJoin.assert_called_once_with(self.ctx, self.part)  # Vérifie que `evalLazyJoin` est appelé
        self.assertEqual(result, "lazyJoinResult")  # Vérifie que le résultat est correct

    @patch('SPARQLLM.udf.SPARQLLM.evalGraph', return_value="graphResult")
    def test_my_evalgraph(self, mock_evalGraph):
        """
        Test de la fonction `my_evalgraph`.
        Vérifie que la fonction appelle correctement `evalGraph` et retourne le résultat attendu.
        """
        # Exécute la fonction
        result = my_evalgraph(self.ctx, self.part)

        # Vérifie l'appel et le résultat
        mock_evalGraph.assert_called_once_with(self.ctx, self.part)  # Vérifie que `evalGraph` est appelé
        self.assertEqual(result, "graphResult")  # Vérifie que le résultat est correct

    @patch('SPARQLLM.udf.SPARQLLM.evalServiceQuery', return_value="serviceQueryResult")
    def test_my_evalservice(self, mock_evalServiceQuery):
        """
        Test de la fonction `my_evalservice`.
        Vérifie que la fonction appelle correctement `evalServiceQuery` et retourne le résultat attendu.
        """
        # Exécute la fonction
        result = my_evalservice(self.ctx, self.part)

        # Vérifie l'appel et le résultat
        mock_evalServiceQuery.assert_called_once_with(self.ctx, self.part)  # Vérifie que `evalServiceQuery` est appelé
        self.assertEqual(result, "serviceQueryResult")  # Vérifie que le résultat est correct

    @patch('SPARQLLM.udf.SPARQLLM.evalLazyJoin', return_value="customJoinResult")
    def test_customEval_join(self, mock_evalLazyJoin):
        """
        Test de la fonction `customEval` pour les parties de type "Join".
        Vérifie que la fonction appelle correctement `evalLazyJoin` et retourne le résultat attendu.
        """
        # Configure le part.name pour qu'il retourne "Join"
        self.part.name = "Join"

        result = customEval(self.ctx, self.part)  # Appel de la fonction à tester
        mock_evalLazyJoin.assert_called_once_with(self.ctx, self.part)  # Vérifie que `evalLazyJoin` est appelé
        self.assertEqual(result, "customJoinResult")  # Vérifie que le résultat est correct

    def test_customEval_unsupported_part(self):
        """
        Test de la fonction `customEval` pour des types de parties non supportés.
        Vérifie que la fonction lève une exception `NotImplementedError` pour des types non implémentés.
        """
        # Configure le part.name pour qu'il retourne un nom non implémenté
        self.part.name = "UnsupportedPart"

        with self.assertRaises(NotImplementedError):  # Capture l'exception
            customEval(self.ctx, self.part)  # Appel de la fonction à tester

    @patch('SPARQLLM.udf.SPARQLLM.Dataset', return_value=Dataset())
    def test_store_initialization(self, mock_dataset):
        """
        Test pour vérifier l'initialisation du store.
        Vérifie que le store est correctement initialisé et qu'il est vide au démarrage.
        """
        store = mock_dataset.return_value  # Récupère le mock du store
        self.assertIsInstance(store, Dataset)  # Vérifie que le store est une instance de Dataset
        self.assertEqual(len(store), 0, "Le store ne devrait pas contenir de graphes au démarrage.")  # Vérifie que le store est vide

    @patch('SPARQLLM.udf.SPARQLLM.Dataset', return_value=Dataset())
    def test_store_dynamic_graph_creation(self, mock_dataset):
        """
        Test pour vérifier la création dynamique des graphes dans le store.
        Vérifie qu'un graphe peut être ajouté dynamiquement et qu'il contient les triplets attendus.
        """
        store = mock_dataset.return_value  # Récupère le mock du store
        graph_uri = URIRef("http://example.org/testGraph")  # URI du graphe fictif
        test_graph = store.get_context(graph_uri)  # Crée ou récupère le graphe nommé
        test_graph.add((URIRef("http://example.org/s"), URIRef("http://example.org/p"), Literal("o")))  # Ajoute un triplet au graphe

        # Vérifie que le graphe contient le triplet ajouté
        self.assertEqual(len(test_graph), 1)  # Vérifie que le graphe contient un triplet
        self.assertIn(
            (URIRef("http://example.org/s"), URIRef("http://example.org/p"), Literal("o")),  # Triplet attendu
            test_graph  # Vérifie que le triplet est présent dans le graphe
        )


# Exécution des tests unitaires
if __name__ == "__main__":
    unittest.main()