
# install

Requires RDFLIB 7, OpenAI and python3 (and more ;). 
```
pip install rdflib
pip install openai
```
It supposes your chatGPT api key available in os.environ.get("OPENAI_API_KEY")

It also suppose that you have a custom search Google API activated :
```
se_api_key=os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key=os.environ.get("SEARCH_CX")
```

just run:
```
python main.py
```

# Usage

SPARQLLM is a way to integrate SPARQL, Search Engines and LLMs calls into a SPARQL service. 

It relies mainly on 5 user defined Functions:

* __LLM(Prompt:String):- String__ Answer is the result of the prompt. the output the result of the prompt.

* __Google(Keywords:String):- URI__  answer is the first URI returned by Google Search.

* __BS4(uri):-String. answer is the text content of the URI.

* __SEGRAPH(keywords:strings,entity) :- named_graph__. named_graph contain the answer of the search engine as a RDF graph. The entity is linked to URIs with the  <http://example.org/has_uri> predicate.

* __LLMGRAPH(prompt, RDF entity):-named_graph__.Prompt ask the LLM to generate a graph where the roots of this graph is lined to RDF entity with a  <http://example.org/has_schema_type> predicate. 


# LLM Function

For example, the query below
load a bibliographic KG and ask for each journal/conf the metrics of the journal.
Journal metrics are obtained with LLM prompt in the BIND statement.

```
SELECT ?pub  ?journal 
  (ex:LLM(REPLACE("In the scientific world, give me the impact factor or CORE ranking as JSON for the journal or conference entitled %PLACE%","%PLACE%",STR(?journal))) as ?llm) 
  WHERE {
    ?pub dct:isPartOf ?part .
    ?part dc:title ?journal .
 } limit 10
```

This returns:
```
...
file:///Users/molli-p/SPARQLLM/Bonet2023b  Proceedings of the 40th International Conference on Machine Learning (PMLR) {
  "journal": "Proceedings of the 40th International Conference on Machine Learning (PMLR)",
  "impact_factor": 3.981,
  "CORE_ranking": "A*"
}
file:///Users/molli-p/SPARQLLM/Hamoum2023a  International Conference on Digital Signal Processing, DSP {
  "journal": "International Conference on Digital Signal Processing, DSP",
  "impact_factor": 1.234,
  "CORE_ranking": "B"
...
```

It works but many results are hallucinated.

# Google and BS4 functions

Another interesting query is:
```
SELECT DISTINCT ?universityLabel ?uri ?nbetu ?result
WHERE {
    SERVICE <http://dbpedia.org/sparql> {
    SELECT *  where {
        ?university a dbo:University ;
            dbo:country dbr:France ;
            dbo:numberOfStudents ?nbetu .
    OPTIONAL { ?university rdfs:label ?universityLabel . 
    FILTER (lang(?universityLabel) = "fr") }
    } LIMIT 5
    }
    BIND(ex:Google(REPLACE("FRANCE UNIV ","UNIV",STR(?universityLabel))) AS ?uri)
    BIND(ex:BS4(?uri) AS ?page)   
     BIND(ex:LLM(REPLACE("trouve le nombre d'étudiant dans le texte suivant et renvoie un entier avec son contexte :<text>PAGE</text>","PAGE",str(?page))) AS ?result)
}
```

The results are:
```
row : Institut d'études politiques de Paris https://www.sciencespo.fr/en/about/governance-and-budget/institut-detudes-politiques-de-paris/ 14000 Le nombre d'étudiants dans le texte est de 1. Le contexte est que le lien "Student" renvoie à une page destinée aux étudiants.
row : Institut d'études politiques d'Aix-en-Provence https://en.wikipedia.org/wiki/Sciences_Po_Aix 15 Il n'y a pas de nombre d'étudiants mentionné dans le texte fourni.
row : Institut d'études politiques d'Aix-en-Provence https://en.wikipedia.org/wiki/Sciences_Po_Aix 1800 Il n'y a pas de nombre d'étudiants mentionné dans le texte fourni.
row : Université Montpellier-II https://www.umontpellier.fr/en/ 16224 Le nombre d'étudiants dans le texte est zéro.
row : École d'urbanisme de Paris https://www.eup.fr/ 500 Il n'y a pas de mention du nombre d'étudiants dans le texte fourni.
```

This query retreives universities from Dbpedia, then ask a search engine to find one URL, and ask LLM to extract info from the page content of whose URLs.

It works, but only one URIs from search engine can be explored.

# SEGRAPH, BS4 and LLMGRAPH Combined

The following query allows to explore multiple URIs, and select patterns in the extracted schema.org markup. It is a Select Query, but it can be CONSTRUCT QUERY.

```
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dbr: <http://dbpedia.org/resource/>
PREFIX ex: <http://example.org/>

SELECT ?university ?uri ?o1
WHERE {
  SERVICE <http://dbpedia.org/sparql> {
      SELECT *  WHERE {
         ?university a dbo:University ;
            dbo:country dbr:France ;
            dbo:numberOfStudents ?nbetu .
            OPTIONAL { ?university rdfs:label ?universityLabel . 
             FILTER (lang(?universityLabel) = "fr") }
        } LIMIT 1
      }
  BIND(ex:SEGRAPH(REPLACE("UNIV France","UNIV",STR(?universityLabel)),?university) AS ?segraph).
  GRAPH ?segraph {?university <http://example.org/has_uri> ?uri}    

  BIND(ex:BS4(?uri) AS ?page)   
  BIND(ex:LLMGRAPH(REPLACE("generate in JSON-LD a schema.org representation for a type university of : <page> PAGE </page>. Output only JSON-LD","PAGE",STR(?page)),?university) AS ?g)
  GRAPH ?g {?university <http://example.org/has_schema_type> ?root . ?root ?p1 ?o1}    
```

the results are:
```
<...>
university: http://dbpedia.org/resource/Sciences_Po
uri: https://www.sciencespo.fr/en/about/governance-and-budget/institut-detudes-politiques-de-paris/
o1: http://schema.org/University

university: http://dbpedia.org/resource/Sciences_Po
uri: https://www.sciencespo.fr/en/about/governance-and-budget/institut-detudes-politiques-de-paris/
o1: Sciences Po

university: http://dbpedia.org/resource/Sciences_Po
uri: https://www.sciencespo.fr/en/about/governance-and-budget/institut-detudes-politiques-de-paris/
o1: https://www.sciencespo.fr/en/
<...>
```