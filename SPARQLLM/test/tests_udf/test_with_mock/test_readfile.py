import unittest
from unittest.mock import patch, mock_open, MagicMock
from rdflib import Literal
from rdflib.namespace import XSD
from SPARQLLM.udf.readfile import readhtmlfile


class TestReadHtmlFile(unittest.TestCase):
    def setUp(self):
        self.max_size = 100
        self.path_uri = "file:///mocked/path/to/file.html"

    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())
    @patch("builtins.open", new_callable=mock_open, read_data="<html><body><h1>Hello, World!</h1></body></html>")
    def test_valid_html_file(self, mock_file, mock_config):
        result = readhtmlfile(self.path_uri, self.max_size)
        expected = Literal("Hello, World!", datatype=XSD.string)
        self.assertEqual(result, expected)

    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())
    @patch("builtins.open", new_callable=mock_open, read_data="")
    def test_empty_html_file(self, mock_file, mock_config):
        result = readhtmlfile(self.path_uri, self.max_size)
        expected = Literal("", datatype=XSD.string)
        self.assertEqual(result, expected)

    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="<html><body><h1>Hello, World!</h1><a href='#'>Link</a></body></html>",
    )
    def test_html_with_links(self, mock_file, mock_config):
        """
        Test avec un fichier HTML contenant des liens.
        """
        result = readhtmlfile(self.path_uri, self.max_size)
        # La sortie attendue ne doit contenir que le texte propre sans liens
        expected = Literal("Hello, World!", datatype=XSD.string)
        self.assertEqual(result, expected)




    @patch("SPARQLLM.udf.readfile.ConfigSingleton", return_value=MagicMock())
    @patch("builtins.open", new_callable=mock_open, read_data="<html><body><h1>Hello, &nbsp;World!</h1></body></html>")
    def test_html_with_special_characters(self, mock_file, mock_config):
        result = readhtmlfile(self.path_uri, self.max_size)
        expected = Literal("Hello, World!", datatype=XSD.string)
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
