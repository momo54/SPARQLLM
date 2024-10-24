from rdflib import Graph, URIRef, Literal
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.evalutils import _eval
from rdflib.plugins.sparql.evaluate import evalService

# Define a custom service handler
def custom_service_handler(endpoint, algebra, query_context):
    # Process the custom service query however you want
    print(f"Custom SERVICE call to: {endpoint}")
    
    # Example: Returning a hardcoded result for demonstration purposes
    return [
        {"fakeSubject": Literal("FakeSubject1"), "fakeValue": Literal("Processed Value 1")},
        {"fakeSubject": Literal("FakeSubject2"), "fakeValue": Literal("Processed Value 2")}
    ]

# Override the default SERVICE evaluator to use our custom handler
def eval_custom_service(expr, ctx):
    if str(expr.iri) == "http://example.org/customService":
        return custom_service_handler(expr.iri, expr.p, ctx)
    else:
        return evalService(expr, ctx)  # Call the default service handler for other endpoints

# Patch the rdflib evaluator to use the custom service handler
_eval["service"] = eval_custom_service

# Create a sample RDF graph
g = Graph()

# Add some sample data to the graph
g.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal(5)))

# SPARQL query that uses the custom SERVICE function
query_str = """
PREFIX ex: <http://example.org/>
SELECT ?fakeSubject ?fakeValue
WHERE {
    SERVICE <http://example.org/customService> {
        ?fakeSubject ?p ?fakeValue .
    }
}
"""

# Prepare and execute the query
query = prepareQuery(query_str)
result = g.query(query)

# Display the results from the custom service handler
for row in result:
    print(f"Subject: {row['fakeSubject']}, Value: {row['fakeValue']}")
