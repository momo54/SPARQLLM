from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

# Define the custom SPARQL function to compute 2 * x
def double_value(x):
    if isinstance(x, Literal) and x.datatype in [XSD.integer, XSD.float, XSD.decimal]:
        return Literal(2 * x.toPython(), datatype=x.datatype)  # Return 2 * x
    else:
        raise ValueError("Argument must be a numeric literal!")

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/double"), double_value)

# Create a sample RDF graph
g = Graph()

# Add some sample data to the graph
g.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal(5, datatype=XSD.integer)))

# SPARQL query using the custom function
query_str = """
PREFIX ex: <http://example.org/>
SELECT ?doubled
WHERE {
    ?s ?p ?value .
    BIND(ex:double(?value) AS ?doubled)
}
"""

# Execute the query
query = prepareQuery(query_str)
result = g.query(query)

# Display the results
for row in result:
    print(f"Doubled value: {row['doubled']}")
