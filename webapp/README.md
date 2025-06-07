# Webapp de tirage quotidien

Cette application Flask est un exemple simplifié du système de tirage de cartes
présent sur le bot Discord. Elle peut maintenant se connecter au même Google
Sheet que le bot et annoncer les tirages dans un salon Discord.

## Installation rapide

1. Installez les dépendances :
   ```bash
   pip install flask requests gspread google-auth
   ```
2. Créez une application Discord pour obtenir `DISCORD_CLIENT_ID` et
   `DISCORD_CLIENT_SECRET`. Définissez aussi `DISCORD_REDIRECT_URI` dans les
   variables d'environnement ainsi qu'une `FLASK_SECRET` quelconque. Le bot
   doit disposer d'un token (`DISCORD_TOKEN`) capable d'envoyer des messages
   dans le salon d'annonce (`DISCORD_CHANNEL_ID`, par défaut `1361993326215172218`).
3. Définissez les variables pour l'accès à Google Sheets :
   `SERVICE_ACCOUNT_JSON` (contenu JSON de votre compte de service) et
   `GOOGLE_SHEET_ID_CARTES`.
4. Lancez le serveur :
   ```bash
   python app.py
   ```
5. Ouvrez `http://localhost:5000` et connectez‑vous avec Discord pour effectuer
   votre tirage quotidien.

Les tirages sont inscrits dans le même Google Sheet que le bot Discord et un
message récapitulatif est envoyé dans le salon configuré.

Pour l'hébergement, n'importe quelle plateforme supportant Python (Render,
Railway, un serveur personnel…) peut convenir. Il suffit de définir les
variables d'environnement ci-dessus.
