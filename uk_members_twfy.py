import requests
import sqlite3
import json
import time
import argparse
import os
import sys
# This script creates a SQLite database to store UK Parliament members' data fetched from TheyWorkForYou

import pandas as pd
import sqlite3

def create_mps_database(csv_filepath, db_filepath):
    """
    Creates a SQLite database from the 'mps.csv' file.

    Args:
        csv_filepath (str): The path to the input CSV file.
        db_filepath (str): The desired path for the output SQLite database file.
    """
    try:
        # Read the CSV file into a pandas DataFrame
        df = pd.read_csv(csv_filepath)

        # Validate required columns exist
        required_columns = ['Person ID', 'First name', 'Last name']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"Error: Missing required columns in CSV: {missing_columns}", file=sys.stderr)
            return False

        # Rename the 'Person ID' column to 'iid'
        df = df.rename(columns={'Person ID': 'iid'})

        # Combine 'First name' and 'Last name' into a new 'name' column
        df['name'] = df['First name'] + ' ' + df['Last name']

        # Drop the original 'First name' and 'Last name' columns
        df = df.drop(columns=['First name', 'Last name'])

        # Create a SQLite database and table
        conn = sqlite3.connect(db_filepath)
        df.to_sql('mps', conn, if_exists='replace', index=False)
        conn.close()

        print(f"SQLite database '{db_filepath}' created successfully with the 'mps' table.")
        return True

    except FileNotFoundError:
        print(f"Error: The file '{csv_filepath}' was not found.", file=sys.stderr)
        return False
    except pd.errors.EmptyDataError:
        print(f"Error: The CSV file '{csv_filepath}' is empty.", file=sys.stderr)
        return False
    except pd.errors.ParserError as e:
        print(f"Error: Could not parse CSV file '{csv_filepath}': {e}", file=sys.stderr)
        return False
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return False

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Create SQLite database from UK Parliament members CSV file.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--csv-file',
        required=True,
        help='Path to the input CSV file containing MP data'
    )

    parser.add_argument(
        '--db-file',
        required=True,
        help='Path for the output SQLite database file'
    )

    # Parse command line arguments
    args = parser.parse_args()

    csv_filepath = args.csv_file
    db_filepath = args.db_file

    # Validate input CSV file exists and is readable
    if not os.path.isfile(csv_filepath):
        print(f"Error: CSV file '{csv_filepath}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(csv_filepath, 'r', encoding='utf-8') as f:
            pass
    except IOError as e:
        print(f"Error: Cannot read CSV file '{csv_filepath}': {e}", file=sys.stderr)
        sys.exit(1)

    # Validate output directory exists or can be created
    db_directory = os.path.dirname(db_filepath)
    if db_directory and not os.path.exists(db_directory):
        try:
            os.makedirs(db_directory)
            print(f"Created directory: {db_directory}")
        except OSError as e:
            print(f"Error: Cannot create directory '{db_directory}': {e}", file=sys.stderr)
            sys.exit(1)

    # Check if output file already exists and warn user
    if os.path.exists(db_filepath):
        print(f"Warning: Database file '{db_filepath}' already exists and will be replaced.")

    print(f"Processing CSV file: {csv_filepath}")
    print(f"Creating database: {db_filepath}")

    # Run the database creation function
    success = create_mps_database(csv_filepath, db_filepath)

    if not success:
        print("Database creation failed.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()