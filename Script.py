import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv

def migrate_json_to_sheets():
    load_dotenv()
    
    # Connexion à Google Sheets
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(os.getenv('SERVICE_ACCOUNT_JSON')), 
        scope
    )
    
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(os.getenv('GOOGLE_SHEET_ID_VOCABULAIRE')).sheet1

    # Charger le JSON
    with open('vocabulaire.json', 'r', encoding='utf-8') as f:
        vocabulary = json.load(f)

    # Effacer la feuille existante
    sheet.clear()

    # Préparer les données pour un envoi groupé
    data = [['Mot', 'Definition', 'Extrait']]  # En-têtes
    for mot, info in vocabulary.items():
        data.append([mot, info['definition'], info['extrait']])

    # Écrire toutes les données en une seule fois
    sheet.update('A1', data)

if __name__ == '__main__':
    migrate_json_to_sheets()