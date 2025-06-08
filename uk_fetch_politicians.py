# Script to fetch all current UK members of both Houses of Parliament from the official Parliament API.
# 06/06/2025 - returns 650 members of the Commons and 859 members of the Lords.
# NB you can use a tool like sqlitebrowser to check the data after download.

import requests
import sqlite3
import time
import sys

def create_database():
    """Create SQLite database with tables for members of both Houses"""
    conn = sqlite3.connect('uk_parliament_members.db')
    cursor = conn.cursor()
    
    # Create tables if they don't exist
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
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS contact_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        type TEXT,
        value TEXT,
        FOREIGN KEY (member_id) REFERENCES members(id)
    )
    ''')
    
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

def fetch_members_page(house_type, skip=0, take=50):
    """Fetch a single page of members from the UK Parliament API"""
    base_url = "https://members-api.parliament.uk/api/Members/Search"
    
    params = {
        "House": house_type,  # 1 for Commons, 2 for Lords
        "IsCurrentMember": True,
        "skip": skip,
        "take": take
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching members: {e}")
        return None

def process_house_members(conn, house_type, house_name, max_members=100):
    """Process members for a specific house with pagination"""
    cursor = conn.cursor()
    
    # Check if we already have members for this house
    cursor.execute("SELECT COUNT(*) FROM members WHERE house = ?", (house_name,))
    existing_count = cursor.fetchone()[0]
    
    if existing_count > 0:
        print(f"Already have {existing_count} {house_name} members in database.")
        return existing_count
    
    print(f"Fetching {house_name} members (limited to {max_members})...")
    
    skip = 0
    take = 50  # Fetch 50 at a time
    total_fetched = 0
    total_processed = 0
    
    while total_fetched < max_members:
        print(f"Fetching page: skip={skip}, take={take}")
        page_data = fetch_members_page(house_type, skip, take)
        
        if not page_data or "items" not in page_data or not page_data["items"]:
            print("No more members to fetch.")
            break
        
        members_page = page_data["items"]
        total_results = page_data.get("totalResults", 0)
        
        print(f"Fetched {len(members_page)} members (total available: {total_results})")
        total_fetched += len(members_page)
        
        # Process each member in this page
        for member in members_page:
            try:
                member_id = member["value"]["id"]
                name = member["value"].get("nameDisplayAs", "Unknown")
                gender = member["value"].get("gender", "Unknown")
                
                # Get party information
                party = "Unknown"
                if "latestParty" in member["value"] and member["value"]["latestParty"]:
                    party = member["value"]["latestParty"].get("name", "Unknown")
                
                # Get membership dates if available
                start_date = None
                end_date = None
                constituency = None
                
                if "latestHouseMembership" in member["value"] and member["value"]["latestHouseMembership"]:
                    membership = member["value"]["latestHouseMembership"]
                    start_date = membership.get("membershipStartDate")
                    end_date = membership.get("membershipEndDate")
                    
                    # Get constituency for Commons members
                    if house_type == 1 and "membershipFrom" in membership:
                        constituency = membership["membershipFrom"]
                
                # Insert into members table
                cursor.execute('''
                INSERT OR REPLACE INTO members (id, name, gender, party, house, current_status, start_date, end_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (member_id, name, gender, party, house_name, "Current", start_date, end_date))
                
                # Insert constituency if available
                if constituency:
                    cursor.execute('''
                    INSERT INTO constituencies (member_id, name, start_date, end_date)
                    VALUES (?, ?, ?, ?)
                    ''', (member_id, constituency, start_date, end_date))
                
                total_processed += 1
                print(f"Processed {house_name} member: {name}")
                
            except Exception as e:
                print(f"Error processing member: {e}")
        
        conn.commit()
        
        # Check if we've reached the end of available members
        if len(members_page) < take or total_fetched >= total_results:
            break
        
        skip += take
        time.sleep(0.5)  # Small delay between pages
    
    print(f"Completed processing {total_processed} {house_name} members")
    return total_processed

def main():
    # Create or connect to database
    conn = create_database()
    print("Database ready.")
    
    # Process Commons members (limited to 100 for this demo)
    commons_count = process_house_members(conn, 1, "Commons", 100)
    
    # Process Lords members (limited to 100 for this demo)
    lords_count = process_house_members(conn, 2, "Lords", 100)
    
    # Print summary
    print(f"\nDatabase Summary:")
    print(f"- House of Commons members: {commons_count}")
    print(f"- House of Lords members: {lords_count}")
    print(f"- Total members: {commons_count + lords_count}")
    
    # Print sample data
    cursor = conn.cursor()
    print("\nSample data from members table:")
    cursor.execute("SELECT id, name, party, house FROM members LIMIT 5")
    for row in cursor.fetchall():
        print(f"ID: {row[0]}, Name: {row[1]}, Party: {row[2]}, House: {row[3]}")
    
    conn.close()
    print("\nDatabase created and populated successfully: uk_parliament_members.db")

if __name__ == "__main__":
    main()
