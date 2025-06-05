import requests
import sqlite3
import json
import datetime
import os
import time
import re  # För HTML-rensning

# --- Databas Konfiguration ---
SOURCE_DATABASE_NAME = "riksdagen_anforanden.db"  # For reading members and speeches
ANALYSIS_DATABASE_NAME = "ollama_analysis_results.db"  # For storing Ollama analysis results

# --- Ollama Konfiguration ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL_NAME = "Gemma3"  # Model for initial analysis (e.g., "llama3", "gemma:7b")
OLLAMA_REQUEST_TIMEOUT = 180  # Sekunder

# --- Ollama Refiner/Critic Konfiguration ---
OLLAMA_REFINER_MODEL_NAME = "Gemma3"  # Model for refining (can be same or different, e.g., "llama3", "gemma:7b")
OLLAMA_REFINER_REQUEST_TIMEOUT = 180  # Sekunder for refiner

# --- HTML Output Konfiguration ---
# Filename will be further customized in generate_analysis_html based on number of members
HTML_ANALYSIS_FILENAME_TEMPLATE = "Riksdagen_Jämförande_Ledamotsanalys_Ollama_{date_from}_till_{date_to}.html"


def setup_analysis_db_connection(db_name):
    """Ansluter till/skapar SQLite-databasen för analysresultat."""
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        # Skapar tabellen för Ollama-analyser.
        # Notera: Ingen FOREIGN KEY här eftersom 'members'-tabellen är i en annan databasfil.
        # iid, name, party kommer att dupliceras/refereras konceptuellt.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ollama_analysis (
                iid TEXT PRIMARY KEY,        -- Ursprungligt IID från members-tabellen
                name TEXT,                   -- Ledamotens namn
                party TEXT,                  -- Ledamotens parti
                initial_analysis_text TEXT,  -- Första analysen från Ollama
                analysis_text TEXT,          -- Den raffinerade, handlingsinriktade analysen
                last_analyzed_date TEXT      -- Datum för senaste analys
            )
        ''')
        conn.commit()
        print(f"Ansluten till analysdatabas '{db_name}'. Tabell 'ollama_analysis' är redo.")
        return conn, cursor
    except sqlite3.Error as e:
        print(f"Databasfel vid anslutning/setup av analysdatabas {db_name}: {e}")
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
    """Skickar text till Ollama för initial analys och returnerar råtextsvaret."""
    logging_tag = f"initial analysis of {member_name}"
    print(f"  Starting initial analysis for {member_name} with Ollama (model: {OLLAMA_MODEL_NAME})...")

    clean_text = re.sub(r'<[^>]+>', ' ', text_to_analyze)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    if not clean_text.strip():
        print(f"    No text to analyze for {member_name} after cleaning.")
        return "Ingen text tillgänglig för analys efter HTML-rensning."

    prompt = f"""Du är en AI-assistent som specialiserat sig på att analysera politiska texter.
Analysera följande samlade anföranden från riksdagsledamoten {member_name}.
Fokusera på att identifiera:
1.  Huvudsakliga ämnen som tas upp (ge en lista med max 5-7 nyckelämnen).
2.  Generellt sentiment (t.ex. positivt, negativt, neutralt, blandat) med en kort motivering.
3.  Ledamotens argumentativa stil (t.ex. logisk, emotionell, faktabaserad, retorisk, anekdotisk, etc.) med exempel om möjligt.
4.  Nyckelargument och möjliga sätt att närma sig denna parliamentariker. 
Ge en koncis sammanfattning av din analys i punktform eller korta stycken.

Formatera allt detta i HTML. Gör det så robust som möjligt.  

Anföranden:
---
{clean_text[:15000]} 
---
Din analys:
"""
    return _call_ollama_api(prompt, logging_tag, OLLAMA_MODEL_NAME, OLLAMA_REQUEST_TIMEOUT, OLLAMA_API_URL)


def refine_analysis_with_ollama(initial_analysis_text, member_name):
    """Skickar initial analys till Ollama för att få en mer koncis och handlingsinriktad version."""
    logging_tag = f"refinement of analysis for {member_name}"
    print(f"  Starting refinement of analysis for {member_name} with Ollama (model: {OLLAMA_REFINER_MODEL_NAME})...")

    error_keywords = ["Timeout:", "Connection Error:", "Request Exception", "JSON Decode Error", "No response content",
                      "Ingen text tillgänglig"]
    if any(err_keyword in initial_analysis_text for err_keyword in error_keywords):
        print(
            f"    Skipping refinement for {member_name} due to error in initial analysis: '{initial_analysis_text[:100]}...'")
        return f"Refinement skipped due to error in initial analysis. Initial error: {initial_analysis_text}"

    prompt = f"""You are an expert political strategist AI. Your task is to refine an existing analysis of parliamentarian {member_name}.
The goal is to transform the initial analysis into a version that is highly succinct and sharply focused on actionable insights for someone interested in effectively working with or lobbying this politician.

INITIAL ANALYSIS TO REFINE:
---
{initial_analysis_text}
---

Rewrite and replace the initial analysis. Your new, refined output must be:
1.  **Succinct:** Eliminate all non-essential information. Be direct and to the point. Use concise language.
2.  **Actionable:** For each key observation (e.g., topics, sentiment, argumentative style), explicitly state the implications or concrete strategies for engagement. For instance, if the politician is 'fact-based', an actionable insight would be: "Strategy: Engage using well-researched data and concrete evidence; emotional appeals are likely to be less effective."
3.  **Focused:** Prioritize the top 2-3 most critical insights that directly inform engagement strategies. What must someone absolutely know to successfully interact with this MP?
4.  **Clear Structure:** Present the refined analysis in a clear, easily digestible format, preferably using bullet points under key headings. The final output must be in English.

Do not offer a critique of the initial analysis itself; instead, directly provide the improved, refined analysis as the output.

REFINED AND ACTIONABLE ANALYSIS of {member_name}:
"""
    return _call_ollama_api(prompt, logging_tag, OLLAMA_REFINER_MODEL_NAME, OLLAMA_REFINER_REQUEST_TIMEOUT,
                            OLLAMA_API_URL)


def perform_ollama_analysis_for_members(source_cursor, analysis_conn, analysis_cursor):
    """Hämtar anföranden för de två första ledamöterna från källdatabasen,
    analyserar med Ollama (tvåstegs) och sparar resultatet i analysdatabasen."""
    print("\nPåbörjar Ollama-analys (tvåstegs) för de två första ledamöterna...")

    sql_query = "SELECT iid, name, party FROM members ORDER BY iid LIMIT 2"
    try:
        source_cursor.execute(sql_query)
        members = source_cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Databasfel vid hämtning av ledamöter från källdatabasen '{SOURCE_DATABASE_NAME}': {e}")
        return []

    all_analyses_data = []
    if not members:
        print(f"Inga ledamöter hittades i källdatabasen '{SOURCE_DATABASE_NAME}'. Avbryter analys.")
        return all_analyses_data

    if len(members) < 2:
        print(f"VARNING: Endast {len(members)} ledamot hittades i källdatabasen. Analyserar den/de som hittades.")
    print(f"Följande ledamöter kommer att bearbetas (max 2 första från källdatabasen): {[m[1] for m in members]}")

    for iid, name, party in members:
        print(f"\nBearbetar ledamot: {name} ({party}) (IID: {iid})")

        initial_analysis_raw = "Kunde inte initiera initial analys."  # Default error
        refined_analysis_raw = "Kunde inte initiera raffinerad analys."  # Default error

        try:
            source_cursor.execute("SELECT anforandetext FROM speeches WHERE iid = ? ORDER BY dok_datum DESC", (iid,))
            speeches_texts = [row[0] for row in source_cursor.fetchall() if row[0]]
        except sqlite3.Error as e:
            error_message = f"Databasfel vid hämtning av anföranden för {name} från källdatabasen: {e}"
            print(f"  {error_message}")
            initial_analysis_raw = error_message
            refined_analysis_raw = error_message  # Propagate error
        else:
            if not speeches_texts:
                error_message = "Inga anföranden att analysera i databasen."
                print(f"  {error_message} för {name}.")
                initial_analysis_raw = error_message
                refined_analysis_raw = error_message
            else:
                combined_speeches = "\n\n---\n\n".join(speeches_texts)
                if not combined_speeches.strip():
                    error_message = "Anföranden är tomma efter sammanfogning."
                    print(f"  {error_message} för {name}.")
                    initial_analysis_raw = error_message
                    refined_analysis_raw = error_message
                else:
                    initial_analysis_raw = analyze_text_with_ollama(combined_speeches, name)
                    refined_analysis_raw = refine_analysis_with_ollama(initial_analysis_raw, name)

        try:
            current_date = datetime.date.today().isoformat()
            analysis_cursor.execute("""
                INSERT OR REPLACE INTO ollama_analysis (iid, name, party, initial_analysis_text, analysis_text, last_analyzed_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (iid, name, party, initial_analysis_raw, refined_analysis_raw, current_date))
            analysis_conn.commit()
            print(
                f"  Analyser (initial och refined) för {name} sparade/uppdaterade i analysdatabasen '{ANALYSIS_DATABASE_NAME}'.")
        except sqlite3.Error as e:
            print(f"  Databasfel vid sparande av analys för {name} i analysdatabasen '{ANALYSIS_DATABASE_NAME}': {e}")
            analysis_conn.rollback()

        all_analyses_data.append({
            "iid": iid,
            "name": name,
            "party": party,
            "analysis": refined_analysis_raw,  # This is the refined analysis
            "initial_analysis": initial_analysis_raw  # This is the initial analysis
        })

        is_last_member = (members.index((iid, name, party)) == len(members) - 1)
        if len(members) > 1 and not is_last_member:
            print(f"  Väntar 1 sekund innan nästa ledamot...")
            time.sleep(1)

    print(f"\nOllama-analys (tvåstegs) klar för de bearbetade ledamöterna. Resultat i '{ANALYSIS_DATABASE_NAME}'.")
    return all_analyses_data


def generate_analysis_html(analysis_data, filename_template_base, date_from_str, date_to_str):
    """Genererar en HTML-sida som visar både initial och raffinerad Ollama-analys."""
    print("Genererar HTML-sida med Ollama-analyser (initial och raffinerad)...")
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    effective_filename_template = filename_template_base
    if len(analysis_data) == 2:
        member_names_for_file = "_och_".join(
            sorted([re.sub(r'\W+', '', data['name'].replace(" ", "_")) for data in analysis_data]))
        base_template = "Riksdagen_Jämförande_Ledamotsanalys_Ollama_{member_names_part}_{date_from}_till_{date_to}.html"
        effective_filename_template = base_template.format(member_names_part=member_names_for_file,
                                                           date_from="{date_from}", date_to="{date_to}")
        print(f"Använder anpassat filnamn för 2 ledamöter.")
    elif len(analysis_data) == 1:
        member_name_for_file = re.sub(r'\W+', '', analysis_data[0]['name'].replace(" ", "_"))
        base_template = "Riksdagen_Jämförande_Ledamotsanalys_Ollama_{member_name_part}_{date_from}_till_{date_to}.html"
        effective_filename_template = base_template.format(member_name_part=member_name_for_file,
                                                           date_from="{date_from}", date_to="{date_to}")
        print(f"Använder anpassat filnamn för 1 ledamot.")
    else:  # Fallback to slightly modified base template name if 0 or >2 members
        effective_filename_template = HTML_ANALYSIS_FILENAME_TEMPLATE.replace(
            "Ledamotsanalys", "Jämförande_Ledamotsanalys_Flera"
        ) if len(analysis_data) > 0 else HTML_ANALYSIS_FILENAME_TEMPLATE

    html_filename = effective_filename_template.format(date_from=today_str, date_to=today_str)
    print(f"HTML-fil kommer att sparas som: {html_filename}")

    html_content = f"""
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jämförande Riksdagsledamöters Anförandeanalys (Ollama)</title>
    <style>
        body {{ font-family: 'Arial', sans-serif; margin: 0; padding: 0; background-color: #f4f7f6; color: #333; }}
        .page-container {{ max-width: 1200px; margin: 20px auto; background: #fff; padding: 25px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; text-align: center; border-bottom: 2px solid #3498db; padding-bottom: 15px; margin-bottom: 10px; }}
        .page-subtitle {{ text-align:center; font-size:0.9em; color: #777; margin-bottom: 25px;}}
        .member-container {{ margin-bottom: 40px; }}
        .member-header {{ padding: 15px; background-color: #e9ecef; border-radius: 8px 8px 0 0; border: 1px solid #ddd; border-bottom: none;}}
        .member-header h2 {{ font-size: 1.8em; color: #3498db; margin: 0 0 5px 0; }}
        .member-header .party {{ font-style: italic; color: #555; display: block; }}
        .analyses-grid {{ display: flex; flex-wrap: wrap; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px; }}
        .analysis-column {{ flex: 1; min-width: 300px; padding: 20px; box-sizing: border-box; }}
        .analysis-column:first-child {{ border-right: 1px solid #eee; }}
        .analysis-column h3 {{ font-size: 1.3em; color: #17a2b8; margin-top: 0; margin-bottom: 10px; border-bottom: 1px solid #dee2e6; padding-bottom: 8px; }}
        .analysis-content {{ background-color: #fdfdff; padding: 15px; border-radius: 6px; line-height: 1.6; white-space: pre-wrap; font-size: 0.95em; border: 1px solid #eaf2f8; min-height: 150px; overflow-x: auto;}}
        .error-analysis {{ color: #c0392b; font-style: italic; background-color: #fbeaea; }}
        footer {{ text-align: center; margin-top: 30px; padding-top:15px; border-top:1px solid #eee; font-size: 0.9em; color: #7f8c8d; }}
         @media (max-width: 768px) {{
            .analyses-grid {{ flex-direction: column; }}
            .analysis-column:first-child {{ border-right: none; border-bottom: 1px solid #eee; }}
        }}
    </style>
</head>
<body>
    <div class="page-container">
        <h1>Jämförande Analys av Riksdagsledamöters Anföranden</h1>
        <p class="page-subtitle">Visar initial analys och en raffinerad, handlingsinriktad version sida vid sida.<br>
        Modeller: Initial ({OLLAMA_MODEL_NAME}), Refiner ({OLLAMA_REFINER_MODEL_NAME}). Anförandedata från '{SOURCE_DATABASE_NAME}' (period upp till {date_to_str}).</p>
"""
    if not analysis_data:
        html_content += "<p style='text-align:center;'>Ingen analysdata att visa. Kontrollera att källdatabasen '{SOURCE_DATABASE_NAME}' innehåller ledamöter och att de har anföranden.</p>"
    else:
        sorted_analysis_data = sorted(analysis_data, key=lambda x: x['name'])
        for member_data in sorted_analysis_data:
            initial_analysis_class = "analysis-content"
            refined_analysis_class = "analysis-content"
            error_keywords_html = ["Fel vid", "Timeout", "Inga anföranden", "Ingen text", "Anslutningsfel",
                                   "No response content", "Refinement skipped", "Kunde inte initiera"]

            # Check for errors in initial analysis
            if any(err_key.lower() in member_data.get('initial_analysis', '').lower() for err_key in
                   error_keywords_html):
                initial_analysis_class += " error-analysis"
            # Check for errors in refined analysis (key 'analysis')
            if any(err_key.lower() in member_data.get('analysis', '').lower() for err_key in error_keywords_html):
                refined_analysis_class += " error-analysis"

            html_content += f"""
        <div class="member-container">
            <div class="member-header">
                <h2>{member_data['name']}</h2>
                <span class="party">Parti: {member_data['party'] if member_data['party'] else 'Okänt'}</span>
            </div>
            <div class="analyses-grid">
                <div class="analysis-column">
                    <h3>Initial Analys ({OLLAMA_MODEL_NAME})</h3>
                    <div class="{initial_analysis_class}">
                        {member_data.get('initial_analysis', 'Initial analysdata saknas.')}
                    </div>
                </div>
                <div class="analysis-column">
                    <h3>Raffinerad & Handlingsinriktad Analys ({OLLAMA_REFINER_MODEL_NAME})</h3>
                    <div class="{refined_analysis_class}">
                        {member_data.get('analysis', 'Raffinerad analysdata saknas.')}
                    </div>
                </div>
            </div>
        </div>
"""
    html_content += """
    </div>
    <footer>
        Analyser genererade med Ollama. Anförandedata från '{SOURCE_DATABASE_NAME}'. Analysresultat sparade i '{ANALYSIS_DATABASE_NAME}'.
    </footer>
</body>
</html>
"""
    try:
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"HTML-fil med jämförande analyser '{html_filename}' har skapats.")
        print(f"Du hittar den på: {os.path.abspath(html_filename)}")
    except IOError as e:
        print(f"Kunde inte skriva till filen {html_filename}: {e}")


def main():
    """Huvudfunktion för Ollama-analys och rapportgenerering."""
    print("Startar Ollama-analysskript för Riksdagsanföranden...")

    date_to = datetime.date.today()
    # date_from is not directly used for speech selection logic in this script version,
    # but kept for context in HTML filename/header.
    date_from = date_to - datetime.timedelta(days=365)
    date_from_str = date_from.strftime("%Y-%m-%d")
    date_to_str = date_to.strftime("%Y-%m-%d")

    source_conn = None
    analysis_conn = None
    source_cursor = None

    try:
        # Anslutning till källdatabasen (läser ledamöter och anföranden)
        source_conn = sqlite3.connect(SOURCE_DATABASE_NAME)
        source_cursor = source_conn.cursor()
        print(f"Ansluten till källdatabas '{SOURCE_DATABASE_NAME}' för läsning.")
    except sqlite3.Error as e:
        print(f"Kunde inte ansluta till källdatabasen {SOURCE_DATABASE_NAME}: {e}. Avslutar.")
        return  # Exit if source DB cannot be opened

    # Anslutning till analysdatabasen (skriver analysresultat)
    analysis_conn, analysis_cursor = setup_analysis_db_connection(ANALYSIS_DATABASE_NAME)
    if not analysis_conn or not analysis_cursor:  # setup_analysis_db_connection handles its own print
        if source_conn: source_conn.close()  # Clean up source connection if analysis DB fails
        print("Avslutar på grund av fel med analysdatabasen.")
        return

    try:
        all_member_analyses = perform_ollama_analysis_for_members(source_cursor, analysis_conn, analysis_cursor)

        if all_member_analyses:
            generate_analysis_html(all_member_analyses, HTML_ANALYSIS_FILENAME_TEMPLATE, date_from_str, date_to_str)
        else:
            print("Ingen analysdata genererades (t.ex. inga ledamöter i källdatabasen), skapar inte HTML-rapport.")

    finally:  # Ensure connections are closed
        if source_conn:
            source_conn.close()
            print(f"Källdatabasanslutning '{SOURCE_DATABASE_NAME}' stängd.")
        if analysis_conn:
            analysis_conn.close()
            print(f"Analysdatabasanslutning '{ANALYSIS_DATABASE_NAME}' stängd.")

    print("Ollama-analysprocessen (tvåstegs, separat DB) är klar.")


if __name__ == "__main__":
    main()