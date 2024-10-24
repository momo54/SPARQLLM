#!/usr/bin/python

from rdflib.plugins.sparql.algebra import translateQuery, translateUpdate
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate
from rdflib.plugins.sparql.algebra import pprintAlgebra
from rdflib.plugins.sparql.parserutils import prettify_parsetree

import pprint

def explain(query):
    pp = pprint.PrettyPrinter(indent=2)
    pq = parseQuery(query)
    tq = translateQuery(pq)
    print(pprintAlgebra(tq))

