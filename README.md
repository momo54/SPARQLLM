SPARQLLM proposes a new technique to access external sources during SPARQL query execution.
It allows to easily run SPARQL query that can access Search Engines, Large Language Models, or Vector database. 

SPARQL-LM allows to run SPARQL queries like [this one](queries/city-search-faiss-llm.sparql) that search in Wikidata, perform a Vector Search to find URIs and extract cultural events from Uris:
```
## slm-run --config config.ini -f queries/city-search-faiss.sparql --debug
PREFIX wdt: <http://www.wikidata.org/prop/direct/>    # Propriétés directes (ex. wdt:P31 pour "instance de")
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wd: <http://www.wikidata.org/entity/>  
PREFIX ex: <http://example.org/>

SELECT ?label ?chunk ?label ?uri ?score ?date  WHERE {
    SERVICE <https://query.wikidata.org/sparql> {
        SELECT *  WHERE {
           ?country wdt:P31 wd:Q6256;  # The country (instance of a sovereign state)
           wdt:P30 wd:Q46;    # Located in Europe (Q46)
           wdt:P36 ?capital.  # Has capital
           ?capital rdfs:label ?label.
           FILTER(LANG(?label) = "en")
        } 
    } 
    BIND(CONCAT("I want a cultural event related to cinema that is located in ",STR(?label)) AS ?rag)
    BIND(ex:SLM-SEARCH-FAISS(?rag,?capital,5) AS ?gf).
    GRAPH ?gf {
        ?capital ex:is_aligned_with ?bn .
        ?bn ex:has_chunk ?chunk .
        ?bn ex:has_source ?uri .
        ?bn ex:has_score ?score .
    }
    BIND(ex:SLM-READFILE(?uri) AS ?page)   
    BIND(CONCAT("""
    We consider a type Event with the following properties:
      <http://schema.org/StartDate> : The start date of the event
      <http://schema.org/name> : The name of the event.
    Extract from the text below, the date of the event and the name of the event. 
    Generate only output JSON-LD instance of the Event type with
    this format replacing the 0 with the date of the event, and 1 with the name of the event:
     "@context": "https://schema.org/",
     "@type": "Event",
     "http://schema.org/StartDate": "0",
     "http://schema.org/name": "1",
    <page>""",STR(?page), "</page>") AS ?prompt)
    BIND(ex:SLM-LLMGRAPH_OLLA(?prompt,?uri) AS ?gl)
    GRAPH ?gl {
        ?uri <http://example.org/has_schema_type> ?root . 
        ?root a <http://schema.org/Event>. 
        ?root <http://schema.org/StartDate> ?date.
        ?root <http://schema.org/name> ?name
    }    
} order by DESC(?score) limit 10
```

with output like that:
```
       label                            uri               score              date                           name
0  Amsterdam  file:///Users/molli-p/SPAR...  15.239427663552743     21 March 2025  Cinema in Amsterdam: Switc...
1      Paris  file:///Users/molli-p/SPAR...  16.225315614252626  09 February 2025  Cinema in Paris: Distribut...
2  Amsterdam  file:///Users/molli-p/SPAR...  15.239427663552743     21 March 2025  Cinema in Amsterdam: Switc...
3     Dublin  file:///Users/molli-p/SPAR...  14.531948130739828        2025-03-30  Cinema in Dublin: Multi-la...
4   Budapest  file:///Users/molli-p/SPAR...  15.116024306274257        2025-03-11  Cinema in Budapest: Horizo...
5     Madrid  file:///Users/molli-p/SPAR...  14.380867914788142  24 February 2025  Cinema in Madrid: Open-sou...
6     Madrid  file:///Users/molli-p/SPAR...  13.516983778696542  25 February 2025  Cinema in Madrid: Realigne...
```



# install Basic Software

```
git clone https://github.com/momo54/SPARQLLM
cd SPARQLLM
```
Or  work in:
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/momo54/SPARQLLM?quickstart=1)



install with virtualenv (recommended):
```
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
pip install .
```

# Install Search, Vector and LLM capabilities

Need Ollama installed, For Linux, MacOS:
```
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.1:latest
ollama pull nomic-embed-text
```

Need index and semantic index:
```
cd data
python index_whoosh.py
python index_faiss.py
cd ..
```

# run queries

You should be able to run: `slm-run --help`
```
Usage: slm-run [OPTIONS]

Options:
  -q, --query TEXT          SPARQL query to execute (passed in command-line)
  -f, --file TEXT           File containing a SPARQL query to execute
  -c, --config TEXT         Config File for User Defined Functions
  -l, --load TEXT           RDF data file to load
  -fo, --format TEXT        Format of RDF data file
  -d, --debug               turn on debug.
  -k, --keep-store TEXT     File to store the RDF data collected during the
  -o, --output-result TEXT  File to store the result of the query query. 1
                            line per result
  --help                    Show this message and exit.
```

# Run queries working with the local file system


Run a simple queries using the local file system as external source :
```
slm-run --config config.ini -f queries/simple-csv.sparql --debug
slm-run --config config.ini -f queries/readfile.sparql --debug
slm-run --config config.ini -f queries/ReadDir.sparql --debug
```

We can read files, html-files, csv-files, directories during query processing.


# Run queries working with Search capabilities

Run a simple query with a (local) Search Engine [Whoosh](https://github.com/whoosh-community/whoosh):
```
slm-run --config config.ini -f queries/city-search.sparql --debug
```

# run queries with Search and LLms

Combine Wikidata, Vector Search and LLM in a single query [See the query](queries/city-search-faiss-llm.sparql). It is slow on codespace as there is no GPU:
```
slm-run --config config.ini -f queries/city-search-faiss-llm.sparql --debug
```

Same query with keyword search instead of vector search:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```

Keep store and replay:
```
slm-run --config config.ini -f queries/city-search-faiss-llm.sparql --keep-store city.nq
slm-run --config config.ini --load city.nq  --format nquads -f queries/city-search-faiss-llm.sparql
````

Your query can be rexecuted quickly with only local access now. 


## Working with web search engines

If you want to perform the same query on the WEB with [Google Search API](https://developers.google.com/custom-search), your custom search Google API have
to be  activated and the keys have to be available as environment variables :
```
export GOOGLE_API_KEY=xxxxxxxx_orbIQ302-4NOQhRnxxxxxxx
export GOOGLE_CX=x4x3x5x4xfxxxxxxx
```

You should be able to run the same query than before with Google
as a search engine.
```
slm-run --config config.ini -f queries/city-search.sparql --debug
```


## Working a online LLMs

If you  use MISTRAL AI, your MistralAI API key should be available as an environment variable:
```
export MISTRAL_API_KEY='xxxx'
```

Model to use should be configured in config.ini:
```
...
[Requests]
...
SLM-MISTRALAI-MODEL=ministral-8b-latest
```

test the same query with:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```


If you want to use CHATGPT, your chatGPT api key should be available as an environment variable
```
export OPENAI_API_KEY=xxxxxxxxx
```

Model to use should be configured in config.ini:
```
...
[Requests]
...
SLM-OPENAI-MODEL=gpt-3.5-turbo-0125
```

test the same query with:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```


# Developpers

Developping new function is very easy. Just go into SPARQL/udf to see how we wrote User Defined Functions you just used, code is very short and can be used as a template for your custom functions. 

You can run tests by  just typing :
```
pytest
```