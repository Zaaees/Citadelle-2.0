# 🎴 Guide du Système Forum des Cartes

## Vue d'ensemble

Le système forum des cartes transforme le mur de cartes traditionnel en une structure organisée par threads, où chaque catégorie de cartes dispose de son propre thread avec des statistiques de progression en temps réel.

## 🏗️ Structure du Forum

### Threads par Catégorie
- **10 threads au total** : Un pour chaque catégorie de cartes
- **Catégories normales** : Secrète, Fondateur, Historique, Maître, Black Hole, Architectes, Professeurs, Autre, Élèves
- **Catégorie spéciale** : Full (toutes les cartes Full de toutes catégories)

### Organisation des Cartes
- **Ordre chronologique** : Les cartes apparaissent dans l'ordre de découverte
- **Thread automatique** : Les cartes Full sont automatiquement dirigées vers le thread "Cartes Full"
- **Métadonnées préservées** : Découvreur, index de découverte, timestamp

## 📊 Système de Compteurs

### Statistiques par Catégorie
Chaque thread affiche dans son message épinglé :
- **Progression catégorie** : `X/Y cartes découvertes (Z restantes)`
- **Exemple** : `📊 Progression Élèves : 30/50 (20 restantes)`

### Statistiques Globales
Affichées dans tous les threads :
- **Toutes cartes** : Inclut les cartes normales et Full
- **Hors Full** : Exclut les cartes Full du décompte
- **Exemple** : 
  ```
  📈 Progression Globale
  Toutes cartes : 120/200 (80 restantes)
  Hors Full : 112/185 (73 restantes)
  ```

### Mise à Jour Automatique
- **Temps réel** : Les statistiques se mettent à jour automatiquement lors de nouvelles découvertes
- **Messages épinglés** : Les compteurs sont toujours visibles en haut de chaque thread

## 🚀 Commandes d'Administration

### Configuration Initiale

#### 1. Configurer le Canal Forum
```
!configurer_forum_cartes <forum_channel_id>
```
- Active le système forum
- Remplace le système de mur legacy
- Utiliser `!configurer_forum_cartes` sans paramètre pour désactiver

#### 2. Initialiser la Structure
```
!initialiser_forum_cartes <forum_channel_id>
```
- Crée tous les threads de catégories
- Migre toutes les cartes découvertes existantes
- Configure les messages épinglés avec statistiques
- **⚠️ À exécuter une seule fois lors de la migration**

### Gestion Continue

#### 3. Vérifier le Statut
```
!statut_forum_cartes
```
- Affiche l'état actuel du système
- Montre le canal forum configuré
- Compte les threads créés

#### 4. Mettre à Jour les Statistiques
```
!mettre_a_jour_forum_cartes
```
- Recalcule et met à jour tous les compteurs
- Utile après des modifications manuelles
- Répare les messages épinglés si nécessaire

## 🔧 Fonctionnement Technique

### Détection des Cartes Full
- **Critère** : Nom se terminant par `" (Full)"`
- **Routage automatique** : Toutes les cartes Full vont dans le thread "Cartes Full"
- **Comptage séparé** : Les Full sont comptées à part dans les statistiques

### Gestion des Threads
- **Création automatique** : Nouveaux threads créés au besoin
- **Réouverture** : Les threads archivés/verrouillés sont automatiquement rouverts
- **Messages épinglés** : Le premier message de chaque thread est épinglé avec les stats

### Compatibilité
- **Mode dual** : Peut basculer entre forum et legacy
- **Migration sûre** : Toutes les données existantes sont préservées
- **Rollback possible** : Retour au système legacy si nécessaire

## 📋 Exemple d'Utilisation

### Mise en Place Complète
```bash
# 1. Créer un canal Forum dans Discord
# 2. Noter l'ID du canal (ex: 1234567890)

# 3. Configurer le système
!configurer_forum_cartes 1234567890

# 4. Initialiser et migrer
!initialiser_forum_cartes 1234567890

# 5. Vérifier le résultat
!statut_forum_cartes
```

### Maintenance
```bash
# Mettre à jour les statistiques si nécessaire
!mettre_a_jour_forum_cartes

# Vérifier l'état du système
!statut_forum_cartes

# Désactiver le forum (retour au legacy)
!configurer_forum_cartes
```

## 🎯 Avantages du Système Forum

### Organisation
- **Séparation claire** par catégorie de cartes
- **Navigation facile** entre les différents types
- **Historique préservé** dans chaque thread

### Visibilité
- **Statistiques toujours visibles** grâce aux messages épinglés
- **Progression claire** par catégorie et globale
- **Compteurs en temps réel** mis à jour automatiquement

### Scalabilité
- **Gestion automatique** des threads
- **Performance optimisée** pour de gros volumes
- **Maintenance minimale** requise

## ⚠️ Notes Importantes

- **Permissions** : Le bot doit avoir les permissions de gestion des threads et d'épinglage
- **Canal Forum** : Seuls les canaux de type Forum sont supportés
- **Migration unique** : L'initialisation ne doit être faite qu'une seule fois
- **Sauvegarde** : Les données existantes sont préservées pendant la migration
