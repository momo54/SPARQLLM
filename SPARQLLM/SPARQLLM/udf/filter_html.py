from bs4 import BeautifulSoup
from rdflib import Literal

def filter_html(func, args):
    """
    Filtrer une page HTML en supprimant les balises inutiles tout en conservant les informations pertinentes.
    
    - Dans le header, on garde seulement : title, meta, link, et les informations sur l'auteur/organisation.
    - Dans le body, on garde tous les éléments qui présentent des informations utiles.
    
    :param code_html: chaîne de caractères contenant le code HTML
    :return: le code HTML filtré sous forme de chaîne de caractères
    """

    # func étant la fonction qu'on wrap
    code_html = func(args)
    code_html = str(code_html)

    # Liste des balises inutiles à supprimer
    balises_inutiles = ['script', 'style', 'noscript', 'iframe', 'svg', 'canvas']

    # Utilisation de BeautifulSoup pour analyser le code HTML
    soup = BeautifulSoup(code_html, 'html.parser')

    if soup.head != None and soup.body != None:
        
        # Filtrer le <head>
        for tag in soup.head.find_all(True):  # Tous les tags
            if tag.name in balises_inutiles or (tag.name == 'link' and tag.get('rel') != 'stylesheet') or (tag.name == 'meta' and tag.get('name') not in ['description', 'author']):
                tag.decompose()

        # Filtrer le <body>
        body = soup.body
        for tag in body.find_all(True):  # Tous les tags
            if tag.name in balises_inutiles:
                tag.decompose()

        # Retourner le code HTML filtré sous forme de chaîne
        return Literal(str(soup))
    
    else:
        return Literal(code_html)
    
