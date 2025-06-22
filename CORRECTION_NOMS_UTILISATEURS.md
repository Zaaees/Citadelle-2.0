# Correction des noms d'utilisateurs dans le mur des cartes

## Problème
Les cartes dans le forum affichent "User_374571976645148693" au lieu du vrai nom du découvreur.

## Cause
La fonction de migration utilisait `bot.get_user()` qui ne fonctionne que pour les utilisateurs en cache. Si un utilisateur n'était pas en cache, le système utilisait un nom de fallback "User_ID".

## Solution implémentée

### 1. Amélioration de la migration
- Modifié `migrate_existing_discoveries()` pour utiliser `bot.fetch_user()` en plus de `bot.get_user()`
- `fetch_user()` fait un appel API pour récupérer les utilisateurs même s'ils ne sont pas en cache

### 2. Nouvelle commande de correction
Ajouté la commande `!corriger_noms_decouvreurs` qui :
- Parcourt toutes les découvertes existantes
- Identifie les noms au format "User_XXXXX"
- Récupère les vrais noms d'utilisateurs via l'API Discord
- Met à jour la base de données Google Sheets

## Utilisation

### Pour corriger les noms existants :
```
!corriger_noms_decouvreurs
```

Cette commande :
1. Analyse toutes les découvertes dans Google Sheets
2. Trouve les entrées avec des noms au format "User_XXXXX"
3. Récupère les vrais noms via l'API Discord
4. Met à jour la base de données
5. Rafraîchit le cache

### Résultat attendu
- Les cartes dans le forum afficheront maintenant les vrais noms d'utilisateurs
- Les nouvelles découvertes utiliseront automatiquement les vrais noms
- Les statistiques et informations de cartes seront également corrigées

## Notes techniques
- La correction est idempotente (peut être exécutée plusieurs fois sans problème)
- Seuls les noms au format "User_XXXXX" sont corrigés
- Si un utilisateur ne peut pas être récupéré (compte supprimé, etc.), son nom reste inchangé
- La correction se fait par batch pour optimiser les performances

## Commandes disponibles
- `!corriger_noms_decouvreurs` : Corrige les noms existants
- `!migrer_decouvertes force` : Refait la migration complète (⚠️ DANGER)
- `!statut_forum_cartes` : Vérifie le statut du système forum
