# Import RDFLib components
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, FOAF


# Load RDF graph from XML file
g = Graph()
g.parse("cominlabs2023.rdf", format="xml")
query="""
#        PREFIX dct: <http://purl.org/dc/terms/>
#        PREFIX dc: <http://purl.org/dc/elements/1.1/>
#        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
#        PREFIX vcard: <http://www.w3.org/2001/vcard-rdf/3.0#>
        PREFIX bibtex: <http://www.edutella.org/bibtex#>
#        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#">
        SELECT ?s0  ?o WHERE {
            ?s0 dct:isPartOf ?part .
            ?part dc:title ?o    
        } limit 50"""
qres = g.query(query)
for row in qres:
        print(f"{row.s0}  {row.o}")