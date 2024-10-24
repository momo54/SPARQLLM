##
## Just for debugging purpose
## Need to see the evaluation order of the RDFLIB.
## -> used to determine that forcing LAzyJoin was working.
##


import rdflib
from rdflib import Graph, ConjunctiveGraph,  URIRef, Literal, Namespace
from rdflib.plugins.sparql.evaluate import evalGraph, evalServiceQuery, evalLazyJoin

from udf.SPARQLLM import store

from udf.llmgraph_fake import LLMGRAPH_fake

from utils.explain import explain


def my_evalgraph(ctx, part):
    print(f"EVALGRAPH ctx: {ctx.graph.identifier}, part: {part}")
#    try:
#        print(f"before init bindings: {ctx.initBindings}")
#        print(f"before bindings: {ctx.bindings}")
#        print(f"EVALGRAPH before solution: {ctx.solution()}")
#    except:
#        print("eval graph no bindings")
#        pass
    res=evalGraph(ctx, part)
#    try:
#        print(f"after init bindings: {ctx.initBindings}")
#        print(f"after graph bindings: {ctx.bindings}")
#        print(f"EVALGRAPH AFTER solution: {ctx.solution()}")
#    except:
#        print("EVALGRAPH after graph no bindings")
#        pass

    return res

def my_evalservice(ctx, part):
    print(f"EVALSERVICE ctx: {ctx}, part: {part}")
    return evalServiceQuery(ctx, part)

def my_evaljoin(ctx, part):
    print(f"EVALJOIN ctx: {ctx}, part: {part}")
    ## only lazyJoin. Sure to have the named computed before evaluating graph clauses...
    return evalLazyJoin(ctx, part)



def customEval(ctx, part):  # noqa: N802
    """
    Rewrite triple patterns to get super-classes
    """
    print("part.name", part.name)
    if part.name == "Graph":
            return my_evalgraph(ctx, part)
    if part.name == "ServiceGraphPattern":
            return my_evalservice(ctx, part)
    if part.name == "Join":
            return my_evaljoin(ctx, part)

    raise NotImplementedError()

rdflib.plugins.sparql.CUSTOM_EVALS["exampleEval"] = customEval



store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("http://example.org/graph1")))  

store.get_context("http://example.org/graph1").add((URIRef("http://example.org/subject1"), URIRef("http://example.org/has_uri"), URIRef("https://zenodo.org/records/13955291")))
store.get_context("http://example.org/graph2").add((URIRef("http://example.org/graph2"), URIRef("http://example.org/has_uri"), URIRef("http://example.org/graph3")))

#store.get_context("https://zenodo.org/records/13955291").add((URIRef("https://zenodo.org/records/13955291"), URIRef("http://example.org/has_schema_type"), URIRef("http://example.org/graph5")))

query_str = """
        PREFIX ex: <http://example.org/>
        SELECT *
        WHERE {
              ?s <http://example.org/hasValue> ?value .
              BIND(?value AS ?graph1)
                GRAPH ?graph1 {?s <http://example.org/has_uri> ?uri} .
            BIND(CONCAT("tagada zouzou",str(?value)) AS ?page) . 
            BIND(?uri as ?force)  
            BIND(ex:LLMGRAPH_fake(REPLACE("Extrait en JSON-LD la représentation schema.org de : PAGE ","PAGE",STR(?page)),?value) AS ?graph2) .
               GRAPH ?graph2 {?s ?p ?o}    
        }
        """

#for g in store.contexts():  # context() retourne tous les named graphs
#    print(f"main store named graphs: {g.identifier}")

explain(query_str)

result = store.query(query_str)

for row in result:
    for var in result.vars:  # results.vars contient les noms des variables
        print(f" results {var}: {row[var]}")  # Afficher nom de colonne et valeur
    print()  # Séparation entre les lignes
