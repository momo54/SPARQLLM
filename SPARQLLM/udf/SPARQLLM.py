import rdflib
from rdflib import Graph, ConjunctiveGraph, Dataset,  URIRef, Literal, Namespace
from rdflib.plugins.sparql.evaluate import evalGraph, evalServiceQuery, evalLazyJoin

import logging

def my_evaljoin(ctx, part):
    #print(f"EVALJOIN ctx: {ctx}, part: {part}")
    ## only lazyJoin. Sure to have the named graphs computed before evaluating graph clauses...
    return evalLazyJoin(ctx, part)

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


def customEval(ctx, part):  # noqa: N802
    """
    Rewrite triple patterns to get super-classes
    """
    #logging.debug("part.name:{part.name}")
    # if part.name == "Graph":
    #         return my_evalgraph(ctx, part)
    # if part.name == "ServiceGraphPattern":
    #         return my_evalservice(ctx, part)
    if part.name == "Join":
            return my_evaljoin(ctx, part)

    raise NotImplementedError()

rdflib.plugins.sparql.CUSTOM_EVALS["exampleEval"] = customEval

## super important !!
## need one store per request as graph are created dynamically during query execution.
store = Dataset()

def reset_store():
    """Reset the global store."""
    global store
    for g in list(store.contexts()):
        store.remove_graph(g)
    #store = Dataset()  # Reinitialize the global store