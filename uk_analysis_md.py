import requests
import sqlite3
import json
import datetime
import os
import time
import re
import configparser
import argparse
import sys

# This script analyzes parliamentary speeches using the Ollama API and stores results in a SQLite database.
# Expects the politician information to be in a file called members.db

# --- Configuration (will be loaded from uk_config.cfg) ---
SOURCE_DATABASE_NAME = ""
ANALYSIS_DATABASE_NAME = ""
OLLAMA_API_URL = ""
OLLAMA_MODEL_NAME = ""
OLLAMA_REQUEST_TIMEOUT = 0
OLLAMA_REFINER_MODEL_NAME = ""
OLLAMA_REFINER_REQUEST_TIMEOUT = 0
MD_ANALYSIS_FILENAME_TEMPLATE = ""
NUMBER_OF_MEMBERS_TO_ANALYZE = 0
INITIAL_ANALYSIS_PROMPT_TEMPLATE = ""
REFINEMENT_ANALYSIS_PROMPT_TEMPLATE = ""

# New global variable for log file name
LOG_FILE_NAME = ""

START_MEMBER_INDEX = 0  # New variable for starting position


def load_configuration(config_file='uk_config.cfg'):
    """
    Loads configuration from the specified INI file.
    """
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        print(f"Error: Configuration file '{config_file}' not found. Please create it.")
        exit(1)
    
    try:
        config.read(config_file)

        # Database settings
        global SOURCE_DATABASE_NAME
        global ANALYSIS_DATABASE_NAME
        SOURCE_DATABASE_NAME = config.get('Database', 'SOURCE_DATABASE_NAME')
        ANALYSIS_DATABASE_NAME = config.get('Database', 'ANALYSIS_DATABASE_NAME')

        # Ollama settings
        global OLLAMA_API_URL
        global OLLAMA_MODEL_NAME
        global OLLAMA_REQUEST_TIMEOUT
        global OLLAMA_REFINER_MODEL_NAME
        global OLLAMA_REFINER_REQUEST_TIMEOUT
        OLLAMA_API_URL = config.get('Ollama', 'OLLAMA_API_URL')
        OLLAMA_MODEL_NAME = config.get('Ollama', 'OLLAMA_MODEL_NAME')
        OLLAMA_REQUEST_TIMEOUT = config.getint('Ollama', 'OLLAMA_REQUEST_TIMEOUT')
        OLLAMA_REFINER_MODEL_NAME = config.get('Ollama', 'OLLAMA_REFINER_MODEL_NAME')
        OLLAMA_REFINER_REQUEST_TIMEOUT = config.getint('Ollama', 'OLLAMA_REFINER_REQUEST_TIMEOUT')

        # Output settings
        global MD_ANALYSIS_FILENAME_TEMPLATE
        MD_ANALYSIS_FILENAME_TEMPLATE = config.get('Output', 'MD_ANALYSIS_FILENAME_TEMPLATE')

        # Analysis Limits
        global NUMBER_OF_MEMBERS_TO_ANALYZE
        NUMBER_OF_MEMBERS_TO_ANALYZE = config.getint('AnalysisLimits', 'NUMBER_OF_MEMBERS_TO_ANALYZE')

        # Prompt Templates
        global INITIAL_ANALYSIS_PROMPT_TEMPLATE
        global REFINEMENT_ANALYSIS_PROMPT_TEMPLATE
        INITIAL_ANALYSIS_PROMPT_TEMPLATE = config.get('Prompts.InitialAnalysis', 'template')
        REFINEMENT_ANALYSIS_PROMPT_TEMPLATE = config.get('Prompts.RefinementAnalysis', 'template')

        # Logging
        global LOG_FILE_NAME
        LOG_FILE_NAME = config.get('Logging', 'LOG_FILE_NAME')

        print(f"Configuration loaded successfully from '{config_file}'.")

    except configparser.Error as e:
        print(f"Error reading configuration file '{config_file}': {e}")
        exit(1)
    except Exception as e:
        print(f"An unexpected error occurred while loading configuration: {e}")
        exit(1)


