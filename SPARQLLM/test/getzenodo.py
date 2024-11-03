
import requests
import html
import html2text
import unidecode

headers = {
            'Accept': 'text/html',
            'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
        }

uri="https://zenodo.org/records/13957372"

response = requests.get(uri,headers=headers)


h = html2text.HTML2Text()
uri_text = h.handle(response.text)
uri_text_uni= unidecode.unidecode(uri_text).strip()

with open("out.txt", "a", encoding="utf-8") as fichier:
    # Ajouter la chaîne dans le fichier
    fichier.write(uri_text_uni)

    
