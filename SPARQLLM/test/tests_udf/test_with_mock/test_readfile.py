import unittest  # Importation du module unittest pour les tests unitaires
from unittest.mock import patch, mock_open, MagicMock  # Importation des fonctions de mocking
from rdflib import Literal  # Importation de la classe Literal du module rdflib
from rdflib.namespace import XSD  # Importation du namespace XSD de rdflib
from SPARQLLM.udf.readfile import readhtmlfile  # Importation de la fonction readhtmlfile du module readfile

class TestReadHtmlFile(unittest.TestCase):  # Définition de la classe de test pour la fonction readhtmlfile
    def setUp(self):
        """
        Configuration initiale avant chaque test.
        """
        self.max_size = 100  # Définition de la taille maximale
        self.path_uri = "file:///mocked/path/to/file.html"  # Définition de l'URI du fichier

    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())  # Mock de ConfigSingleton
    @patch("builtins.open", new_callable=mock_open, read_data="<html><body><h1>Hello, World!</h1></body></html>")  # Mock de la fonction open
    def test_valid_html_file(self, mock_file, mock_config):
        """
        Test avec un fichier HTML valide.
        """
        result = readhtmlfile(self.path_uri, self.max_size)  # Appel de la fonction readhtmlfile avec l'URI et la taille maximale
        expected = Literal("Hello, World!", datatype=XSD.string)  # Résultat attendu
        self.assertEqual(result, expected)  # Vérification que le résultat est égal au résultat attendu

    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())  # Mock de ConfigSingleton
    @patch("builtins.open", new_callable=mock_open, read_data="")  # Mock de la fonction open avec un fichier vide
    def test_empty_html_file(self, mock_file, mock_config):
        """
        Test avec un fichier HTML vide.
        """
        result = readhtmlfile(self.path_uri, self.max_size)  # Appel de la fonction readhtmlfile avec l'URI et la taille maximale
        expected = Literal("", datatype=XSD.string)  # Résultat attendu
        self.assertEqual(result, expected)  # Vérification que le résultat est égal au résultat attendu

    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())  # Mock de ConfigSingleton
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="<html><body><h1>Hello, World!</h1><a href='#'>Link</a></body></html>",
    )  # Mock de la fonction open avec un fichier HTML contenant des liens
    def test_html_with_links(self, mock_file, mock_config):
        """
        Test avec un fichier HTML contenant des liens.
        """
        result = readhtmlfile(self.path_uri, self.max_size)  # Appel de la fonction readhtmlfile avec l'URI et la taille maximale
        # La sortie attendue ne doit contenir que le texte propre sans liens
        expected = Literal("Hello, World!", datatype=XSD.string)  # Résultat attendu
        self.assertEqual(result, expected)  # Vérification que le résultat est égal au résultat attendu

    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())  # Mock de ConfigSingleton
    @patch("builtins.open", new_callable=mock_open, read_data="<html><body><h1>Hello, &nbsp;World!</h1></body></html>")  # Mock de la fonction open avec un fichier HTML contenant des caractères spéciaux
    def test_html_with_special_characters(self, mock_file, mock_config):
        """
        Test avec un fichier HTML contenant des caractères spéciaux.
        """
        result = readhtmlfile(self.path_uri, self.max_size)  # Appel de la fonction readhtmlfile avec l'URI et la taille maximale
        expected = Literal("Hello, World!", datatype=XSD.string)  # Résultat attendu
        self.assertEqual(result, expected)  # Vérification que le résultat est égal au résultat attendu
        
    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())  # Mock ConfigSingleton
    @patch("builtins.open", new_callable=mock_open, read_data="<html><body><h1>" + ("Test " * 100) + "</h1></body></html>")
    def test_file_exceeds_max_size(self, mock_file, mock_config):
        """
        Test avec un fichier HTML dont le contenu dépasse la taille maximale autorisée.
        """
        file_path = "file:///tmp/test_large.html"
        result = readhtmlfile(file_path, 20)

        # Vérifiez que le contenu est tronqué à la taille maximale
        self.assertIsInstance(result, Literal)
        self.assertTrue(len(result.value) <= 20, "Le contenu devrait être tronqué à max_size.")

        
    def test_non_html_file(self):
        """
        Test avec un fichier qui n'est pas au format HTML.
        """
        non_html_content = "This is plain text, not HTML."
        file_path = "file:///tmp/test.txt"

        with patch("builtins.open", mock_open(read_data=non_html_content)):
            result = readhtmlfile(file_path, 100)

        # Vérifiez que le contenu brut est traité comme du texte
        self.assertIsInstance(result, Literal)
        self.assertIn("This is plain text", result.value)
        
    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())  # Mock de ConfigSingleton
    def test_file_not_found(self, mock_config):
        """
        Test avec un chemin de fichier inexistant.
        """
        file_path = "file:///tmp/nonexistent.html"

        # Simuler une erreur FileNotFoundError
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = readhtmlfile(file_path, 100)

        self.assertIsInstance(result, Literal)
        self.assertIn("Error reading", result.value)

        
    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())  # Mock ConfigSingleton
    def test_non_html_file(self, mock_config):
        """
        Test avec un fichier qui n'est pas au format HTML.
        """
        non_html_content = "This is plain text, not HTML."
        file_path = "file:///tmp/test.txt"

        with patch("builtins.open", mock_open(read_data=non_html_content)):
            result = readhtmlfile(file_path, 100)

        # Vérifiez que le contenu brut est traité comme du texte
        self.assertIsInstance(result, Literal)
        self.assertIn("This is plain text", result.value)




if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
