import unittest
from unittest.mock import patch, MagicMock
from rdflib import URIRef, Dataset, Literal
from rdflib.namespace import XSD
from SPARQLLM.udf.readdir import RDIR
from SPARQLLM.udf.SPARQLLM import store
import logging

# Logger pour le fichier de test
test_logger = logging.getLogger("test_readdir")
test_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
test_logger.addHandler(handler)


class TestRDIRFunction(unittest.TestCase):
    def setUp(self):
        """
        Prépare un graphe RDF pour les tests.
        """
        global store
        store = Dataset()
        self.test_dir = "file:///mocked/dir"
        self.test_graph_uri = URIRef(self.test_dir)
        self.test_graph = store.get_context(self.test_graph_uri)

    @patch('SPARQLLM.udf.readdir.list_directory_content', return_value=["file1.txt", "file2.txt"])
    @patch('SPARQLLM.udf.readdir.add_triples_to_graph')
    def test_rdir_with_valid_directory(self, mock_add_triples, mock_listdir):
        """
        Test avec un répertoire valide contenant plusieurs fichiers.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))

        # Vérifie que RDIR retourne le bon URI
        self.assertEqual(result, self.test_graph_uri)

        # Vérifie que les fonctions internes ont été appelées correctement
        mock_listdir.assert_called_once_with('/mocked/dir')
        mock_add_triples.assert_called_once()

        # Vérifie le contenu attendu dans les triplets
        expected_calls = [
            ((self.test_graph, URIRef("http://example.org/root"), "/mocked/dir", ["file1.txt", "file2.txt"]),)
        ]
        mock_add_triples.assert_has_calls(expected_calls)

    @patch('SPARQLLM.udf.readdir.named_graph_exists', return_value=True)
    def test_rdir_with_existing_graph(self, mock_named_graph_exists):
        """
        Test avec un graphe nommé existant.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))
        self.assertIsNone(result)

    @patch('SPARQLLM.udf.readdir.os.listdir', return_value=[])
    def test_rdir_with_empty_directory(self, mock_listdir):
        """
        Test avec un répertoire vide.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))
        self.assertEqual(result, self.test_graph_uri)
        self.assertEqual(len(list(self.test_graph)), 0)


if __name__ == "__main__":
    unittest.main()
