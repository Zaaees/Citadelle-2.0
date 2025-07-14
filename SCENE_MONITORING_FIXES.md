# Corrections du système de surveillance des scènes inactives

## Problèmes identifiés

1. **Messages de rappel non supprimés** : Les messages datant du 11/07/2025 19:11 n'ont pas été supprimés automatiquement
2. **Pas de renouvellement quotidien** : Les messages ne se renouvellent pas chaque jour comme prévu
3. **Logique de vérification défaillante** : La fonction `has_alert_been_sent_today()` ne gérait pas correctement le renouvellement
4. **Synchronisation insuffisante** : Pas de coordination entre la suppression des anciens messages et l'envoi des nouveaux

## Solutions implémentées

### 1. Nouvelle logique de renouvellement quotidien

- **Ajout de `should_send_new_alert()`** : Vérifie si plus de 24h se sont écoulées depuis la dernière alerte
- **Modification de la fréquence de vérification** : Passage de 24h à 6h pour plus de fiabilité
- **Amélioration de la logique temporelle** : Utilisation de `total_seconds()` pour une précision au niveau des secondes

### 2. Gestion améliorée des messages de rappel

- **Ajout de `cleanup_old_reminder_message()`** : Supprime automatiquement l'ancien message avant d'envoyer le nouveau
- **Suivi des messages de rappel** : Nouveau champ `last_reminder_message_id` dans les données de surveillance
- **Suppression synchronisée** : L'ancien message est supprimé avant l'envoi du nouveau

### 3. Améliorations de la base de données

- **Nouveau champ dans Google Sheets** : `last_reminder_message_id` pour traquer les messages de rappel
- **Mise à jour des en-têtes** : Ajout du nouveau champ dans les feuilles existantes et nouvelles
- **Chargement compatible** : Support des anciennes données sans le nouveau champ

### 4. Robustesse et gestion d'erreurs

- **Gestion des messages supprimés** : Traitement des cas où les messages n'existent plus
- **Nettoyage automatique** : Suppression des entrées orphelines dans Google Sheets
- **Logs améliorés** : Meilleur suivi des opérations de suppression et de création

## Fonctionnement du nouveau système

### Cycle de vie d'un message de rappel

1. **Détection d'inactivité** : Scène inactive depuis plus de 7 jours
2. **Vérification du renouvellement** : Plus de 24h depuis la dernière alerte ?
3. **Suppression de l'ancien message** : Si un message de rappel existe déjà
4. **Envoi du nouveau message** : Création d'un nouveau message de rappel
5. **Enregistrement** : Sauvegarde de l'ID du nouveau message et du timestamp

### Fréquence d'exécution

- **Vérification des scènes inactives** : Toutes les 6h (au lieu de 24h)
- **Nettoyage des messages expirés** : Toutes les heures
- **Renouvellement des alertes** : Exactement 24h après la dernière alerte

## Tests implémentés

Le fichier `test_scene_monitoring.py` vérifie :

- ✅ Première alerte correctement envoyée
- ✅ Alerte récente correctement bloquée  
- ✅ Renouvellement après 24h détecté
- ✅ Cas limites (salon inexistant, exactement 24h, 23h59)

## Script de nettoyage

Le fichier `cleanup_old_reminders.py` permet de :

- 🧹 Supprimer manuellement les anciens messages de rappel
- 🗑️ Nettoyer les entrées orphelines dans Google Sheets
- 📊 Fournir un rapport de nettoyage

## Utilisation

### Déploiement automatique
Les corrections sont intégrées dans le cog `channel_monitor.py` et s'activent automatiquement au redémarrage du bot.

### Nettoyage manuel (optionnel)
```bash
python cleanup_old_reminders.py
```

### Test du système
```bash
python test_scene_monitoring.py
```

## Résultat attendu

Après ces modifications, le système devrait :

1. **Supprimer automatiquement** les anciens messages de rappel après 24h
2. **Envoyer un nouveau message** chaque jour pour les scènes toujours inactives
3. **Fonctionner même si le bot est déconnecté** entre temps (vérification toutes les 6h)
4. **Maintenir la cohérence** entre Discord et Google Sheets

## Compatibilité

- ✅ Compatible avec les données existantes
- ✅ Pas de perte de fonctionnalité
- ✅ Migration automatique des structures de données
- ✅ Gestion des cas d'erreur améliorée
