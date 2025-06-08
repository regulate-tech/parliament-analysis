import sqlite3
import argparse
import os
import sys

def update_party_info(members_db="uk/members.db", speeches_db="uk/politician_speeches.db"):
    """
    Opens two SQLite databases, joins them on the common field 'iid',
    and updates the 'party' field in the 'speeches' table from the 'Party'
    field in the 'mps' table.

    Args:
        members_db (str): The filename of the members database.
        speeches_db (str): The filename of the speeches database.
    """
    try:
        # Connect to the speeches database
        conn_speeches = sqlite3.connect(speeches_db)
        cursor_speeches = conn_speeches.cursor()

        # Attach the members database to the speeches database connection
        cursor_speeches.execute(f"ATTACH DATABASE '{members_db}' AS members_db")

        # Update the 'party' field in the 'speeches' table
        # by joining with the 'mps' table from the attached database
        cursor_speeches.execute('''
            UPDATE speeches
            SET party = members_db.mps.Party
            FROM members_db.mps
            WHERE speeches.iid = members_db.mps.iid;
        ''')

        # Commit the changes
        conn_speeches.commit()
        print(f"Successfully updated 'party' field in '{speeches_db}' using data from '{members_db}'.")

    except sqlite3.Error as e:
        print(f"An SQLite error occurred: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Close the connection to the speeches database (which also detaches members_db)
        if conn_speeches:
            conn_speeches.close()

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Update party information in speeches database using members database.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--members-db',
        required=True,
        help='Path to the members database file (contains MP party information)'
    )

    parser.add_argument(
        '--speeches-db',
        required=True,
        help='Path to the speeches database file (to be updated with party information)'
    )

    # Parse command line arguments
    args = parser.parse_args()

    members_db_path = args.members_db
    speeches_db_path = args.speeches_db

    # Validate that both database files exist
    if not os.path.isfile(members_db_path):
        print(f"Error: Members database file '{members_db_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(speeches_db_path):
        print(f"Error: Speeches database file '{speeches_db_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Validate that files are readable
    try:
        with open(members_db_path, 'rb') as f:
            pass
    except IOError as e:
        print(f"Error: Cannot read members database file '{members_db_path}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(speeches_db_path, 'r+b') as f:
            pass
    except IOError as e:
        print(f"Error: Cannot read/write speeches database file '{speeches_db_path}': {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Using members database: {members_db_path}")
    print(f"Updating speeches database: {speeches_db_path}")

    # Run the update function
    update_party_info(members_db_path, speeches_db_path)

    # Optional: Verify the update
    print("\nVerifying update - showing first 5 records:")
    try:
        conn_verify = sqlite3.connect(speeches_db_path)
        cursor_verify = conn_verify.cursor()
        cursor_verify.execute("SELECT iid, name, party FROM speeches WHERE party != '' LIMIT 5")
        rows = cursor_verify.fetchall()
        if rows:
            for row in rows:
                print(f"ID: {row[0]}, Name: {row[1]}, Party: {row[2]}")
        else:
            print("No records found with party information.")
        conn_verify.close()
    except sqlite3.Error as e:
        print(f"Warning: Could not verify update: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()