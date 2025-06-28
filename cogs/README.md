# Cogs — Modules du bot *Citadelle 2.0*

Ce dossier contient les différents modules (`cogs`) utilisés par le bot Discord. Chaque fichier représente un aspect fonctionnel du bot.

---

## 🃏 Cards.py
Gère le système de cartes à collectionner :
- Tirages aléatoires pondérés par rareté.
- Gestion des variantes.
- Galerie utilisateur.
- Intégration avec Google Sheets.
- Affichage des cartes et progression dans un mur.
- Commandes : `/cartes`, `!tirage_journalier`, etc.

---

## 🎒 inventaire.py
Gère l’inventaire des utilisateurs (objets, éléments associés).
- Chargement/sauvegarde des données d’inventaire.
- Utilisé comme base pour les autres systèmes (RP ou cartes).

---

## 📊 RPTracker.py
Système de suivi d'activité RP :
- Enregistre l’activité des utilisateurs dans les salons RP.
- Permet de déterminer les personnages les plus actifs.
- Sert pour accorder des bonus liés à l’activité.

---

## 🧼 InactiveUserTracker.py
Détecte les utilisateurs inactifs :
- Scanne l’activité sur le serveur pour repérer les absences prolongées.
- Sert à des actions de nettoyage ou de relance.

---

## 💬 vocabulaire.py
Gestion d’un dictionnaire de vocabulaire spécifique :
- Peut être utilisé pour détecter des mots interdits ou analysés dans les messages.
- Probablement en lien avec des fonctionnalités RP ou de modération.

---

## 📌 validation.py
Module de validation :
- Sert à confirmer ou refuser des actions utilisateurs.
- Potentiellement utilisé pour la création d’éléments ou la participation à des événements.

---

## 🧵 souselement.py
Gestion des sous-éléments (threads ?) dans Discord :
- Permet d’ajouter ou retirer des sous-composants à une structure principale.
- Possiblement utilisé pour le RP (ex : gestion de posts secondaires, de PNJ, etc.).

---

## 🎟️ ticket.py
Système de ticket :
- Crée des canaux privés temporaires (tickets d’assistance, d’administration ou d’événement).
- Peut inclure des boutons et des validations.

---

## 🌌 Espace.py
Cog probablement lié à un thème "espace" ou à une dimension narrative spécifique.
- À confirmer selon son contenu exact.

---



## 🧼 bump.py
Fonction pour le bump automatique ou assisté :
- Relance de serveurs (type Disboard ?).
- Peut aider à maintenir de la visibilité sur des listes de serveurs publics.

---

## 🐍 __pycache__/
Cache automatique généré par Python. Ignorer ce dossier.