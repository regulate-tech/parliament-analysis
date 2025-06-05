import requests
import xml.etree.ElementTree as ET
import os
import datetime
import sqlite3
import json  # För att bädda in data i HTML för JavaScript
from collections import defaultdict

# --- Konfiguration ---
MAX_SPEECHES_TO_FETCH = 1000  # Antal anföranden att hämta
DATABASE_NAME = "riksdagen_anforanden.db"
HTML_OUTPUT_FILENAME_TEMPLATE = "Riksdagen_Ledamotsanforanden_Interaktiv_{date_from}_till_{date_to}.html"


def fetch_xml_data(url):
    """Hämtar XML-data från den angivna URL:en."""
    try:
        print(f"Hämtar data från: {url}")
        response = requests.get(url, timeout=60)  # Ökad timeout
        response.raise_for_status()
        print("Data hämtad framgångsrikt.")
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Fel vid hämtning av data från {url}: {e}")
        return None


def get_text_from_element(element, tag_name, default_value=""):
    """Hjälpfunktion för att säkert hämta textinnehåll från ett XML-element."""
    if element is None:
        return default_value
    found = element.find(tag_name)
    return found.text.strip() if found is not None and found.text is not None else default_value


def setup_database(db_name):
    """Konfigurerar SQLite-databasen och skapar tabeller om de inte finns."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Tabell för ledamöter
    # iid är riksdagens unika ID för en intressent (person)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            iid TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            party TEXT
        )
    ''')

    # Tabell för anföranden
    # anforande_id är ett unikt ID för ett specifikt anförande-segment
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS speeches (
            anforande_id TEXT PRIMARY KEY,
            iid TEXT NOT NULL,                  -- Främmande nyckel till members.iid
            dok_id TEXT,                        -- Dokumentets ID (t.ex. protokoll, motion)
            dok_datum TEXT,
            avsnittsrubrik TEXT,
            dok_titel TEXT,                     -- Dokumentets titel (t.ex. "Protokoll 2023/24:1")
            anforandetext TEXT,
            anforande_url_xml TEXT UNIQUE,      -- URL till det specifika anförandets XML
            FOREIGN KEY (iid) REFERENCES members (iid)
        )
    ''')
    conn.commit()
    print(f"Databas '{db_name}' är redo med tabellerna 'members' och 'speeches'.")
    return conn, cursor


def fetch_speech_text_from_url(speech_xml_url):
    """Hämtar och returnerar anförandetexten från en specifik anforande_url_xml."""
    if not speech_xml_url:
        return "URL för anförande-XML saknas."

    speech_xml_content_bytes = fetch_xml_data(speech_xml_url)
    if not speech_xml_content_bytes:
        return "Kunde inte hämta XML för specifikt anförande."

    try:
        try:
            speech_xml_content_str = speech_xml_content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Försök med ISO-8859-1 om UTF-8 misslyckas, vanligt för äldre data.
            speech_xml_content_str = speech_xml_content_bytes.decode('iso-8859-1')

        speech_root = ET.fromstring(speech_xml_content_str)

        anforande_node = speech_root.find('.//anforande')
        if anforande_node is not None:
            text = get_text_from_element(anforande_node, 'anforandetext', "")
            if text: return text

        return get_text_from_element(speech_root, 'anforandetext', "Anförandetext kunde inte hittas.")
    except ET.ParseError as e:
        print(f"Fel vid XML-analys för {speech_xml_url}: {e}")
        return f"Fel vid XML-analys: {e}"
    except Exception as e:
        print(f"Oväntat fel vid bearbetning av {speech_xml_url}: {e}")
        return f"Oväntat fel: {e}"


def populate_database(conn, cursor, date_from_str, date_to_str):
    """Hämtar anföranden och lagrar dem i databasen."""
    print(f"Påbörjar datainhämtning för perioden {date_from_str} till {date_to_str}...")
    # Lade till anftyp=Anförande för att filtrera på faktiska anföranden
    api_list_url = (
        f"https://data.riksdagen.se/anforandelista/"
        f"?dfr={date_from_str}&dto={date_to_str}"
        f"&sz={MAX_SPEECHES_TO_FETCH}&anftyp=Anförande&utformat=xml&sort=datum&sortorder=desc"
    )

    main_xml_content_bytes = fetch_xml_data(api_list_url)
    if not main_xml_content_bytes:
        print("Misslyckades med att hämta anförandelistan. Databasen uppdateras inte.")
        return

    try:
        try:
            main_xml_content_str = main_xml_content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            main_xml_content_str = main_xml_content_bytes.decode('iso-8859-1')
        main_root = ET.fromstring(main_xml_content_str)
    except Exception as e:
        print(f"Fel vid avkodning/analys av XML för anförandelistan: {e}")
        return

    anforanden_elements = main_root.findall('anforande')
    total_in_list = len(anforanden_elements)
    print(f"Hittade {total_in_list} anföranden i listan för perioden (filtrerat på anftyp=Anförande).")
    if total_in_list == 0:
        print("Inga anföranden returnerades från API:et för den angivna perioden och filtret.")
        return
    if total_in_list >= MAX_SPEECHES_TO_FETCH:
        print(f"VARNING: Antalet anföranden når maxgränsen ({MAX_SPEECHES_TO_FETCH}). Alla kanske inte hämtas.")

    speeches_processed_count = 0
    speeches_added_to_db_count = 0
    members_added_to_db_count = 0

    for i, el in enumerate(anforanden_elements):
        print(f"\nBearbetar post {i + 1} av {total_in_list} från anförandelistan...")

        # För felsökning: Avkommentera för att se XML-strukturen för den första posten.
        # if i == 0:
        #     print("--- DEBUG: XML för första anförande-elementet i listan ---")
        #     ET.dump(el)
        #     print("--- SLUT DEBUG ---")

        iid_from_xml = get_text_from_element(el, 'iid')
        talare = get_text_from_element(el, 'talare')
        parti = get_text_from_element(el, 'parti')
        anforande_id = get_text_from_element(el, 'anforande_id')
        anforande_url_xml = get_text_from_element(el, 'anforande_url_xml')
        dok_id = get_text_from_element(el, 'dok_id')
        dok_datum = get_text_from_element(el, 'dok_datum')
        avsnittsrubrik = get_text_from_element(el, 'avsnittsrubrik', "Ej specificerat ämne")
        dok_titel = get_text_from_element(el, 'dok_titel')

        # Kärninformation som behövs för att kunna hämta och identifiera anförandet
        if not talare or not anforande_id or not anforande_url_xml:
            print(f"VARNING: Kärninformation saknas för post {i + 1}. Detaljer:")
            if not talare: print("  - talare saknas")
            if not anforande_id: print("  - anforande_id saknas")
            if not anforande_url_xml: print("  - anforande_url_xml saknas")
            print("  Hoppar över denna post.")
            continue

        # Bestäm vilket iid som ska användas för databasen
        db_iid = iid_from_xml
        if not db_iid:
            # Generera ett stabilt iid om det saknas (t.ex. för TALMANNEN)
            s_talare = ''.join(c for c in talare if c.isalnum() or c == ' ').replace(' ', '_').lower()
            s_parti = ''.join(c for c in parti if c.isalnum()).lower() if parti else "okantparti"
            db_iid = f"gen_{s_talare}_{s_parti}"
            db_iid = db_iid[:60]  # Begränsa längden för säkerhets skull
            print(f"  INFO: Original iid saknades för '{talare}' ({parti}). Använder genererat iid: '{db_iid}'")

        # 1. Lägg till/uppdatera ledamot i 'members'-tabellen
        try:
            cursor.execute("INSERT OR IGNORE INTO members (iid, name, party) VALUES (?, ?, ?)",
                           (db_iid, talare, parti))
            if cursor.rowcount > 0:
                members_added_to_db_count += 1
                print(f"  Lade till ny ledamot: {talare} ({parti}) med IID: {db_iid}")
        except sqlite3.Error as e:
            print(f"  Databasfel vid infogning/ignorering av ledamot {talare} (IID: {db_iid}): {e}")
            continue

            # 2. Kontrollera om anförandetexten redan finns i 'speeches'-tabellen (baserat på anforande_id)
        cursor.execute("SELECT 1 FROM speeches WHERE anforande_id = ?", (anforande_id,))
        if cursor.fetchone():
            print(f"  Anförande {anforande_id} av {talare} finns redan i databasen. Hoppar över hämtning av text.")
            speeches_processed_count += 1  # Räkna som bearbetad även om den redan fanns
            continue

            # 3. Hämta den fullständiga anförandetexten
        print(f"  Hämtar text för anförande {anforande_id} av {talare} från: {anforande_url_xml}")
        anforandetext = fetch_speech_text_from_url(anforande_url_xml)

        if "kunde inte hittas" in anforandetext.lower() or "fel vid" in anforandetext.lower():
            print(f"  VARNING: Kunde inte hämta/analysera text för anförande {anforande_id}: {anforandetext}")

        # 4. Spara anförandet i 'speeches'-tabellen
        try:
            cursor.execute('''
                INSERT INTO speeches (anforande_id, iid, dok_id, dok_datum, avsnittsrubrik, dok_titel, anforandetext, anforande_url_xml)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (anforande_id, db_iid, dok_id, dok_datum, avsnittsrubrik, dok_titel, anforandetext, anforande_url_xml))
            conn.commit()
            speeches_added_to_db_count += 1
            print(f"  Sparade anförande {anforande_id} till databasen.")
        except sqlite3.IntegrityError:
            print(f"  Anförande {anforande_id} (URL: {anforande_url_xml}) finns redan (IntegrityError).")
        except sqlite3.Error as e:
            print(f"  Databasfel vid infogning av anförande {anforande_id}: {e}")
            conn.rollback()

        speeches_processed_count += 1

    print(f"\nDatainhämtning klar.")
    print(f"  Poster från API-listan som försökts bearbetas: {speeches_processed_count}")
    print(f"  Nya ledamöter tillagda i databasen: {members_added_to_db_count}")
    print(f"  Nya anföranden tillagda i databasen: {speeches_added_to_db_count}")


def generate_interactive_html(conn, cursor, filename_template, date_from_str, date_to_str):
    """Genererar en interaktiv HTML-sida från databasens innehåll."""
    print("Genererar interaktiv HTML-sida...")

    cursor.execute("SELECT iid, name, party FROM members ORDER BY name ASC")
    members_list = [{"iid": row[0], "name": row[1], "party": row[2]} for row in cursor.fetchall()]

    cursor.execute("""
        SELECT iid, dok_datum, avsnittsrubrik, dok_titel, anforandetext, anforande_id
        FROM speeches 
        ORDER BY dok_datum DESC, avsnittsrubrik ASC
    """)
    speeches_by_member = defaultdict(list)
    for row in cursor.fetchall():
        speeches_by_member[row[0]].append({
            "dok_datum": row[1],
            "avsnittsrubrik": row[2],
            "dok_titel": row[3],
            "anforandetext": row[4],
            "anforande_id": row[5]
        })

    html_filename = filename_template.format(date_from=date_from_str, date_to=date_to_str)

    html_content = f"""
