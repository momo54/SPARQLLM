from rdflib import Graph, ConjunctiveGraph,  URIRef, Literal, Namespace

## super important !!
## need one store per request as graph are created dynamically during query execution.
store = ConjunctiveGraph()
