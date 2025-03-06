import os
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID

# Define schema with filename included
schema = Schema(filename=ID(stored=True), content=TEXT)

# Set up Whoosh index
txt_dir = "events"
index_dir = "index"
if not os.path.exists(index_dir):
    os.makedirs(index_dir)
    ix = create_in(index_dir, schema)
else:
    ix = open_dir(index_dir)

writer = ix.writer()

# Read all .txt files and index them
for txt_file in os.listdir(txt_dir):
    if txt_file.endswith(".txt"):
        file_path = os.path.abspath(os.path.join(txt_dir, txt_file))
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Index document
        writer.add_document(filename=file_path, content=content)

writer.commit()
print("Indexing completed!")
