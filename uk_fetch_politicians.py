import requests
import sqlite3
import json
import time

def create_database():
    """Create SQLite database with tables for members of both Houses"""
    conn = sqlite3.connect('uk_parliament_members.db')
    cursor = conn.cursor()
    
    # Drop existing tables if they exist
    cursor.execute("DROP TABLE IF EXISTS contact_details")
    cursor.execute("DROP TABLE IF EXISTS constituencies")
    cursor.execute("DROP TABLE IF EXISTS members")
    
    # Create table for members
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY,
        name TEXT,
        gender TEXT,
        party TEXT,
        house TEXT,
        current_status TEXT,
        start_date TEXT,
        end_date TEXT
    )
    ''')
    
    # Create table for contact details
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS contact_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        type TEXT,
        value TEXT,
        FOREIGN KEY (member_id) REFERENCES members(id)
    )
    ''')
    
    # Create table for constituencies/seats
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS constituencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        name TEXT,
        start_date TEXT,
        end_date TEXT,
        FOREIGN KEY (member_id) REFERENCES members(id)
    )
    ''')
    
    conn.commit()
    return conn

def fetch_members(house_type):
    """Fetch members from the UK Parliament API"""
    base_url = "https://members-api.parliament.uk/api/Members/Search"
    
    # Parameters for the API request
    params = {
        "House": house_type,  # 1 for Commons, 2 for Lords
        "IsCurrentMember": True,
        "skip": 0,
        "take": 1000  # Large enough to get all members
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching members: {e}")
        return None

def fetch_member_details(member_id):
    """Fetch detailed information about a specific member"""
    url = f"https://members-api.parliament.uk/api/Members/{member_id}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching member details for ID {member_id}: {e}")
        return None

def insert_member_data(conn, member_data, house_type):
    """Insert member data into the database"""
    cursor = conn.cursor()
    
    try:
        # Extract basic member information
        member_id = member_data["value"]["id"]
        name = member_data["value"].get("nameDisplayAs", "Unknown")
        gender = member_data["value"].get("gender", "Unknown")
        
        # Get party information
        party = "Unknown"
        if "latestParty" in member_data["value"] and member_data["value"]["latestParty"]:
            party = member_data["value"]["latestParty"].get("name", "Unknown")
        
        # Determine current status based on membership status
        current_status = "Current"  # Default to current since we're filtering for current members
        
        # Get house type (Commons or Lords)
        house = "Commons" if house_type == 1 else "Lords"
        
        # Get membership dates if available
        start_date = None
        end_date = None
        if "latestHouseMembership" in member_data["value"] and member_data["value"]["latestHouseMembership"]:
            membership = member_data["value"]["latestHouseMembership"]
            start_date = membership.get("membershipStartDate")
            end_date = membership.get("membershipEndDate")
        
        # Insert into members table
        cursor.execute('''
        INSERT OR REPLACE INTO members (id, name, gender, party, house, current_status, start_date, end_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (member_id, name, gender, party, house, current_status, start_date, end_date))
        
        # Fetch detailed information for contact details and constituencies
        details = fetch_member_details(member_id)
        if details and "value" in details:
            # Insert contact details if available
            if "contactDetails" in details["value"] and details["value"]["contactDetails"]:
                for contact_type, contacts in details["value"]["contactDetails"].items():
                    for contact in contacts:
                        contact_value = contact.get("line1", "")
                        if contact_value:
                            cursor.execute('''
                            INSERT INTO contact_details (member_id, type, value)
                            VALUES (?, ?, ?)
                            ''', (member_id, contact_type, contact_value))
            
            # Insert constituency information for Commons members
            if house_type == 1 and "latestHouseMembership" in details["value"] and details["value"]["latestHouseMembership"]:
                if "membershipFrom" in details["value"]["latestHouseMembership"]:
                    constituency = details["value"]["latestHouseMembership"]["membershipFrom"]
                    cursor.execute('''
                    INSERT INTO constituencies (member_id, name, start_date, end_date)
                    VALUES (?, ?, ?, ?)
                    ''', (member_id, constituency, start_date, end_date))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error processing member {member_data['value'].get('nameDisplayAs', 'Unknown')}: {e}")
        return False

def main():
    # Create database
    conn = create_database()
    print("Database created successfully.")
    
    # Fetch and insert Commons members
    print("Fetching House of Commons members...")
    commons_members = fetch_members(1)
    commons_success = 0
    
    if commons_members and "items" in commons_members:
        total_commons = len(commons_members["items"])
        print(f"Found {total_commons} House of Commons members.")
        
        for i, member in enumerate(commons_members["items"]):
            name = member["value"].get("nameDisplayAs", f"Member {i+1}")
            print(f"Processing Commons member {i+1}/{total_commons}: {name}")
            if insert_member_data(conn, member, 1):
                commons_success += 1
            # Add a small delay to avoid overwhelming the API
            time.sleep(0.1)
    
    # Fetch and insert Lords members
    print("Fetching House of Lords members...")
    lords_members = fetch_members(2)
    lords_success = 0
    
    if lords_members and "items" in lords_members:
        total_lords = len(lords_members["items"])
        print(f"Found {total_lords} House of Lords members.")
        
        for i, member in enumerate(lords_members["items"]):
            name = member["value"].get("nameDisplayAs", f"Member {i+1}")
            print(f"Processing Lords member {i+1}/{total_lords}: {name}")
            if insert_member_data(conn, member, 2):
                lords_success += 1
            # Add a small delay to avoid overwhelming the API
            time.sleep(0.1)
    
    # Print summary
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM members WHERE house='Commons'")
    commons_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM members WHERE house='Lords'")
    lords_count = cursor.fetchone()[0]
    
    print(f"\nDatabase Summary:")
    print(f"- House of Commons members: {commons_count}")
    print(f"- House of Lords members: {lords_count}")
    print(f"- Total members: {commons_count + lords_count}")
    print(f"- Successfully processed: {commons_success} Commons, {lords_success} Lords")
    
    # Print sample data
    print("\nSample data from members table:")
    cursor.execute("SELECT id, name, party, house FROM members LIMIT 5")
    for row in cursor.fetchall():
        print(f"ID: {row[0]}, Name: {row[1]}, Party: {row[2]}, House: {row[3]}")
    
    conn.close()
    print("\nDatabase created and populated successfully: uk_parliament_members.db")

if __name__ == "__main__":
    main()