def setup_analysis_db_connection(db_name):
    """Connects to/creates the SQLite database for analysis results."""
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        # Creates the table for Ollama analyses.
        # Note: No FOREIGN KEY here as the 'members' table is in another database file.
        # iid, name, party will be duplicated/referenced conceptually.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ollama_analysis (
                iid TEXT PRIMARY KEY,        -- Original IID from the members table
                name TEXT,                   -- Member's name
                party TEXT,                  -- Member's party
                initial_analysis_text TEXT,  -- First analysis from Ollama
                analysis_text TEXT,          -- The refined, action-oriented analysis
                last_analyzed_date TEXT      -- Date of last analysis
            )
        ''')
        conn.commit()
        print(f"Connected to analysis database '{db_name}'. Table 'ollama_analysis' is ready.")
        return conn, cursor
    except sqlite3.Error as e:
        print(f"Database error when connecting/setting up analysis database {db_name}: {e}")
        return None, None


def _call_ollama_api(prompt_text, member_name_logging_tag, model_name, timeout, api_url):
    """Generic function to call Ollama API and return raw text response."""
    print(f"  Querying Ollama (model: {model_name}) for: {member_name_logging_tag}...")
    payload = {
        "model": model_name,
        "prompt": prompt_text,
        "stream": False
    }
    try:
        response = requests.post(api_url, json=payload, timeout=timeout)
        response.raise_for_status()
        raw_response_text = response.json().get("response",
                                                f"No response content from Ollama for {member_name_logging_tag}.")
        print(f"    Ollama (model: {model_name}) call successful for {member_name_logging_tag}.")
        return raw_response_text
    except requests.exceptions.Timeout:
        error_msg = f"Timeout: Ollama API (model: {model_name}) did not respond in time for {member_name_logging_tag}."
        print(f"    {error_msg}")
        return error_msg
    except requests.exceptions.ConnectionError:
        error_msg = f"Connection Error: Check if Ollama (model: {model_name}) is running and accessible for {member_name_logging_tag}."
        print(f"    {error_msg}")
        return error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Request Exception with Ollama (model: {model_name}) for {member_name_logging_tag}: {e}"
        print(f"    {error_msg}")
        return error_msg
    except json.JSONDecodeError:
        error_msg = f"JSON Decode Error: Could not parse response from Ollama (model: {model_name}) for {member_name_logging_tag}."
        print(f"    {error_msg}")
        return error_msg


def analyze_text_with_ollama(text_to_analyze, member_name):
    """Sends text to Ollama for initial analysis and returns the raw text response."""
    logging_tag = f"initial analysis of {member_name}"
    print(f"  Starting initial analysis for {member_name} with Ollama (model: {OLLAMA_MODEL_NAME})...")

    clean_text = re.sub(r'<[^>]+>', ' ', text_to_analyze)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    if not clean_text.strip():
        print(f"    No text to analyze for {member_name} after cleaning.")
        return "No text available for analysis after HTML cleaning."

    prompt = INITIAL_ANALYSIS_PROMPT_TEMPLATE.format(
        member_name=member_name,
        speeches_text=clean_text[:15000]
    )
    return _call_ollama_api(prompt, logging_tag, OLLAMA_MODEL_NAME, OLLAMA_REQUEST_TIMEOUT, OLLAMA_API_URL)


def refine_analysis_with_ollama(initial_analysis_text, member_name):
    """Sends initial analysis to Ollama to get a more concise and action-oriented version."""
    logging_tag = f"refinement of analysis for {member_name}"
    print(f"  Starting refinement of analysis for {member_name} with Ollama (model: {OLLAMA_REFINER_MODEL_NAME})...")

    error_keywords = ["Timeout:", "Connection Error:", "Request Exception", "JSON Decode Error", "No response content",
                      "No text available"]
    if any(err_keyword in initial_analysis_text for err_keyword in error_keywords):
        print(
            f"    Skipping refinement for {member_name} due to error in initial analysis: '{initial_analysis_text[:100]}...'")
        return f"Refinement skipped due to error in initial analysis. Initial error: {initial_analysis_text}"

    prompt = REFINEMENT_ANALYSIS_PROMPT_TEMPLATE.format(
        member_name=member_name,
        initial_analysis_text=initial_analysis_text
    )
    return _call_ollama_api(prompt, logging_tag, OLLAMA_REFINER_MODEL_NAME, OLLAMA_REFINER_REQUEST_TIMEOUT,
                            OLLAMA_API_URL)


def log_analysis_entry(member_name, party, speeches_size_chars,
                       initial_analysis_start_time, initial_analysis_end_time,
                       refined_analysis_start_time, refined_analysis_end_time):
    """Writes a single entry to the analysis log file."""
    log_file_path = LOG_FILE_NAME
    file_exists = os.path.exists(log_file_path)

    with open(log_file_path, 'a', encoding='utf-8') as f:
        if not file_exists:
            # Write header if file is new
            f.write("Timestamp,Member Name,Party,Speeches Size (Chars),Initial Analysis Start,Initial Analysis End,Refined Analysis Start,Refined Analysis End\n")
        
        current_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format times as ISO strings, handling potential None if analysis failed
        initial_start_str = initial_analysis_start_time.isoformat() if initial_analysis_start_time else "N/A"
        initial_end_str = initial_analysis_end_time.isoformat() if initial_analysis_end_time else "N/A"
        refined_start_str = refined_analysis_start_time.isoformat() if refined_analysis_start_time else "N/A"
        refined_end_str = refined_analysis_end_time.isoformat() if refined_analysis_end_time else "N/A"

        log_line = f"{current_timestamp},{member_name},{party},{speeches_size_chars},{initial_start_str},{initial_end_str},{refined_start_str},{refined_end_str}\n"
        f.write(log_line)
    print(f"  Log entry added for {member_name} to '{LOG_FILE_NAME}'.")


def perform_ollama_analysis_for_members(source_cursor, analysis_conn, analysis_cursor):
    """Retrieves speeches for members from the source database,
    analyzes with Ollama (two-stage) and saves the result in the analysis database."""
    print(f"\nStarting Ollama analysis (two-stage) for {NUMBER_OF_MEMBERS_TO_ANALYZE} members...")

    sql_query = f"SELECT iid, name, party FROM speeches ORDER BY iid LIMIT {NUMBER_OF_MEMBERS_TO_ANALYZE} OFFSET {START_MEMBER_INDEX}"
    try:
        source_cursor.execute(sql_query)
        members = source_cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error when fetching members from the source database '{SOURCE_DATABASE_NAME}': {e}")
        return []

    all_analyses_data = []
    if not members:
        print(f"No members found in source database '{SOURCE_DATABASE_NAME}'. Aborting analysis.")
        return all_analyses_data

    if len(members) < NUMBER_OF_MEMBERS_TO_ANALYZE:
        print(f"WARNING: Only {len(members)} member(s) found in source database. Analyzing the one(s) found.")
    
    print(f"The following members will be processed (max first {NUMBER_OF_MEMBERS_TO_ANALYZE} from source database): {[m[1] for m in members]}")

    for iid, name, party in members:
        actual_member_position = START_MEMBER_INDEX + members.index((iid, name, party)) + 1
        print(f"\nProcessing member {actual_member_position}: {name} ({party}) (IID: {iid})")

        initial_analysis_raw = "Could not initiate initial analysis."
        refined_analysis_raw = "Could not initiate refined analysis."
        
        speeches_size_chars = 0
        initial_analysis_start_time = None
        initial_analysis_end_time = None
        refined_analysis_start_time = None
        refined_analysis_end_time = None

        try:
            source_cursor.execute("SELECT speech_text FROM speeches WHERE iid = ?", (iid,))
            speeches_texts = [row[0] for row in source_cursor.fetchall() if row[0]]
        except sqlite3.Error as e:
            error_message = f"Database error when fetching speeches for {name} from the source database: {e}"
            print(f"  {error_message}")
            initial_analysis_raw = error_message
            refined_analysis_raw = error_message
        else:
            if not speeches_texts:
                error_message = "No speeches to analyze in the database."
                print(f"  {error_message} for {name}.")
                initial_analysis_raw = error_message
                refined_analysis_raw = error_message
            else:
                combined_speeches = "\n\n---\n\n".join(speeches_texts)
                speeches_size_chars = len(combined_speeches) # Get size of combined speeches

                if not combined_speeches.strip():
                    error_message = "Speeches are empty after concatenation."
                    print(f"  {error_message} for {name}.")
                    initial_analysis_raw = error_message
                    refined_analysis_raw = error_message
                else:
                    initial_analysis_start_time = datetime.datetime.now()
                    initial_analysis_raw = analyze_text_with_ollama(combined_speeches, name)
                    initial_analysis_end_time = datetime.datetime.now()

                    # Only attempt refinement if initial analysis was not an error
                    error_keywords = ["Timeout:", "Connection Error:", "Request Exception", "JSON Decode Error", "No response content", "No text available"]
                    if not any(err_keyword in initial_analysis_raw for err_keyword in error_keywords):
                        refined_analysis_start_time = datetime.datetime.now()
                        refined_analysis_raw = refine_analysis_with_ollama(initial_analysis_raw, name)
                        refined_analysis_end_time = datetime.datetime.now()
                    else:
                        print(f"    Skipping refinement for {name} due to error in initial analysis.")

        # Log the analysis times and details
        log_analysis_entry(
            member_name=name,
            party=party,
            speeches_size_chars=speeches_size_chars,
            initial_analysis_start_time=initial_analysis_start_time,
            initial_analysis_end_time=initial_analysis_end_time,
            refined_analysis_start_time=refined_analysis_start_time,
            refined_analysis_end_time=refined_analysis_end_time
        )

        try:
            current_date = datetime.date.today().isoformat()
            analysis_cursor.execute("""
                INSERT OR REPLACE INTO ollama_analysis (iid, name, party, initial_analysis_text, analysis_text, last_analyzed_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (iid, name, party, initial_analysis_raw, refined_analysis_raw, current_date))
            analysis_conn.commit()
            print(
                f"  Analyses (initial and refined) for {name} saved/updated in analysis database '{ANALYSIS_DATABASE_NAME}'.")
        except sqlite3.Error as e:
            print(f"  Database error when saving analysis for {name} in analysis database '{ANALYSIS_DATABASE_NAME}': {e}")
            analysis_conn.rollback()

        all_analyses_data.append({
            "iid": iid,
            "name": name,
            "party": party,
            "analysis": refined_analysis_raw,
            "initial_analysis": initial_analysis_raw
        })

        is_last_member = (members.index((iid, name, party)) == len(members) - 1)
        if len(members) > 1 and not is_last_member:
            print(f"  Waiting 1 second before next member...")
            time.sleep(1)

    print(f"\nOllama analysis (two-stage) complete for the processed members. Results in '{ANALYSIS_DATABASE_NAME}'.")
    return all_analyses_data


def generate_analysis_md(analysis_data, filename_template_base, date_from_str, date_to_str):
    """Generates a Markdown page displaying both initial and refined Ollama analysis."""
    print("Generating Markdown page with Ollama analyses (initial and refined)...")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    num_members_analyzed = len(analysis_data)
    
    # Add subset information to filename
    if START_MEMBER_INDEX > 0 or num_members_analyzed < 100:
        subset_info = f"_subset_{START_MEMBER_INDEX + 1}_to_{START_MEMBER_INDEX + num_members_analyzed}"
        filename_parts = filename_template_base.rsplit('.', 1)
        if len(filename_parts) == 2:
            md_filename = f"{filename_parts[0]}{subset_info}.{filename_parts[1]}"
        else:
            md_filename = f"{filename_template_base}{subset_info}"
    else:
        md_filename = filename_template_base.format(
            num_members=num_members_analyzed,
            date_from=date_from_str,
            date_to=date_to_str
        )
    
    print(f"Markdown file will be saved as: {md_filename}")

    md_content = f"""
# Comparative Analysis of Parliament Members' Speeches (Ollama)
## Models: Initial ({OLLAMA_MODEL_NAME}), Refiner ({OLLAMA_REFINER_MODEL_NAME}). Speech data from '{SOURCE_DATABASE_NAME}' (period up to {date_to_str}).
"""
    if not analysis_data:
        md_content += f"No analysis data to display. Check that the source database '{SOURCE_DATABASE_NAME}' contains members and that they have speeches."
    else:
        sorted_analysis_data = sorted(analysis_data, key=lambda x: x['name'])
        for member_data in sorted_analysis_data:
            initial_analysis_class = "analysis-content"
            refined_analysis_class = "analysis-content"
            error_keywords_md = ["Fel vid", "Timeout", "Inga anföranden", "Ingen text", "Anslutningsfel",
                                   "No response content", "Refinement skipped", "Kunde inte initiera"]

            # Check for errors in initial analysis
            if any(err_key.lower() in member_data.get('initial_analysis', '').lower() for err_key in
                   error_keywords_md):
                initial_analysis_class += " error-analysis"
            # Check for errors in refined analysis (key 'analysis')
            if any(err_key.lower() in member_data.get('analysis', '').lower() for err_key in error_keywords_md):
                refined_analysis_class += " error-analysis"

            md_content += f"""
---
## {member_data['name']}
**Party**: {member_data['party'] if member_data['party'] else 'Unknown'}

### Initial Analysis ({OLLAMA_MODEL_NAME})
{member_data.get('initial_analysis', 'Initial analysis data missing.')}

### Refined & Action-Oriented Analysis ({OLLAMA_REFINER_MODEL_NAME})
{member_data.get('analysis', 'Refined analysis data missing.')}
"""
    md_content += f"""
*Analyses generated with Ollama. Speech data from '{SOURCE_DATABASE_NAME}'. Analysis results saved in '{ANALYSIS_DATABASE_NAME}'.*
"""
    try:
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Markdown file with comparative analyses '{md_filename}' has been created.")
        print(f"You can find it at: {os.path.abspath(md_filename)}")
    except IOError as e:
        print(f"Could not write to file {md_filename}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze UK Parliament speeches using Ollama API with subset processing capability.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--start-index',
        type=int,
        default=0,
        help='Starting member index (0-based). Skip this many members before beginning analysis. Default: 0'
    )

    parser.add_argument(
        '--count',
        type=int,
        help='Number of members to analyze. Overrides config file setting if provided.'
    )

    args = parser.parse_args()

    print("Starting Ollama analysis script for Parliament Speeches...")

    load_configuration()

    global START_MEMBER_INDEX, NUMBER_OF_MEMBERS_TO_ANALYZE
    START_MEMBER_INDEX = args.start_index

    if args.count is not None:
        if args.count <= 0:
            print("Error: --count must be a positive integer.", file=sys.stderr)
            sys.exit(1)
        NUMBER_OF_MEMBERS_TO_ANALYZE = args.count
        print(f"Overriding config file: analyzing {NUMBER_OF_MEMBERS_TO_ANALYZE} members")

    if START_MEMBER_INDEX < 0:
        print("Error: --start-index must be non-negative.", file=sys.stderr)
        sys.exit(1)

    print(f"Configuration: Starting from member index {START_MEMBER_INDEX}, analyzing {NUMBER_OF_MEMBERS_TO_ANALYZE} members")

    date_to = datetime.date.today()
    date_from = date_to - datetime.timedelta(days=365)
    date_from_str = date_from.strftime("%Y-%m-%d")
    date_to_str = date_to.strftime("%Y-%m-%d")

    source_conn = None
    analysis_conn = None
    source_cursor = None

    try:
        source_conn = sqlite3.connect(SOURCE_DATABASE_NAME)
        source_cursor = source_conn.cursor()
        print(f"Connected to source database '{SOURCE_DATABASE_NAME}' for reading.")
    except sqlite3.Error as e:
        print(f"Could not connect to source database {SOURCE_DATABASE_NAME}: {e}. Exiting.")
        return

    analysis_conn, analysis_cursor = setup_analysis_db_connection(ANALYSIS_DATABASE_NAME)
    if not analysis_conn or not analysis_cursor:
        if source_conn: source_conn.close()
        print("Exiting due to analysis database error.")
        return

    try:
        all_member_analyses = perform_ollama_analysis_for_members(source_cursor, analysis_conn, analysis_cursor)

        if all_member_analyses:
            generate_analysis_md(all_member_analyses, MD_ANALYSIS_FILENAME_TEMPLATE, date_from_str, date_to_str)
        else:
            print("No analysis data generated (e.g., no members in source database), not creating Markdown report.")

    finally:
        if source_conn:
            source_conn.close()
            print(f"Source database connection '{SOURCE_DATABASE_NAME}' closed.")
        if analysis_conn:
            analysis_conn.close()
            print(f"Analysis database connection '{ANALYSIS_DATABASE_NAME}' closed.")

    print("Ollama analysis process (two-stage, separate DB) is complete.")


if __name__ == "__main__":
    main()