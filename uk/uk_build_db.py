import xml.etree.ElementTree as ET
import sqlite3
import re
import os
import sys # Import sys for command-line arguments
import argparse # Add argparse for better command-line argument handling

def process_speaker_data(xml_file_path, db_connection):
    """
    Processes an XML file containing speaker data, extracts relevant information,
    and stores it in a SQLite database using an existing connection.

    Args:
    xml_file_path (str): The path to the XML file.
    db_connection (sqlite3.Connection): An active SQLite database connection.
    """
    c = db_connection.cursor()
    
    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Error parsing XML file {xml_file_path}: {e}", file=sys.stderr)
        return False
    except IOError as e:
        print(f"Error reading XML file {xml_file_path}: {e}", file=sys.stderr)
        return False

    member_id = None
    member_name = None
    
    # Safely get attributes, handling potential KeyError if attributes are missing
    try:
        member_id = int(root.attrib['member_id'])
        member_name = root.attrib['member_name']
    except KeyError as e:
        print(f"Missing attribute in XML file {xml_file_path}: {e}. Skipping file.", file=sys.stderr)
        return False
    except ValueError as e:
        print(f"Invalid 'member_id' format in XML file {xml_file_path}: {e}. Skipping file.", file=sys.stderr)
        return False
    
    # The party information is not directly available in the provided XML structure's root attributes.
    # If party information is desired, it would need to be extracted from the XML if present elsewhere,
    # or passed in via another mechanism. For now, it will remain an empty string as in the original script.
    member_party = "" 

    all_speech_text = []
    for speech in root.findall('speech'):
        paragraphs = speech.findall('p')
        for p in paragraphs:
            # Get all text within <p> tags, stripping leading/trailing whitespace
            paragraph_text = "".join(p.itertext()).strip()
            if paragraph_text:  # Only add if there's actual text
                all_speech_text.append(paragraph_text)

    full_speech_text = " ".join(all_speech_text).strip()

    try:
        # Insert data into the table
        # Using INSERT OR IGNORE to prevent adding duplicate entries based on primary key (iid)
        c.execute("INSERT OR IGNORE INTO speeches (iid, name, party, speech_text) VALUES (?, ?, ?, ?)",
                  (member_id, member_name, member_party, full_speech_text))
        db_connection.commit()
        print(f"Successfully processed and stored data for {member_name} (ID: {member_id}) from {os.path.basename(xml_file_path)}")
        return True
    except sqlite3.Error as e:
        print(f"Database error when inserting data for {member_name} from {xml_file_path}: {e}", file=sys.stderr)
        db_connection.rollback() # Rollback in case of an error
        return False

def main():
    # Set up argument parser with named arguments
    parser = argparse.ArgumentParser(
        description='Process UK Parliament speech XML files and store them in a SQLite database.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--input-dir',
        required=True,
        help='Source directory containing XML files to process'
    )
    
    parser.add_argument(
        '--output-dir', 
        required=True,
        help='Destination directory where the SQLite database will be created'
    )
    
    # Parse command line arguments
    args = parser.parse_args()
    
    source_directory = args.input_dir
    destination_directory = args.output_dir
    db_name = "politician_speeches.db"
    db_path = os.path.join(destination_directory, db_name)

    # --- Error Trapping for Directories ---
    if not os.path.isdir(source_directory):
        print(f"Error: Source directory '{source_directory}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(destination_directory):
        try:
            os.makedirs(destination_directory)
            print(f"Destination directory '{destination_directory}' created.")
        except OSError as e:
            print(f"Error: Could not create destination directory '{destination_directory}': {e}", file=sys.stderr)
            sys.exit(1)
    elif not os.path.isdir(destination_directory):
        print(f"Error: Destination path '{destination_directory}' exists but is not a directory.", file=sys.stderr)
        sys.exit(1)

    conn = None # Initialize connection to None
    try:
        # Connect to SQLite database (creates if not exists)
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Create table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS speeches (
                iid INTEGER PRIMARY KEY,
                name TEXT,
                party TEXT,
                speech_text TEXT
            )
        ''')
        conn.commit()
        print(f"Connected to database '{db_path}'. Table 'speeches' is ready.")

        processed_files_count = 0
        skipped_files_count = 0

        for filename in os.listdir(source_directory):
            # Check if it's an XML file and matches the expected naming convention (e.g., '12345_name.xml')
            if filename.endswith(".xml") and re.match(r'^\d{5}_.*\.xml$', filename):
                xml_file_path = os.path.join(source_directory, filename)
                if process_speaker_data(xml_file_path, conn):
                    processed_files_count += 1
                else:
                    skipped_files_count += 1
            else:
                print(f"Skipping non-XML or malformed file: {filename}", file=sys.stderr)
                skipped_files_count += 1

        print(f"\nDatabase '{db_path}' created/updated successfully.")
        print(f"Processed {processed_files_count} XML files.")
        print(f"Skipped {skipped_files_count} files (due to errors or naming convention).")

        # Optional: Verify the data
        print("\nVerifying a few entries from the database:")
        c.execute("SELECT iid, name, party, SUBSTR(speech_text, 1, 100) || '...' FROM speeches LIMIT 5")
        rows = c.fetchall()
        if not rows:
            print("No data found in the speeches table.")
        for row in rows:
            print(row)

    except sqlite3.Error as e:
        print(f"Critical database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            print(f"Database connection to '{db_path}' closed.")

if __name__ == "__main__":
    main()
