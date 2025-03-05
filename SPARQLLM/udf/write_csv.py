import csv
import os


def write_csv(key, title, parcours, area, score):
    # Vérifiez si le fichier existe
    file_exists = os.path.isfile('output.csv')
    area = os.path.basename(area)
    key = key.replace('http://example.org/course/', '')

    # Ouvrez le fichier en mode ajout
    with open('output.csv', 'a', newline='') as file:
        writer = csv.writer(file)

        # Écrivez l'en-tête si le fichier n'existe pas
        if not file_exists:
            writer.writerow(['key', 'title', 'parcours', 'area'])

        # Écrivez la nouvelle ligne
        writer.writerow([key, title, parcours, area])


if __name__ == "__main__":
    # Exemple d'utilisation
    key = 'ZZCRLADR'
    title = 'Classification, representation learning and dimensionality reduction'
    parcours = 'M1'
    area = 'DS'
    write_csv(key, title, parcours, area)