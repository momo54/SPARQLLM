import unittest
from SPARQLLM.udf.filter_html import filter_html

from bs4 import BeautifulSoup

class TestFilterHTML(unittest.TestCase):

    def normalize_html(self, html):
        """Normaliser le HTML en le parsant avec BeautifulSoup pour uniformiser l'indentation."""
        soup = BeautifulSoup(html, 'html.parser')
        return soup.prettify()

    def test_filter_head(self):
        """Test que le filtre sur <head> fonctionne correctement."""
        html_input = """
        <html>
            <head>
                <title>Test Title</title>
                <meta name="description" content="Test Description">
                <meta name="author" content="Test Author">
                <script>alert('Not needed');</script>
                <style>.not-needed {}</style>
            </head>
            <body>
                <p>Test Body</p>
            </body>
        </html>
        """
        expected_output = """
        <html>
            <head>
                <title>Test Title</title>
                <meta name="description" content="Test Description">
                <meta name="author" content="Test Author">
            </head>
            <body>
                <p>Test Body</p>
            </body>
        </html>
        """
        result = filter_html(lambda x: x, html_input)
        self.assertEqual(
            self.normalize_html(str(result)),
            self.normalize_html(expected_output)
        )

    def test_filtrer_body(self):
        """Test que le filtre sur <body> fonctionne correctement."""
        html_input = """
        <html>
            <head>
                <title>Test Title</title>
            </head>
            <body>
                <script>alert('Not needed');</script>
                <noscript>Not needed either</noscript>
                <p>Keep this</p>
                <style>.not-needed {}</style>
                <iframe src="not-needed"></iframe>
            </body>
        </html>
        """
        expected_output = """
        <html>
            <head>
                <title>Test Title</title>
            </head>
            <body>
                <p>Keep this</p>
            </body>
        </html>
        """
        result = filter_html(lambda x: x, html_input)
        self.assertEqual(
            self.normalize_html(str(result)),
            self.normalize_html(expected_output)
        )

    def test_no_head_or_body(self):
        """Test que le comportement est correct si head ou body est manquant."""
        html_input = "<html></html>"
        result = filter_html(lambda x: x, html_input)
        self.assertEqual(
            self.normalize_html(str(result)),
            self.normalize_html(html_input)
        )


    def test_empty_html(self):
        """Test que le code HTML vide est géré correctement."""
        html_input = ""
        result = filter_html(lambda x: x, html_input)
        self.assertEqual(
            self.normalize_html(str(result)),
            self.normalize_html(html_input)
        )


if __name__ == '__main__':
    unittest.main()
