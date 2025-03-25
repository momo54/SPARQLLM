import os
import sys
import pandas as pd
from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.drawing.image import Image
from io import BytesIO
from PIL import Image as PILImage
import pytesseract
from pdf2image import convert_from_path

def get_pdf_path():
    """Demande le chemin du fichier PDF via la ligne de commande"""
    while True:
        pdf_path = input("Entrez le chemin complet du fichier PDF: ").strip()
        if os.path.isfile(pdf_path) and pdf_path.lower().endswith('.pdf'):
            return pdf_path
        print("Fichier PDF introuvable. Veuillez réessayer.")

def get_output_folder():
    """Demande le dossier de sortie via la ligne de commande"""
    while True:
        folder = input("Entrez le dossier de sortie (laissez vide pour le dossier courant): ").strip()
        if not folder:
            return os.getcwd()
        if os.path.isdir(folder):
            return folder
        print("Dossier introuvable. Veuillez réessayer.")

def extract_tables_from_pdf(pdf_path):
    """Tente d'extraire les tableaux du PDF (version simplifiée)"""
    # Cette partie devrait idéalement utiliser une librairie comme camelot ou pdfplumber
    # Pour cet exemple, nous utilisons une approche simplifiée
    laparams = LAParams()
    rsrcmgr = PDFResourceManager()
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    
    tables = []
    
    with open(pdf_path, 'rb') as pdf_file:
        for page in PDFPage.get_pages(pdf_file):
            interpreter.process_page(page)
            layout = device.get_result()
            # Ici, nous devrions analyser la layout pour trouver les tableaux
            # Pour l'exemple, nous extrayons simplement tout le texte
            tables.append(extract_text(pdf_path))
    
    return tables

def pdf_to_excel(pdf_path, excel_path):
    """
    Convertit un PDF en fichier Excel en essayant de préserver la structure
    :param pdf_path: Chemin vers le fichier PDF
    :param excel_path: Chemin pour enregistrer le fichier Excel
    """
    try:
        # Créer un nouveau classeur Excel
        wb = Workbook()
        
        # Supprimer la feuille par défaut
        if 'Sheet' in wb.sheetnames:
            del wb['Sheet']
        
        # Option 1: Extraire le texte structuré
        try:
            tables = extract_tables_from_pdf(pdf_path)
            for i, table in enumerate(tables):
                # Créer un DataFrame à partir du texte (simplifié)
                lines = [line.strip() for line in table.split('\n') if line.strip()]
                df = pd.DataFrame({'Contenu': lines})
                
                # Ajouter un onglet
                sheet_name = f"Page {i+1}"
                ws = wb.create_sheet(title=sheet_name)
                
                # Écrire les données
                for row in dataframe_to_rows(df, index=False, header=True):
                    ws.append(row)
        except Exception as e:
            print(f"Erreur lors de l'extraction des tableaux: {e}")
        
        # Option 2: Utiliser OCR pour les images (si pdf2image et pytesseract sont installés)
        try:
            # Convertir les pages PDF en images
            images = convert_from_path(pdf_path)
            
            for i, image in enumerate(images):
                # Utiliser OCR pour extraire le texte
                text = pytesseract.image_to_string(image)
                
                # Créer un onglet pour cette page
                sheet_name = f"OCR Page {i+1}"
                ws = wb.create_sheet(title=sheet_name)
                
                # Ajouter le texte
                for line in text.split('\n'):
                    if line.strip():
                        ws.append([line.strip()])
        except ImportError:
            print("Les bibliothèques OCR ne sont pas disponibles")
        except Exception as e:
            print(f"Erreur lors de l'OCR: {e}")
        
        # Sauvegarder le fichier Excel
        wb.save(excel_path)
        print(f"\nConversion réussie ! Fichier Excel créé : {excel_path}")
        return True
    
    except Exception as e:
        print(f"\nErreur lors de la conversion : {str(e)}")
        return False

def main():
    print("\n=== Convertisseur PDF vers Excel amélioré ===")
    print("1. Entrez le chemin du fichier PDF à convertir")
    print("2. Entrez le dossier de sortie")
    print("3. Le fichier Excel sera généré automatiquement\n")
    
    # Sélection du fichier PDF
    pdf_path = get_pdf_path()
    print(f"\nFichier PDF sélectionné : {pdf_path}")
    
    # Sélection du dossier de sortie
    output_folder = get_output_folder()
    
    # Nom du fichier de sortie
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    excel_path = os.path.join(output_folder, f"{pdf_name}_converted.xlsx")
    
    # Vérifier si le fichier existe déjà
    if os.path.exists(excel_path):
        choice = input(f"Le fichier {excel_path} existe déjà. Voulez-vous le remplacer ? (o/n): ")
        if choice.lower() != 'o':
            print("Opération annulée.")
            return
    
    # Lancer la conversion
    print("\nConversion en cours...")
    if pdf_to_excel(pdf_path, excel_path):
        print("\nConversion terminée avec succès !")

if __name__ == "__main__":
    main()