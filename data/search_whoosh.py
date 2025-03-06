from whoosh.index import open_dir
from whoosh.qparser import QueryParser
from whoosh.qparser import MultifieldParser,  WildcardPlugin

def search_index(query_str):
    """Search Whoosh index and return matching files with scores."""
    index_dir = "index"
    ix = open_dir(index_dir)
    
    with ix.searcher() as searcher:
        parser=MultifieldParser(["content"], ix.schema)
        parser.add_plugin(WildcardPlugin())
        query = parser.parse(query_str+"*")
        results = searcher.search(query, limit=10)  # Limit to top 10 results
        
        if results:
            print(f"Found {len(results)} results for query: {query_str}\n")
            for result in results:
                print(f"File: {result['filename']}")
                print(f"Score: {result.score:.4f}")
                print("-" * 40)
        else:
            print(f"No results found for query: {query_str}")

if __name__ == "__main__":
    search_index("cinema Paris")