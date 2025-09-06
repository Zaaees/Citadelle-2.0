# 🎭 Système de Surveillance Automatique des Scènes RP

Ce système permet aux maîtres de jeu (MJ) de suivre automatiquement l'activité dans les scènes de jeu de rôle Discord et de recevoir des notifications en temps réel.

## 🚀 Fonctionnalités Principales

### 1. **Initiation de Surveillance**
- Commande `/surveiller_scene` pour activer la surveillance sur n'importe quel salon, thread ou forum
- Détection automatique du salon actuel si non spécifié
- Vérification des permissions MJ

### 2. **Messages Informatifs Visuels**
- **Embeds élégants** avec code couleur basé sur l'activité :
  - 🟢 Vert : Actif (< 6h)
  - 🟡 Jaune : Modéré (< 1j)
  - 🟠 Orange : Peu actif (< 3j)
  - 🔴 Rouge : Inactif (≥ 3j)
- **Informations affichées** :
  - Nom et lien du salon surveillé
  - MJ responsable de la scène
  - Liste des participants actifs (jusqu'à 10 + compteur)
  - Date/heure de la dernière activité (format relatif Discord)
  - Dernier utilisateur ayant participé

### 3. **Boutons Interactifs**
- **🟢 Reprendre la scène** : Permet à un autre MJ de devenir responsable
- **🔴 Clôturer la scène** : Arrête la surveillance et désactive les boutons
- Boutons persistants avec `custom_id` pour survivre aux redémarrages

### 4. **Détection Intelligente des Participants**
- **Filtrage automatique** : Ignore les bots système
- **Reconnaissance des webhooks RP** :
  - Support Tupperbox (détection via footer "Sent by Username")
  - Support PluralKit et autres bots RP similaires
  - Cache des associations webhook → utilisateur réel
  - Patterns extensibles pour nouveaux bots

### 5. **Notifications Privées**
- **Notifications en temps réel** au MJ responsable lors de nouvelle activité
- **Protection anti-spam** : Une notification maximum par 30 minutes
- **Messages riches** avec embed incluant :
  - Lien direct vers le message
  - Extrait du contenu (200 caractères)
  - Informations sur l'auteur (réel, pas le webhook)

### 6. **Alertes d'Inactivité**
- **Surveillance automatique** : Vérification quotidienne
- **Alerte à 7 jours** d'inactivité avec :
  - Message privé au MJ responsable
  - Suggestions d'actions (relancer, clôturer, transférer)
  - Liens directs vers la gestion de la scène

### 7. **Mise à Jour Automatique**
- **Surveillance permanente** via `on_message` listener
- **Mise à jour temps réel** des embeds de statut
- **Rattrapage automatique** lors du redémarrage (chargement depuis Google Sheets)
- **Tâches périodiques** :
  - Mise à jour des statuts : toutes les 30 minutes
  - Vérification inactivité : quotidienne

### 8. **Stockage Persistant**
- **Google Sheets** comme base de données
- **Structure de données** :
  ```
  channel_id | mj_id | status_message_id | status_channel_id | 
  created_at | last_activity | participants | last_author_id | status
  ```
- **Sauvegarde automatique** de tous les événements
- **Récupération** des données après redémarrage

### 9. **Gestion des Permissions**
- **Rôle MJ requis** (ID configurable : `1018179623886000278`)
- **Vérifications** sur toutes les commandes et boutons
- **Messages d'erreur** explicites pour les utilisateurs non autorisés

## 📋 Commandes Disponibles

### `/surveiller_scene [channel]`
Démarre la surveillance d'une scène RP.
- **Paramètre** : `channel` (optionnel) - Le salon à surveiller
- **Par défaut** : Utilise le salon actuel
- **Permissions** : Rôle MJ requis
- **Résultat** : Crée un message de suivi avec boutons interactifs

### `/scenes_actives`
Affiche la liste des scènes actuellement surveillées.
- **Permissions** : Rôle MJ requis
- **Affichage** : Embed avec résumé de toutes les scènes actives

## 🔧 Configuration Requise

### Variables d'Environnement
```bash
# Google Sheets (requis)
SERVICE_ACCOUNT_JSON='{"type": "service_account", ...}'
GOOGLE_SHEET_ID_SURVEILLANCE="id_de_la_feuille"  # ou utilise GOOGLE_SHEET_ID_ACTIVITE

# Discord (déjà configuré)
DISCORD_TOKEN="votre_token"
```

### Rôle MJ
Modifiez la variable `self.mj_role_id` dans la classe pour votre serveur :
```python
self.mj_role_id = 1018179623886000278  # Remplacez par votre ID de rôle MJ
```

## 📊 Installation

### 1. Configuration Google Sheets
```bash
# Exécuter le script de configuration
python setup_scene_surveillance_sheet.py
```

### 2. Chargement du Cog
Le cog est automatiquement chargé dans `main.py`. Pour le recharger manuellement :
```python
await bot.reload_extension('cogs.scene_surveillance')
```

## 🎯 Utilisation Pratique

### Workflow Typique
1. **MJ utilise** `/surveiller_scene` dans le salon de la scène
2. **Message de suivi** créé avec embed informatif et boutons
3. **Participants écrivent** → Détection automatique et mise à jour
4. **MJ reçoit** des notifications privées lors de nouvelle activité
5. **Système surveille** l'inactivité et alerte après 7 jours
6. **MJ peut** transférer ou clôturer via les boutons

### Gestion des Webhooks RP
Le système reconnaît automatiquement :
- **Tupperbox** : Via footer "Sent by Username"
- **PluralKit** : Via patterns dans les embeds
- **Autres bots** : Extensible via `detect_webhook_user()`

### Indicateurs Visuels
- **Couleur de l'embed** = Niveau d'activité récente
- **Timestamps Discord** = Format "<t:timestamp:R>" pour affichage relatif
- **Mentions** = Liens cliquables vers utilisateurs et salons

## 🔍 Monitoring et Debug

### Logs Importants
```python
logger.info(f"Surveillance démarrée: {channel_id}")
logger.error(f"Erreur sauvegarde Google Sheets: {e}")
logger.warning(f"Webhook non reconnu: {webhook_name}")
```

### Vérification des Données
- **Google Sheets** : Consultez directement la feuille
- **Mémoire** : `self.active_scenes` contient les scènes en cours
- **Cache webhooks** : `self.webhook_users` pour les associations

## 🛠️ Maintenance

### Ajout de Nouveaux Bots RP
Modifiez la méthode `detect_webhook_user()` pour ajouter des patterns :
```python
# Exemple pour un nouveau bot
if 'MonNouveauBot' in embed.footer.text:
    pattern_match = re.search(r'Par: (.+)', embed.footer.text)
    if pattern_match:
        username = pattern_match.group(1)
        # Logique de résolution...
```

### Ajustement des Délais
```python
# Dans les décorateurs @tasks.loop()
@tasks.loop(minutes=15)  # Surveillance plus fréquente
async def activity_monitor(self):

@tasks.loop(hours=12)    # Vérification inactivité plus fréquente
async def inactivity_checker(self):
```

## 🚨 Gestion d'Erreurs

Le système est conçu pour être robuste :
- **Erreurs Google Sheets** : Continuent à fonctionner en mémoire
- **Erreurs Discord** : Messages d'erreur utilisateur explicites
- **Tâches en échec** : Auto-redémarrage avec logging
- **Permissions** : Vérifications à tous les niveaux

## 🔮 Extensions Possibles

- **Statistiques avancées** : Graphiques d'activité
- **Templates de scènes** : Création assistée
- **Intégration calendrier** : Planification automatique
- **Multi-serveurs** : Support de plusieurs serveurs Discord
- **API REST** : Interface externe pour la gestion