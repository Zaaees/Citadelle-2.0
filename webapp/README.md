# Webapp de tirage quotidien

Cette application Flask est un exemple simplifié du système de tirage de cartes
présent sur le bot Discord. Elle fonctionne indépendamment du reste du projet.

## Installation rapide

1. Installez les dépendances :
   ```bash
   pip install flask requests
   ```
2. Créez une application Discord pour obtenir `DISCORD_CLIENT_ID` et
   `DISCORD_CLIENT_SECRET`. Définissez aussi `DISCORD_REDIRECT_URI` dans les
   variables d'environnement ainsi qu'une `FLASK_SECRET` quelconque.
3. Lancez le serveur :
   ```bash
   python app.py
   ```
4. Ouvrez `http://localhost:5000` et connectez‑vous avec Discord pour effectuer
   votre tirage quotidien.

Les données utilisateurs sont stockées localement dans `users.json`.
