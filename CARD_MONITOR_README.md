# 📊 Système de Surveillance des Cartes

Ce système surveille automatiquement les changements dans votre Google Sheet des cartes et envoie un rapport quotidien détaillé.

## 🚀 Fonctionnalités

### Surveillance Automatique
- **Surveillance quotidienne** à minuit (heure de Paris)
- **Détection automatique** des ajouts, suppressions et modifications de cartes
- **Résolution des noms d'utilisateurs** (IDs → noms d'affichage Discord)
- **Rapports détaillés** avec embeds Discord formatés

### Types de Changements Détectés
- ➕ **Cartes ajoutées** : Nouvelles cartes apparues dans le sheet
- ➖ **Cartes supprimées** : Cartes qui ont disparu du sheet
- 🔄 **Cartes modifiées** : Changements de quantités pour les utilisateurs existants

### Gestion des Erreurs
- **Notification automatique** si Google Sheets est inaccessible
- **Logs détaillés** pour le débogage
- **Récupération automatique** en cas d'erreur temporaire

## 📋 Configuration

### Canal de Notification
- **ID du canal** : `1230946716849799381`
- Les rapports sont envoyés automatiquement dans ce canal

### Heure de Surveillance
- **Heure** : Minuit (00:00) heure de Paris
- **Fréquence** : Quotidienne

## 🎮 Commandes Disponibles

### `!monitor_status`
Affiche le statut actuel de la surveillance.
- Statut de la tâche (active/inactive)
- Prochaine exécution programmée
- Informations sur le dernier snapshot
- Statut de la connexion Google Sheets

**Permissions requises** : Administrateur

### `!monitor_test`
Effectue un test manuel de la surveillance.
- Compare les données actuelles avec le dernier snapshot
- Envoie un rapport de test dans le canal de surveillance
- Utile pour vérifier que tout fonctionne correctement

**Permissions requises** : Administrateur

### `!monitor_snapshot`
Force la création d'un nouveau snapshot.
- Sauvegarde l'état actuel des données
- Remplace le snapshot précédent
- Utile pour réinitialiser la surveillance

**Permissions requises** : Administrateur

## 📊 Format des Rapports

### Rapport Principal
```
📊 Rapport quotidien - Surveillance des cartes
📈 Statistiques
  Total cartes: 150 (+2)
  Cartes ajoutées: 3
  Cartes supprimées: 1
  Cartes modifiées: 2
```

### Cartes Ajoutées
```
➕ Cartes ajoutées
Élèves
  Alice - JohnDoe (×2), JaneSmith
  Bob - MikeWilson

Professeurs
  Charlie - AdminUser
```

### Cartes Supprimées
```
➖ Cartes supprimées
Maître
  OldCard - FormerUser (×3)
```

### Cartes Modifiées
```
🔄 Cartes modifiées
Élèves
  Alice - JohnDoe: +1 (2→3), NewUser: +2
  Bob - OldUser: -1
```

## 🔧 Installation et Démarrage

### 1. Le cog est déjà ajouté à votre bot
Le fichier `cogs/card_monitor.py` a été créé et ajouté à la liste des extensions dans `main.py`.

### 2. Redémarrage du bot
Redémarrez votre bot pour charger le nouveau cog :
```bash
# Sur votre serveur de déploiement
# Le bot se redémarrera automatiquement et chargera le nouveau cog
```

### 3. Vérification
Une fois le bot redémarré, utilisez :
```
!monitor_status
```

### 4. Création du premier snapshot
Pour commencer la surveillance :
```
!monitor_snapshot
```

## 📁 Fichiers Créés

### `card_snapshots.json`
Fichier de sauvegarde des snapshots quotidiens.
- Créé automatiquement lors du premier snapshot
- Contient l'état complet des données à un moment donné
- Utilisé pour les comparaisons quotidiennes

## ⚠️ Notes Importantes

### Première Utilisation
- Le premier jour, aucun rapport ne sera envoyé (pas de snapshot précédent)
- Un message d'initialisation sera envoyé à la place
- La surveillance commencera le jour suivant

### Gestion des Utilisateurs
- Les IDs utilisateurs sont automatiquement convertis en noms d'affichage
- Si un utilisateur n'est pas trouvé : `Utilisateur#1234` (derniers 4 chiffres de l'ID)
- Utilise le cache Discord en priorité, puis l'API si nécessaire

### Performance
- Les rapports longs sont automatiquement divisés en plusieurs messages
- Limite de 1000 caractères par champ d'embed
- Groupement par catégorie pour une meilleure lisibilité

## 🐛 Dépannage

### La surveillance ne fonctionne pas
1. Vérifiez avec `!monitor_status`
2. Vérifiez les logs du bot
3. Testez avec `!monitor_test`

### Erreurs Google Sheets
- Vérifiez la variable d'environnement `GOOGLE_SHEET_ID_CARTES`
- Vérifiez la variable d'environnement `SERVICE_ACCOUNT_JSON`
- Les erreurs temporaires sont automatiquement signalées

### Canal de notification introuvable
- Vérifiez que l'ID du canal est correct : `1230946716849799381`
- Vérifiez que le bot a accès au canal
- Vérifiez les permissions du bot dans le canal

## 📈 Exemple de Workflow

1. **00:00 (minuit Paris)** : Surveillance automatique déclenchée
2. **Récupération** des données actuelles du Google Sheet
3. **Comparaison** avec le snapshot de la veille
4. **Génération** du rapport des changements
5. **Envoi** du rapport dans le canal de notification
6. **Sauvegarde** du nouveau snapshot pour demain

Le processus se répète automatiquement chaque jour !
