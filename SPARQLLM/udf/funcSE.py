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

headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def BS4(uri):
    config = ConfigSingleton()
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])
    truncate = int(config.config['Requests']['SLM-TRUNCATE'])

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


# Carefull to return the good types !!
def Google(keywords):
    config = ConfigSingleton()
    se_url = config.config['Requests']['SLM-CUSTOM-SEARCH-URL'].format(se_cx_key=se_cx_key,se_api_key=se_api_key)

    logger.debug(f"search: {keywords}, se_url: {se_url}")    
#    se_url=f"https://customsearch.googleapis.com/customsearch/v1?cx={se_cx_key}&key={se_api_key}"

    # Send the request to Google search
    se_url = f"{se_url}&q={quote(keywords)}"
    # print(f"se_url={se_url}")
    headers = {'Accept': 'application/json'}
    request = Request(se_url, headers=headers)
    response = urlopen(request)
    json_data = json.loads(response.read().decode('utf-8'))

    # Extract the URLs from the response
    links = [item['link'] for item in json_data.get('items', [])]
    return URIRef(links[0]) 

# run with : python -m SPARQLLM.udf.funcSE
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/BS4"), BS4)
    register_custom_function(URIRef("http://example.org/Google"), Google)

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("univ nantes", datatype=XSD.string)))  

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value))) AS ?result)
    }
    """

    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("Je veux savoir le nombre d'étudiants à UNIV ","UNIV",STR(?value))) AS ?uri)
        BIND(ex:BS4(?uri) AS ?result)
    }
    """
    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)
