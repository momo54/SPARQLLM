import unittest
from unittest.mock import patch, MagicMock
from rdflib import URIRef, Dataset, Literal
from rdflib.namespace import XSD
from SPARQLLM.udf.readdir import RDIR, gettype, list_directory_content, add_triples_to_graph
from SPARQLLM.udf.SPARQLLM import store
import logging
import os
from pathlib import Path

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

    @patch('SPARQLLM.udf.readdir.os.listdir', side_effect=OSError("Permission denied"))
    def test_rdir_with_directory_error(self, mock_listdir):
        """Test avec une erreur d'accès au répertoire."""
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))
        self.assertIsInstance(result, Literal)
        self.assertEqual(result, Literal("Error retrieving file:///mocked/dir"))

    @patch('SPARQLLM.udf.readdir.named_graph_exists', return_value=False)
    @patch('SPARQLLM.udf.readdir.add_triples_to_graph', side_effect=Exception("Graph error"))
    def test_rdir_with_triples_add_error(self, mock_add_triples, mock_named_graph_exists):
        """Test avec une erreur lors de l'ajout des triplets au graphe."""
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))
        self.assertIsInstance(result, Literal)
        self.assertEqual(result, Literal("Error retrieving file:///mocked/dir"))

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=True)
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=False)
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=False)
    def test_gettype_with_file(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'file'"""
        path = "/mocked/dir/file1.txt"
        result = gettype(path)
        self.assertEqual(result, Literal('file', datatype=XSD.string))

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=False)
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=True)
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=False)
    def test_gettype_with_directory(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'directory'"""
        path = "/mocked/dir/directory1"
        result = gettype(path)
        self.assertEqual(result, Literal('directory', datatype=XSD.string))

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=False)
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=False)
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=True)
    def test_gettype_with_symlink(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'symlink'"""
        path = "/mocked/dir/symlink1"
        result = gettype(path)
        self.assertEqual(result, Literal('symlink', datatype=XSD.string))

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=False)
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=False)
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=False)
    def test_gettype_with_unknown(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'unknown'"""
        path = "/mocked/dir/unknown1"
        result = gettype(path)
        self.assertEqual(result, Literal('unknown', datatype=XSD.string))

    @patch('SPARQLLM.udf.readdir.os.listdir')
    def test_list_directory_content_permission_error(self, mock_listdir):
        """Test de la gestion des erreurs dans list_directory_content avec une permission refusée"""
        
        # Simuler une erreur d'accès au répertoire
        mock_listdir.side_effect = OSError("Permission denied")
        
        with self.assertRaises(OSError):  # Vérifier que l'exception est bien levée
            list_directory_content("/mocked/dir")



if __name__ == "__main__":
    unittest.main()
