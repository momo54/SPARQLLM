import os
import sys
import pandas as pd
from pdfminer.high_level import extract_text
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from io import StringIO
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

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

def pdf_to_excel(pdf_path, excel_path):
    """
    Convertit un PDF en fichier Excel avec chaque page comme onglet séparé
    :param pdf_path: Chemin vers le fichier PDF
    :param excel_path: Chemin pour enregistrer le fichier Excel
    """
    try:
        # Créer un nouveau classeur Excel
        wb = Workbook()
        
        # Supprimer la feuille par défaut si elle existe
        if 'Sheet' in wb.sheetnames:
            del wb['Sheet']
        
        # Extraire le texte de chaque page du PDF
        with open(pdf_path, 'rb') as pdf_file:
            rsrcmgr = PDFResourceManager()
            
            for i, page in enumerate(PDFPage.get_pages(pdf_file)):
                # Créer un convertisseur de texte pour cette page
                output_string = StringIO()
                device = TextConverter(rsrcmgr, output_string)
                interpreter = PDFPageInterpreter(rsrcmgr, device)
                
                # Traiter la page
                interpreter.process_page(page)
                
                # Récupérer le texte
                text = output_string.getvalue()
                
                # Fermer les flux
                device.close()
                output_string.close()
                
                # Créer un DataFrame avec le texte
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                df = pd.DataFrame({'Contenu': lines})
                
                # Ajouter un onglet au classeur Excel
                sheet_name = f"Page {i+1}"
                ws = wb.create_sheet(title=sheet_name)
                
                # Écrire les données dans l'onglet
                for row in dataframe_to_rows(df, index=False, header=True):
                    ws.append(row)
        
        # Sauvegarder le fichier Excel
        wb.save(excel_path)
        print(f"\nConversion réussie ! Fichier Excel créé : {excel_path}")
        return True
    
    except Exception as e:
        print(f"\nErreur lors de la conversion : {str(e)}")
        return False

def main():
    print("\n=== Convertisseur PDF vers Excel ===")
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
    excel_path = os.path.join(output_folder, f"{pdf_name}.xlsx")
    
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