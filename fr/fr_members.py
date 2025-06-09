import requests
import json
import pandas as pd

print("Fetching data from NosDéputés.fr API with corrected name field...")

try:
    url = "https://www.nosdeputes.fr/deputes/json"
    response = requests.get(url, timeout=15)
    print(f"API status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("Success! Processing data with corrected name field...")
        
        members = []
        deputes = data.get('deputes', [])
        
        for deputy in deputes:
            deputy_info = deputy.get('depute', {})
            member_info = {
                'name': deputy_info.get('nom', ''),  # Only use 'nom' field
                'party': deputy_info.get('parti_ratt_financier', ''),
                'group': deputy_info.get('groupe_sigle', ''),
                'constituency': deputy_info.get('nom_circo', ''),
                'place_en_hemicycle': deputy_info.get('place_en_hemicycle', ''),
                'nb_mandats': deputy_info.get('nb_mandats', 0),
                'age': deputy_info.get('age', ''),
                'sexe': deputy_info.get('sexe', ''),
                'date_naissance': deputy_info.get('date_naissance', ''),
                'lieu_naissance': deputy_info.get('lieu_naissance', ''),
                'profession': deputy_info.get('profession', ''),
                'twitter': deputy_info.get('twitter', ''),
                'site_web': deputy_info.get('site_web', ''),
                'emails': deputy_info.get('emails', []),
                'adresses': deputy_info.get('adresses', [])
            }
            members.append(member_info)
        
        # Create DataFrame
        df = pd.DataFrame(members)
        
        print(f"\nTotal deputies found: {len(members)}")
        print(f"\nFirst 5 deputies with corrected names:")
        display_cols = ['name', 'party', 'group', 'constituency']
        print(df[display_cols].head().to_string(index=False))
        
        print(f"\nParty affiliations:")
        party_counts = df['party'].value_counts().head(10)
        print(party_counts.to_string())
        
        print(f"\nParliamentary groups:")
        group_counts = df['group'].value_counts().head(10)
        print(group_counts.to_string())
        
        # Save to CSV with corrected names
        df.to_csv('assemblee_members_corrected.csv', index=False, encoding='utf-8')
        print(f"\nData saved to 'assemblee_members_corrected.csv' with corrected names")
        
    else:
        print(f"API request failed with status {response.status_code}")
        
except Exception as e:
    print(f"Error: {e}")