<!DOCTYPE html>
<html lang="sv">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Riksdagsanföranden per Ledamot (Interaktiv)</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; display: flex; height: 100vh; background-color: #f0f2f5; }}
        #sidebar {{ width: 300px; background-color: #ffffff; padding: 20px; overflow-y: auto; border-right: 1px solid #d1d5db; box-shadow: 2px 0 5px rgba(0,0,0,0.05); }}
        #sidebar h2 {{ margin-top: 0; color: #111827; font-size: 1.5em; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }}
        #member-list {{ list-style-type: none; padding: 0; }}
        #member-list li {{ padding: 10px 12px; cursor: pointer; border-radius: 6px; margin-bottom: 5px; transition: background-color 0.2s ease-in-out, color 0.2s ease-in-out; }}
        #member-list li:hover {{ background-color: #eff6ff; color: #1d4ed8; }}
        #member-list li.active {{ background-color: #3b82f6; color: white; font-weight: bold; }}
        #member-list .member-party {{ font-size: 0.85em; color: #6b7280; display: block; }}
        #member-list li.active .member-party {{ color: #bfdbfe; }}
        #content {{ flex-grow: 1; padding: 25px; overflow-y: auto; background-color: #f8f9fa; }}
        #content h1 {{ color: #1f2937; margin-top:0; }}
        .speech-group {{ margin-bottom: 25px; padding: 15px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .speech-group h3 {{ font-size: 1.3em; color: #17a2b8; margin-top:0; margin-bottom: 5px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }}
        .speech-group .date {{ font-style: italic; color: #6c757d; font-size: 0.9em; margin-bottom: 10px; display: block; }}
        .speech-details {{ margin-bottom: 15px; border-left: 3px solid #3b82f6; padding-left: 15px; }}
        .speech-details .debate-title {{ font-weight: bold; color: #4b5563; font-size: 1em; display: block; margin-bottom: 5px;}}
        .speech-text {{ 
            background-color: #f9fafb; 
            padding: 12px; 
            border-radius: 6px; 
            border: 1px solid #e5e7eb;
            overflow-wrap: break-word;
            word-wrap: break-word;
            font-size: 0.95em;
            line-height: 1.6;
        }}
        .speech-text p {{ margin-top: 0; margin-bottom: 0.5em; }}
        #placeholder {{ text-align: center; color: #6b7280; margin-top: 50px; font-size: 1.2em; }}
        footer {{ text-align: center; padding: 15px; font-size: 0.85em; color: #6c757d; background-color: #e9ecef; border-top: 1px solid #dee2e6; position: sticky; bottom: 0; width: calc(100% - 300px); left: 300px; }}
         /* Responsive adjustments */
        @media (max-width: 768px) {{
            body {{ flex-direction: column; }}
            #sidebar {{ width: 100%; height: auto; max-height: 40vh; border-right: none; border-bottom: 1px solid #d1d5db; }}
            #content {{ width: 100%; }}
            footer {{ width: 100%; left: 0; }}
        }}
    </style>
</head>
<body>
    <div id="sidebar">
        <h2>Riksdagsledamöter</h2>
        <ul id="member-list">
            {"".join([f'<li data-iid="{m["iid"]}">{m["name"]}<span class="member-party">{m["party"]}</span></li>' for m in members_list])}
        </ul>
    </div>
    <div id="content">
        <h1 id="selected-member-name">Välj en ledamot från listan</h1>
        <div id="speeches-container">
            <p id="placeholder">Anföranden för den valda ledamoten kommer att visas här.</p>
        </div>
    </div>

    <script>
        const membersData = {json.dumps(members_list)};
        const speechesByMember = {json.dumps(speeches_by_member)};

        const memberListElement = document.getElementById('member-list');
        const speechesContainerElement = document.getElementById('speeches-container');
        const selectedMemberNameElement = document.getElementById('selected-member-name');
        const placeholderElement = document.getElementById('placeholder');

        memberListElement.addEventListener('click', function(event) {{
            let targetLi = event.target;
            while (targetLi && targetLi.tagName !== 'LI') {{
                targetLi = targetLi.parentElement;
            }}
            if (!targetLi) return;

            const memberIid = targetLi.dataset.iid;
            const member = membersData.find(m => m.iid === memberIid);

            const currentlyActive = memberListElement.querySelector('li.active');
            if (currentlyActive) {{
                currentlyActive.classList.remove('active');
            }}
            targetLi.classList.add('active');

            if (member) {{
                selectedMemberNameElement.textContent = `Anföranden av: ${{member.name}} (${{member.party || 'Parti okänt'}})`;
                const memberSpeeches = speechesByMember[memberIid] || [];
                renderSpeeches(memberSpeeches);
            }}
        }});

        function renderSpeeches(speeches) {{
            speechesContainerElement.innerHTML = ''; 
            if (speeches.length === 0) {{
                placeholderElement.style.display = 'block';
                placeholderElement.textContent = 'Inga anföranden hittades för denna ledamot under den aktuella perioden.';
                return;
            }}
            placeholderElement.style.display = 'none';

            const groupedSpeeches = speeches.reduce((acc, speech) => {{
                const key = `${{speech.dok_datum}} - ${{speech.avsnittsrubrik}}`;
                if (!acc[key]) {{
                    acc[key] = {{
                        date: speech.dok_datum,
                        topic: speech.avsnittsrubrik,
                        speeches: []
                    }};
                }}
                acc[key].speeches.push(speech);
                return acc;
            }}, {{}});

            const sortedGroups = Object.values(groupedSpeeches).sort((a, b) => {{
                if (a.date > b.date) return -1;
                if (a.date < b.date) return 1;
                return a.topic.localeCompare(b.topic);
            }});

            sortedGroups.forEach(group => {{
                const groupDiv = document.createElement('div');
                groupDiv.className = 'speech-group';

                const topicHeader = document.createElement('h3');
                topicHeader.textContent = group.topic || 'Okänt ämne';
                groupDiv.appendChild(topicHeader);

                const dateSpan = document.createElement('span');
                dateSpan.className = 'date';
                dateSpan.textContent = `Datum: ${{group.date || 'Okänt datum'}}`;
                groupDiv.appendChild(dateSpan);

                group.speeches.forEach(speech => {{
                    const speechDiv = document.createElement('div');
                    speechDiv.className = 'speech-details';

                    const debateTitleP = document.createElement('p');
                    debateTitleP.className = 'debate-title';
                    debateTitleP.textContent = `Debatt/Dokument: ${{speech.dok_titel || 'Titel saknas'}}`;
                    speechDiv.appendChild(debateTitleP);

                    const speechTextDiv = document.createElement('div');
                    speechTextDiv.className = 'speech-text';
                    speechTextDiv.innerHTML = speech.anforandetext || 'Text saknas.';
                    speechDiv.appendChild(speechTextDiv);

                    groupDiv.appendChild(speechDiv);
                }});
                speechesContainerElement.appendChild(groupDiv);
            }});
        }}
    </script>
</body>
</html>
"""
    try:
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"HTML-filen '{html_filename}' har skapats.")
        print(f"Du hittar den på: {os.path.abspath(html_filename)}")
    except IOError as e:
        print(f"Kunde inte skriva till filen {html_filename}: {e}")


def main():
    """Huvudfunktion för att sätta upp databas, hämta data och generera HTML."""
    print("Startar Riksdagens anförandehanterare...")

    date_to = datetime.date.today()
    date_from = date_to - datetime.timedelta(days=365)
    date_from_str = date_from.strftime("%Y-%m-%d")
    date_to_str = date_to.strftime("%Y-%m-%d")

    conn, cursor = setup_database(DATABASE_NAME)
    if not conn or not cursor:
        print("Kunde inte initiera databasen. Avslutar.")
        return

    populate_database(conn, cursor, date_from_str, date_to_str)

    generate_interactive_html(conn, cursor, HTML_OUTPUT_FILENAME_TEMPLATE, date_from_str, date_to_str)

    if conn:
        conn.close()
        print("Databasanslutningen stängd.")

    print("Processen är klar.")


if __name__ == "__main__":
    main()
