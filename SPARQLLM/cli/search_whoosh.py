import os
import click
from whoosh.index import open_dir
from whoosh.qparser import MultifieldParser, WildcardPlugin

# 📌 Whoosh Search Function
@click.command()
@click.option('--query', prompt="Enter search query", help="Search query text")
@click.option('--index-dir', default="./data/whoosh_store", help="Directory where Whoosh index is stored")
@click.option('--limit', default=10, help="Number of search results to return")
def search_whoosh(query, index_dir, limit):
    """
    Searches the Whoosh index for matching files with scores.
    """
    if not os.path.exists(index_dir):
        print(f"❌ Error: Index directory '{index_dir}' not found. Run `index_whoosh.py` first.")
        return

    ix = open_dir(index_dir)

    with ix.searcher() as searcher:
        parser = MultifieldParser(["content"], ix.schema)
        parser.add_plugin(WildcardPlugin())  # Enable wildcard searches
        query_obj = parser.parse(query + "*")  # Wildcard search

        results = searcher.search(query_obj, limit=limit)  # Limit results

        if results:
            print(f"\n🔍 Found {len(results)} results for query: '{query}'\n")
            for result in results:
                print(f"📄 File: {result['filename']}")
                print(f"⭐ Score: {result.score:.4f}")
                print("-" * 40)
        else:
            print(f"❌ No results found for query: '{query}'")

# 📌 Run search via CLI
if __name__ == "__main__":
    search_index()
