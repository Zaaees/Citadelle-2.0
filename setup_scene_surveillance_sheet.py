"""
Script d'installation pour créer la feuille Google Sheets pour la surveillance des scènes.
À exécuter une seule fois pour configurer la base de données.
"""

import os
import gspread
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

def setup_scene_surveillance_sheet():
    """Crée et configure la feuille Google Sheets pour la surveillance des scènes."""
    
    try:
        # Configuration Google Sheets
        credentials = service_account.Credentials.from_service_account_info(
            eval(os.getenv('SERVICE_ACCOUNT_JSON')),
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        gc = gspread.authorize(credentials)
        
        # Utiliser la feuille existante ou en créer une nouvelle
        sheet_id = os.getenv('GOOGLE_SHEET_ID_SURVEILLANCE') or os.getenv('GOOGLE_SHEET_ID_ACTIVITE')
        
        if not sheet_id:
            print("❌ Aucun ID de feuille Google Sheets configuré.")
            print("Configurez GOOGLE_SHEET_ID_SURVEILLANCE dans votre fichier .env")
            return
            
        spreadsheet = gc.open_by_key(sheet_id)
        
        # Créer la feuille SceneSurveillance si elle n'existe pas
        try:
            worksheet = spreadsheet.worksheet('SceneSurveillance')
            print("✅ Feuille 'SceneSurveillance' trouvée")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet('SceneSurveillance', rows=1000, cols=10)
            print("✅ Feuille 'SceneSurveillance' créée")
        
        # Configurer les en-têtes
        headers = [
            'channel_id',        # ID du canal surveillé
            'mj_id',            # ID du MJ responsable
            'status_message_id', # ID du message de statut
            'status_channel_id', # ID du canal où est le message de statut
            'created_at',        # Date de création de la surveillance
            'last_activity',     # Dernière activité détectée
            'participants',      # Liste des participants (JSON)
            'last_author_id',    # ID du dernier auteur
            'status'            # Statut: active, closed, paused
        ]
        
        # Vérifier si les en-têtes existent déjà
        try:
            first_row = worksheet.row_values(1)
            if first_row != headers:
                worksheet.insert_row(headers, 1)
                print("✅ En-têtes configurés")
            else:
                print("✅ En-têtes déjà configurés")
        except:
            worksheet.insert_row(headers, 1)
            print("✅ En-têtes ajoutés")
        
        # Formater la feuille
        worksheet.format('A1:I1', {
            'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.9},
            'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
            'horizontalAlignment': 'CENTER'
        })
        
        # Ajuster la largeur des colonnes
        worksheet.columns_auto_resize(0, len(headers))
        
        print("✅ Configuration terminée!")
        print(f"📋 Feuille disponible: https://docs.google.com/spreadsheets/d/{sheet_id}")
        print(f"📝 Feuille de travail: 'SceneSurveillance'")
        
    except Exception as e:
        print(f"❌ Erreur lors de la configuration: {e}")
        print("Vérifiez que:")
        print("- SERVICE_ACCOUNT_JSON est correctement configuré")
        print("- Le compte de service a accès à la feuille Google Sheets")
        print("- GOOGLE_SHEET_ID_SURVEILLANCE ou GOOGLE_SHEET_ID_ACTIVITE est configuré")

if __name__ == "__main__":
    print("🚀 Configuration de la feuille Google Sheets pour la surveillance des scènes...")
    setup_scene_surveillance_sheet()