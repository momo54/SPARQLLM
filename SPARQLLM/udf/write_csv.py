import csv
import os

def write_csv(key, folder_name, label, parcours):
    # Define the CSV file path
    csv_file_path = 'output.csv'

    # Define the row to be written
    row = {
        'key': key,
        'title': label,
        'parcours': parcours,
        'year': 'M1',
        folder_name: 'x'
    }

    # Check if the CSV file exists
    file_exists = os.path.isfile(csv_file_path)

    # Read existing columns if the file exists
    if file_exists:
        with open(csv_file_path, mode='r', newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            existing_columns = reader.fieldnames
    else:
        existing_columns = ['key', 'title', 'parcours', 'year']

    # Add the new folder_name column if it doesn't exist
    if folder_name not in existing_columns:
        existing_columns.append(folder_name)
        # Read existing rows
        if file_exists:
            with open(csv_file_path, mode='r', newline='') as csv_file:
                reader = csv.DictReader(csv_file)
                rows = list(reader)
            # Rewrite the file with the new header
            with open(csv_file_path, mode='w', newline='') as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=existing_columns)
                writer.writeheader()
                writer.writerows(rows)

    # Open the CSV file in append mode
    with open(csv_file_path, mode='a', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=existing_columns)

        # Write the header only if the file does not exist
        if not file_exists:
            writer.writeheader()

        # Write the row
        writer.writerow(row)

if __name__ == "__main__":
    # Example usage
    key = 'example_key'
    ku_source = 'new_folder'
    label = 'Example Label'
    parcours = 'Example Parcours'
    write_csv(key, ku_source, label, parcours)