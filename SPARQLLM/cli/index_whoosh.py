import os
import click
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID

# 📌 Whoosh Indexing Function
@click.command()
@click.option('--txt-dir', default="./data/events", help="Directory containing .txt files to index")
@click.option('--index-dir', default="./data/whoosh_store", help="Directory where Whoosh index will be stored")
def index_whoosh(txt_dir, index_dir):
    """
    Indexes .txt files in Whoosh with filename and content.
    """
    # 🔹 Define schema with filename included
    schema = Schema(filename=ID(stored=True), content=TEXT)

    # 🔹 Ensure index directory exists
    if not os.path.exists(index_dir):
        os.makedirs(index_dir)
        ix = create_in(index_dir, schema)
    else:
        ix = open_dir(index_dir)

    writer = ix.writer()

    # 🔹 Read and index all .txt files
    for txt_file in os.listdir(txt_dir):
        if txt_file.endswith(".txt"):
            file_path = os.path.abspath(os.path.join(txt_dir, txt_file))
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 🔹 Index document
            writer.add_document(filename=file_path, content=content)

    writer.commit()
    print(f"✅ Indexing completed! Indexed files from '{txt_dir}' into '{index_dir}'.")

# 📌 Execute CLI
if __name__ == "__main__":
    index_whoosh()
