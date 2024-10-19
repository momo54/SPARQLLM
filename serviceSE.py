from typing import (
    TYPE_CHECKING,
    Any,
    Deque,
    Dict,
    Generator,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    Union,
)

from rdflib.plugins.sparql.sparql import (
    AlreadyBound,
    FrozenBindings,
    FrozenDict,
    Query,
    QueryContext,
    SPARQLError,
)

from rdflib.plugins.sparql.evaluate import evalServiceQuery
from rdflib.plugins.sparql.sparql import QueryContext
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen
from rdflib import Graph, Literal, URIRef

from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.term import BNode, Identifier, Literal, URIRef, Variable
import re
import os
import json

# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key=os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key=os.environ.get("SEARCH_CX")

#curl  'https://customsearch.googleapis.com/customsearch/v1?q=tagada&cx=94d3d5e42f5a24ac0&key={se_api_key}' \
#  --header 'Accept: application/json' \
#   --compressed


def evalServiceSEQuery(ctx: QueryContext, part: CompValue):
    res = {}
    se_url=f"https://customsearch.googleapis.com/customsearch/v1?cx={se_cx_key}&key={se_api_key}"

    if str(part.get('term')) != "http://www.google.com":
        raise Exception("Service not supported")
    bind_expr = part.get("graph").get("part")[0].get("expr")
    bind_var = part.get("graph").get("part")[0].get("var")

    # Send the request to Google search
    se_url = f"{se_url}&q={quote(bind_expr)}"
    print(f"se_url={se_url}")
    headers = {'Accept': 'application/json'}
    request = Request(se_url, headers=headers)
    response = urlopen(request)
    json_data = json.loads(response.read().decode('utf-8'))

    # Extract the URLs from the response
    links = [item['link'] for item in json_data.get('items', [])]
#    print(f"links={links}")

    c=ctx.push()
    # Return the first 5 links, can be costly, should be a parameter...
    # or in a subquery ??
    res_dict: Dict[Variable, Identifier] = {}
    for link in links[:5]:
        res_dict[ bind_var] = Literal(link)
        yield FrozenBindings(ctx, res_dict)


