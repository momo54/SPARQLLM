SPARQLLM proposes a new technique to access external sources during SPARQL query execution.
It allows to easily run SPARQL query that can access Search Engines, Large Language Models, or Vector database. 


# install

```
git clone https://github.com/momo54/SPARQLLM
cd SPARQLLM
```

install with virtualenv (recommended):
```
virtualenv mon_env
source mon_env/bin/activate
pip install -r requirements.txt
pip install .
```

usage:
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
                            query
  -o, --output-result TEXT  File to store the result of the query
  -o, --output-result TEXT  File to store the result of the query query. 1
                            line per result
  --help                    Show this message and exit.
```



# Run queries working with the local file system


Run a simple queries using the local file system as external source :
```
slm-run --config config.fs -f queries/simple-csv.sparql --debug
slm-run --config config.fs -f queries/readfile.sparql --debug
slm-run --config config.fs -f queries/ReadDir.sparql --debug
slm-run --config config.fs -f queries/recurse.sparql --debug
```

# Run queries with Search Engines capabilities

Create synthetic data and index them with Woosh (a simple keyword search library):
```
cd data
python GenerateEventPages.py
python index_whoosh.py
popd 
```

Run a simple query with a (local) Search Engine (Whoosh):
```
slm-run --config config.ini -f queries/city-search.sparql --debug
```

If you want to perform the same query on the WEB with Google Search, 
it is not free. If you want to try, your custom search Google API have
to be  activated and  the keys have to be available as environment variables :
```
export SEARCH_API_SOBIKE44=xxxxxxxx_orbIQ302-4NOQhRnxxxxxxx
export SEARCH_CX=x4x3x5x4xfxxxxxxx
```

If well configure, you should be able to run the same query than before with Google
as a search engine.
```
slm-run --config config.google -f queries/city-search.sparql --debug
```


# run queries with Search and LLMs

We rely on [OLLAMA](https://ollama.com/) to run AI models. You can easily install locally OLLAMA as a server on macOS, Linux, Windows.

```
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.1:latest
ollama pull nomic-embed-text
```

Test if model is installed:
```
ollama list
```

Should see something like:
```
NAME                       ID              SIZE      MODIFIED      
nomic-embed-text:latest    0a109f422b47    274 MB    9 seconds ago    
llama3.1:latest            46e0c10c039e    4.9 GB    3 hours ago 
...
```

Test if it work:
```
ollama run llama3.1:latest
```


If your OLLAMA server is running and models have been installed, then check your config.ini:
```
SLM-OLLAMA-MODEL=llama3.1:latest
SLM-OLLAMA-URL= http://localhost:11434/api/generate
```
We expect OLLAMA server to run on http://localhost:11434/api/generate, and the selected model is llama3.1:latest. If you installed differently, just change accordingly.


SPARQLLM  run:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```

Should see:
```
      label                            uri        date                    name
0  Amsterdam  file://Users/molli-p/SPARQ...  2023-03-20   Annual Music Festival
1      Paris  file://Users/molli-p/SPARQ...  2022-01-15  Mardi Gras Celebration
2  Amsterdam  file://Users/molli-p/SPARQ...  2023-03-20   Annual Music Festival
3     Dublin  file://Users/molli-p/SPARQ...  2022-09-01                Event 75
4   Budapest  file://Users/molli-p/SPARQ...  2024-02-20                My Event
5     Madrid  file://Users/molli-p/SPARQ...  2022-01-20           Holiday Party
6     Madrid  file://Users/molli-p/SPARQ...  2023-08-25             Summer Camp
```

If you want to use CHATGPT, your chatGPT api key should be available as an environment variable
```
export OPENAI_API_KEY=xxxxxxxxx
```

test the same query with:
```
slm-run --config config.openai -f queries/city-search-llm.sparql --debug
```

# Run queries with Vector database

We use FAISS as vector database for indexing document.
First you need to index your document:
```
cd data
python python index_faiss.py 
cd ..
```

This should build ./data/faiss_store

Next you should be able to run the following query:
```
slm-run --config config.ini -f queries/city-search-faiss.sparql --debug
```

# Run queries with Vector database and LLM

```
slm-run --config config.ini -f queries/city-search-faiss-llm.sparql --debug
```


# Developpers

developping new function is very easy. Just go into SPARQL/udf to see how we wrote User Defined Function you just used, code is very short and can be used as a template for your custom functions. 
