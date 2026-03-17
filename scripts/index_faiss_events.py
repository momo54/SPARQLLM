import faiss
import numpy as np
from rdflib import Graph, Namespace
from sentence_transformers import SentenceTransformer
import argparse

def main():
    parser = argparse.ArgumentParser(description="Index RDF events with FAISS and search over text.")
    parser.add_argument("rdf_file", nargs="?", default="events.nt.ttl", help="RDF file to index (default: events.nt.ttl)")
    args = parser.parse_args()

    SCHEMA = Namespace("http://schema.org/")
    g = Graph()
    g.parse(args.rdf_file, format="turtle")

    # Extract texts and all properties for each entry
    entries = []
    texts = []
    for s in g.subjects(predicate=SCHEMA.text):
        text = g.value(subject=s, predicate=SCHEMA.text)
        props = {str(p): str(o) for p, o in g.predicate_objects(subject=s)}
        entries.append({"uri": str(s), "props": props})
        texts.append(str(text))

    # Embedding + FAISS indexing
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(texts, normalize_embeddings=True)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(np.array(embeddings, dtype='float32'))

    # Example search
    query = "music in Berlin"
    q_emb = model.encode([query], normalize_embeddings=True)
    D, I = index.search(np.array(q_emb, dtype='float32'), k=3)
    print(f"FAISS results for: {query}\n(file: {args.rdf_file})")
    for idx in I[0]:
        print("URI:", entries[idx]["uri"])
        print("Properties:")
        for k, v in entries[idx]["props"].items():
            print(f"  {k} : {v}")
        print("-")

if __name__ == "__main__":
    main()
