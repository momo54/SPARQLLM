import os

from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader


embed = OllamaEmbeddings(
    model="nomic-embed-text"
)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)



def chunk_docs():
    folder_path = "./Pset/pset_length"
    txts = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if filename.endswith(".txt"):
                txts.append(os.path.join(root, filename))
    print(len(txts))
    docs = []
    for txt in txts:
        loader = TextLoader(txt, encoding='utf8')
        pages = loader.load()
        docs.extend(pages)

    print(docs[0])
    return docs


if __name__ == "__main__":
    docs = chunk_docs()
    print(len(docs))