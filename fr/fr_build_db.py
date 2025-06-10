import xml.etree.ElementTree as ET
import sqlite3
import re
import os
import sys
import argparse

def process_speaker_data(xml_file_path, db_connection, person_id):
    """
    Processes an XML file containing French deputy speech data, extracts relevant information,
    and stores it in a SQLite database using an existing connection.

    Args:
    xml_file_path (str): The path to the XML file.
    db_connection (sqlite3.Connection): An active SQLite database connection.
    person_id (int): The unique 5-digit ID for this person.
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

    # Extract deputy name from root attributes
    try:
        deputy_name = root.attrib['name']
    except KeyError as e:
        print(f"Missing 'name' attribute in XML file {xml_file_path}: {e}. Skipping file.", file=sys.stderr)
        return False

    # Use the provided 5-digit person ID
    member_id = person_id

    # Party information is not available in the French XML structure
    member_party = ""

    # Process each speech in the file
    speeches_processed = 0
    for speech in root.findall('speech'):
        # Get speech metadata
        speech_date = speech.attrib.get('date', '')
        speech_time = speech.attrib.get('time', '')
        speech_title = speech.attrib.get('title', '')

        # Get the speech text content
        speech_text = speech.text.strip() if speech.text else ""

        if not speech_text:
            print(f"Warning: Empty speech found for {deputy_name} on {speech_date}")
            continue

        try:
            # Insert data into the table with the 5-digit person ID
            c.execute("INSERT INTO speeches (iid, name, party, speech_text) VALUES (?, ?, ?, ?)",
                     (member_id, deputy_name, member_party, speech_text))
            speeches_processed += 1
        except sqlite3.Error as e:
            print(f"Database error when inserting speech data for {deputy_name} from {xml_file_path}: {e}", file=sys.stderr)
            db_connection.rollback()
            return False

    try:
        db_connection.commit()
        print(f"Successfully processed and stored {speeches_processed} speeches for {deputy_name} (ID: {member_id:05d}) from {os.path.basename(xml_file_path)}")
        return True
    except sqlite3.Error as e:
        print(f"Database error when committing data for {deputy_name} from {xml_file_path}: {e}", file=sys.stderr)
        db_connection.rollback()
        return False

def main():
    # Set up argument parser with named arguments
    parser = argparse.ArgumentParser(
        description='Process French Parliament speech XML files and store them in a SQLite database.',
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
    db_name = "fr_politician_speeches.db"
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

    conn = None
    try:
        # Connect to SQLite database (creates if not exists)
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Create table with same structure as UK version
        c.execute("""
            CREATE TABLE IF NOT EXISTS speeches (
                iid INTEGER PRIMARY KEY,
                name TEXT,
                party TEXT,
                speech_text TEXT
            )
        """)
        conn.commit()
        print(f"Connected to database '{db_path}'. Table 'speeches' is ready.")

        processed_files_count = 0
        skipped_files_count = 0
        person_id_counter = 1

        # Get list of files and sort them for consistent ID assignment
        xml_files = []
        for filename in os.listdir(source_directory):
            # Only process XML files that start with 'mme_' or 'm_'
            if filename.endswith(".xml") and (filename.startswith("mme_") or filename.startswith("m_")):
                xml_files.append(filename)
            else:
                print(f"Skipping file (doesn't match naming pattern): {filename}")
                skipped_files_count += 1

        # Sort files to ensure consistent ID assignment across runs
        xml_files.sort()

        for filename in xml_files:
            xml_file_path = os.path.join(source_directory, filename)
            if process_speaker_data(xml_file_path, conn, person_id_counter):
                processed_files_count += 1
                person_id_counter += 1
            else:
                skipped_files_count += 1

        print(f"Database '{db_path}' created/updated successfully.")
        print(f"Processed {processed_files_count} XML files.")
        print(f"Skipped {skipped_files_count} files (due to errors or naming pattern).")

        # Optional: Verify the data
        print("Verifying a few entries from the database:")
        c.execute("SELECT iid, name, party, SUBSTR(speech_text, 1, 100) || '...' FROM speeches LIMIT 5")
        rows = c.fetchall()
        if not rows:
            print("No data found in the speeches table.")
        else:
            for row in rows:
                print(f"ID: {row[0]:05d}, Name: {row[1]}, Party: {row[2]}, Speech: {row[3]}")

        # Show total count
        c.execute("SELECT COUNT(*) FROM speeches")
        total_speeches = c.fetchone()[0]
        print(f"Total speeches in database: {total_speeches}")

        # Show unique people count
        c.execute("SELECT COUNT(DISTINCT iid) FROM speeches")
        unique_people = c.fetchone()[0]
        print(f"Total unique people processed: {unique_people}")

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
