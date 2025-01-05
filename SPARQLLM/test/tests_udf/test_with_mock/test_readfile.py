# Importation des modules nécessaires
import unittest
from unittest.mock import patch, MagicMock
from rdflib import URIRef, Dataset, Literal
from rdflib.namespace import XSD
from SPARQLLM.udf.readdir import RDIR
from SPARQLLM.udf.SPARQLLM import store
import logging

# Configuration du logger pour le fichier de test
test_logger = logging.getLogger("test_readdir")
test_logger.setLevel(logging.DEBUG)  # Niveau de log : DEBUG
handler = logging.StreamHandler()  # Gestionnaire pour afficher les logs dans la console
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')  # Format des logs
handler.setFormatter(formatter)
test_logger.addHandler(handler)  # Ajout du gestionnaire au logger


class TestRDIRFunction(unittest.TestCase):
    """
    Classe de tests unitaires pour la fonction `RDIR` qui parcourt un répertoire et ajoute des métadonnées RDF.
    """

    def setUp(self):
        """
        Prépare un graphe RDF pour les tests.
        Initialise un store RDF et un graphe nommé pour simuler l'environnement de test.
        """
        global store
        store = Dataset()  # Création d'un store RDF vide
        self.test_dir = "file:///mocked/dir"  # Répertoire fictif pour les tests
        self.test_graph_uri = URIRef(self.test_dir)  # URI du graphe nommé
        self.test_graph = store.get_context(self.test_graph_uri)  # Récupération du graphe nommé

    @patch('SPARQLLM.udf.readdir.list_directory_content', return_value=["file1.txt", "file2.txt"])
    @patch('SPARQLLM.udf.readdir.add_triples_to_graph')
    def test_rdir_with_valid_directory(self, mock_add_triples, mock_listdir):
        """
        Test avec un répertoire valide contenant plusieurs fichiers.
        Vérifie que la fonction `RDIR` ajoute correctement les triplets RDF pour les fichiers du répertoire.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction à tester

        # Vérifie que RDIR retourne le bon URI
        self.assertEqual(result, self.test_graph_uri)

        # Vérifie que les fonctions internes ont été appelées correctement
        mock_listdir.assert_called_once_with('/mocked/dir')  # Vérifie que `list_directory_content` est appelé avec le bon chemin
        mock_add_triples.assert_called_once()  # Vérifie que `add_triples_to_graph` est appelé une fois

        # Vérifie le contenu attendu dans les triplets
        expected_calls = [
            ((self.test_graph, URIRef("http://example.org/root"), "/mocked/dir", ["file1.txt", "file2.txt"]),)
        ]
        mock_add_triples.assert_has_calls(expected_calls)  # Vérifie les arguments passés à `add_triples_to_graph`

    @patch('SPARQLLM.udf.readdir.named_graph_exists', return_value=True)
    def test_rdir_with_existing_graph(self, mock_named_graph_exists):
        """
        Test avec un graphe nommé existant.
        Vérifie que la fonction `RDIR` ne crée pas de nouveau graphe si un graphe existe déjà pour le répertoire.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction à tester
        self.assertIsNone(result)  # Vérifie que la fonction retourne `None` si le graphe existe déjà

    @patch('SPARQLLM.udf.readdir.os.listdir', return_value=[])
    def test_rdir_with_empty_directory(self, mock_listdir):
        """
        Test avec un répertoire vide.
        Vérifie que la fonction `RDIR` gère correctement un répertoire vide.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction à tester
        self.assertEqual(result, self.test_graph_uri)  # Vérifie que l'URI du graphe est retourné
        self.assertEqual(len(list(self.test_graph)), 0)  # Vérifie que le graphe est vide


# Exécution des tests unitaires
if __name__ == "__main__":
    unittest.main()