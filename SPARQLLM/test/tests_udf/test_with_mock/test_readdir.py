import unittest  # Importation du module unittest pour les tests unitaires
from unittest.mock import patch, MagicMock  # Importation des fonctions de mocking
from rdflib import URIRef, Dataset, Literal  # Importation des classes URIRef, Dataset et Literal du module rdflib
from rdflib.namespace import XSD  # Importation du namespace XSD de rdflib
from SPARQLLM.udf.readdir import RDIR, gettype, list_directory_content, add_triples_to_graph  # Importation des fonctions du module readdir
from SPARQLLM.udf.SPARQLLM import store  # Importation de la variable store du module SPARQLLM
import logging  # Importation du module logging
import os  # Importation du module os
from pathlib import Path  # Importation de la classe Path du module pathlib

# Logger pour le fichier de test
test_logger = logging.getLogger("test_readdir")  # Création d'un logger pour les tests
test_logger.setLevel(logging.DEBUG)  # Définition du niveau de log
handler = logging.StreamHandler()  # Création d'un handler pour les logs
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')  # Définition du format des logs
handler.setFormatter(formatter)  # Définition du formateur pour le handler
test_logger.addHandler(handler)  # Ajout du handler au logger

class TestRDIRFunction(unittest.TestCase):  # Définition de la classe de test pour la fonction RDIR
    def setUp(self):
        """
        Prépare un graphe RDF pour les tests.
        """
        global store  # Déclaration de la variable globale store
        store = Dataset()  # Initialisation de store avec un nouveau Dataset
        self.test_dir = "file:///mocked/dir"  # Définition du répertoire de test
        self.test_graph_uri = URIRef(self.test_dir)  # Définition de l'URI du graphe de test
        self.test_graph = store.get_context(self.test_graph_uri)  # Récupération du contexte du graphe de test

    @patch('SPARQLLM.udf.readdir.list_directory_content', return_value=["file1.txt", "file2.txt"])  # Mock de la fonction list_directory_content
    @patch('SPARQLLM.udf.readdir.add_triples_to_graph')  # Mock de la fonction add_triples_to_graph
    def test_rdir_with_valid_directory(self, mock_add_triples, mock_listdir):
        """
        Test avec un répertoire valide contenant plusieurs fichiers.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction RDIR avec le répertoire de test et l'URI racine

        # Vérifie que RDIR retourne le bon URI
        self.assertEqual(result, self.test_graph_uri)  # Vérification que le résultat est égal à l'URI du graphe de test

        # Vérifie que les fonctions internes ont été appelées correctement
        mock_listdir.assert_called_once_with('/mocked/dir')  # Vérification que la fonction list_directory_content a été appelée une fois avec le bon argument
        mock_add_triples.assert_called_once()  # Vérification que la fonction add_triples_to_graph a été appelée une fois

        # Vérifie le contenu attendu dans les triplets
        expected_calls = [
            ((self.test_graph, URIRef("http://example.org/root"), "/mocked/dir", ["file1.txt", "file2.txt"]),)
        ]
        mock_add_triples.assert_has_calls(expected_calls)  # Vérification que les appels attendus ont été faits

    @patch('SPARQLLM.udf.readdir.named_graph_exists', return_value=True)  # Mock de la fonction named_graph_exists
    def test_rdir_with_existing_graph(self, mock_named_graph_exists):
        """
        Test avec un graphe nommé existant.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction RDIR avec le répertoire de test et l'URI racine
        self.assertIsNone(result)  # Vérification que le résultat est None

    @patch('SPARQLLM.udf.readdir.os.listdir', return_value=[])  # Mock de la fonction os.listdir
    def test_rdir_with_empty_directory(self, mock_listdir):
        """
        Test avec un répertoire vide.
        """
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction RDIR avec le répertoire de test et l'URI racine
        self.assertEqual(result, self.test_graph_uri)  # Vérification que le résultat est égal à l'URI du graphe de test
        self.assertEqual(len(list(self.test_graph)), 0)  # Vérification que le graphe est vide

    @patch('SPARQLLM.udf.readdir.os.listdir', side_effect=OSError("Permission denied"))  # Mock de la fonction os.listdir avec une erreur de permission
    def test_rdir_with_directory_error(self, mock_listdir):
        """Test avec une erreur d'accès au répertoire."""
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction RDIR avec le répertoire de test et l'URI racine
        self.assertIsInstance(result, Literal)  # Vérification que le résultat est une instance de Literal
        self.assertEqual(result, Literal("Error retrieving file:///mocked/dir"))  # Vérification que le résultat est égal au message d'erreur attendu

    @patch('SPARQLLM.udf.readdir.named_graph_exists', return_value=False)  # Mock de la fonction named_graph_exists
    @patch('SPARQLLM.udf.readdir.add_triples_to_graph', side_effect=Exception("Graph error"))  # Mock de la fonction add_triples_to_graph avec une exception
    def test_rdir_with_triples_add_error(self, mock_add_triples, mock_named_graph_exists):
        """Test avec une erreur lors de l'ajout des triplets au graphe."""
        result = RDIR(self.test_dir, URIRef("http://example.org/root"))  # Appel de la fonction RDIR avec le répertoire de test et l'URI racine
        self.assertIsInstance(result, Literal)  # Vérification que le résultat est une instance de Literal
        self.assertEqual(result, Literal("Error retrieving file:///mocked/dir"))  # Vérification que le résultat est égal au message d'erreur attendu

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=True)  # Mock de la méthode is_file de Path
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=False)  # Mock de la méthode is_dir de Path
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=False)  # Mock de la méthode is_symlink de Path
    def test_gettype_with_file(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'file'"""
        path = "/mocked/dir/file1.txt"  # Définition du chemin du fichier
        result = gettype(path)  # Appel de la fonction gettype avec le chemin du fichier
        self.assertEqual(result, Literal('file', datatype=XSD.string))  # Vérification que le résultat est égal à 'file'

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=False)  # Mock de la méthode is_file de Path
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=True)  # Mock de la méthode is_dir de Path
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=False)  # Mock de la méthode is_symlink de Path
    def test_gettype_with_directory(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'directory'"""
        path = "/mocked/dir/directory1"  # Définition du chemin du répertoire
        result = gettype(path)  # Appel de la fonction gettype avec le chemin du répertoire
        self.assertEqual(result, Literal('directory', datatype=XSD.string))  # Vérification que le résultat est égal à 'directory'

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=False)  # Mock de la méthode is_file de Path
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=False)  # Mock de la méthode is_dir de Path
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=True)  # Mock de la méthode is_symlink de Path
    def test_gettype_with_symlink(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'symlink'"""
        path = "/mocked/dir/symlink1"  # Définition du chemin du lien symbolique
        result = gettype(path)  # Appel de la fonction gettype avec le chemin du lien symbolique
        self.assertEqual(result, Literal('symlink', datatype=XSD.string))  # Vérification que le résultat est égal à 'symlink'

    @patch('SPARQLLM.udf.readdir.Path.is_file', return_value=False)  # Mock de la méthode is_file de Path
    @patch('SPARQLLM.udf.readdir.Path.is_dir', return_value=False)  # Mock de la méthode is_dir de Path
    @patch('SPARQLLM.udf.readdir.Path.is_symlink', return_value=False)  # Mock de la méthode is_symlink de Path
    def test_gettype_with_unknown(self, mock_is_symlink, mock_is_dir, mock_is_file):
        """Test pour vérifier la détection du type 'unknown'"""
        path = "/mocked/dir/unknown1"  # Définition du chemin de l'élément inconnu
        result = gettype(path)  # Appel de la fonction gettype avec le chemin de l'élément inconnu
        self.assertEqual(result, Literal('unknown', datatype=XSD.string))  # Vérification que le résultat est égal à 'unknown'

    @patch('SPARQLLM.udf.readdir.os.listdir')  # Mock de la fonction os.listdir
    def test_list_directory_content_permission_error(self, mock_listdir):
        """Test de la gestion des erreurs dans list_directory_content avec une permission refusée"""

        # Simuler une erreur d'accès au répertoire
        mock_listdir.side_effect = OSError("Permission denied")  # Définition de l'effet secondaire pour simuler une erreur de permission

        with self.assertRaises(OSError):  # Vérifier que l'exception est bien levée
            list_directory_content("/mocked/dir")  # Appel de la fonction list_directory_content avec le répertoire de test

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
