from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key=os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key=os.environ.get("SEARCH_CX")

from bs4 import BeautifulSoup
import requests
import html
import html2text
import unidecode

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)


from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

config = ConfigSingleton()
timeout = int(config.config['Requests']['SLM-TIMEOUT'])
truncate = int(config.config['Requests']['SLM-TRUNCATE'])

headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}


def BS4(uri):
    """
        Retrieves the content of a web page using Selenium and BeautifulSoup, processes it, and returns the text as an RDF Literal.

        Args:
            uri (str): The URI of the web page to retrieve.

        Returns:
            Literal: The processed text content of the web page as an RDF Literal. If an error occurs, returns an error message as an RDF Literal.

        Raises:
            Exception: If there is an error retrieving or processing the web page content.
    """
    logger.debug(f"BS4: {uri}")
    try:
        # Set up Selenium with Chrome WebDriver
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in headless mode
        service = Service('/path/to/chromedriver')  # Update with your path to chromedriver
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Fetch the page
        driver.get(uri)
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        # Extract the page content
        page_content = driver.page_source
        driver.quit()

        h = html2text.HTML2Text()
        text = h.handle(page_content)
        text = unidecode.unidecode(text)
        return Literal(text.strip()[:truncate])

    except Exception as e:
        logger.error(f"Error retrieving {uri}: {e}")
        return Literal(f"Error retrieving {uri}")


