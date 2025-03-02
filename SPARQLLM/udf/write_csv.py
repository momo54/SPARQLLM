import csv
import os

def write_csv(key, ku_source, label, parcours):
    # Define the CSV file path
    csv_file_path = 'output.csv'

    # Extract the folder name from the ku_source path
    folder_name = os.path.basename(os.path.dirname(ku_source))

    # Read the existing CSV file into a list of dictionaries
    rows = []
    file_exists = os.path.isfile(csv_file_path)
    if file_exists:
        with open(csv_file_path, mode='r', newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            rows = list(reader)

    # Check if the key exists in any row
    key_exists = False
    for row in rows:
        if row['key'] == key:
            key_exists = True
            # Update the folder column
            row[folder_name] = 'x'
            break

    # If the key does not exist, add a new row
    if not key_exists:
        new_row = {
            'key': key,
            'title': label,
            'parcours': parcours,
            'year': 'M1',
            folder_name: 'x'
        }
        rows.append(new_row)

    # Get all folder names from existing rows and the new row
    folder_names = set()
    for row in rows:
        folder_names.update(row.keys())
    folder_names.discard('key')
    folder_names.discard('title')
    folder_names.discard('year')
    folder_names.discard('parcours')
    folder_names = sorted(folder_names)

    # Define the final fieldnames in the desired order
    fieldnames = ['key', 'title', 'year', 'parcours'] + folder_names

    # Write the updated list of dictionaries back to the CSV file
    with open(csv_file_path, mode='w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    # Example usage
    key = 'test2'
    ku_source = r'C:\Users\Denez\Desktop\M1\S2\test\SPARQLLM\data\BodyOfKnowledge\Human_Computer_Interaction_HCI\HCI-Accessibility_Accessibility_and_Inclusive_Design.txt'
    label = 'Label'
    parcours = 'Example Parcours'
    write_csv(key, ku_source, label, parcours)