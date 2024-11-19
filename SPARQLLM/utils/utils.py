import rdflib
from rdflib import URIRef

import pandas as pd

from urllib.parse import urlparse
from urllib.parse import urlencode,quote

def named_graph_exists(conjunctive_graph, graph_uri):
    for g in conjunctive_graph.contexts():  # context() retourne tous les named graphs
        if g.identifier == graph_uri:
            return True
    return False


def print_result_as_table(results,col_width=30):

    pd.set_option('display.max_colwidth', col_width)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    # Extract variable names (column headers)
    columns = [str(var) for var in results.vars]

    # Convert results to a list of dictionaries
    data = [{str(var): str(row[var]) for var in results.vars} for row in results]

    # Create a DataFrame
    df = pd.DataFrame(data, columns=columns)

    # Print the DataFrame
#    print(df.to_string(index=False))
    print(df)

def is_valid_uri(uri):
    """
    Check if the given URI is valid.

    This function parses the input URI and checks if it has a valid scheme and netloc.

    Args:
        uri (str): The URI to be validated.

    Returns:
        bool: True if the URI has a valid scheme and netloc, False otherwise.
    """
    parsed_uri = urlparse(str(uri))
    # Check if the URI has a valid scheme and netloc
    return all([parsed_uri.scheme, parsed_uri.netloc])

def clean_invalid_uris(graph):
    to_remove = []
    
    for s, p, o in graph:
        # Check each term for URI validity
        if (isinstance(s, URIRef) and not is_valid_uri(s)) or \
           (isinstance(p, URIRef) and not is_valid_uri(p)) or \
           (isinstance(o, URIRef) and isinstance(o, URIRef) and not is_valid_uri(o)):
            to_remove.append((s, p, o))
    
    # Remove invalid triples
    for triple in to_remove:
        graph.remove(triple)



