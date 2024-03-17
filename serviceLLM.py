import openai
from rdflib.plugins.sparql.evaluate import evalServiceQuery


from rdflib.plugins.sparql.sparql import (
    QueryContext,
)

from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.term import BNode, Identifier, Literal, URIRef, Variable
import re

from openai import OpenAI
import os
client = OpenAI(
        # This is the default and can be omitted
        api_key=os.environ.get("OPENAI_API_KEY"),
    )

def my_evalServiceQuery(ctx: QueryContext, part: CompValue):
    res = {}
    if str(part.get('term')) != "http://chat.openai.com":
        raise Exception("Service not supported")
    bind_expr = part.get("graph").get("part")[0].get("expr")
    bind_var = part.get("graph").get("part")[0].get("var")
    for var_name, var_value in ctx.solution().items():
        bind_expr = bind_expr.replace(f"?{var_name}", str(var_value))

    # Call OpenAI GPT with bind_expr
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
        messages=[
#            {
#                "role": "system",
#                "content": "you have to answer using one single data type"
#            },
            {
                "role": "user",
                "content": bind_expr
            }
        ],
        temperature=0.0
    )
    
    # Extract the generated text from the response
    generated_text = response.choices[0].message.content
    c=ctx.push()
    c[ bind_var] = generated_text
    yield c.solution()





