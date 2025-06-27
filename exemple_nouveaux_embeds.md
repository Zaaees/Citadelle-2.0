# Exemples des nouveaux embeds de cartes

## Avant (ancien système)
```
┌─────────────────────────────────────┐
│ Nom de la carte                     │
├─────────────────────────────────────┤
│ Catégorie : **Élèves**              │
│ 🎯 Tiré par : **NomUtilisateur**    │
└─────────────────────────────────────┘
```

## Après (nouveau système)

### Cas 1 : Nouvelle carte découverte
```
┌─────────────────────────────────────┐
│ Nom de la carte                     │
├─────────────────────────────────────┤
│ Catégorie : **Élèves**              │
│ 🎯 Tiré par : **NomUtilisateur**    │
│ ✨ **NOUVELLE CARTE !**             │
│ 💫 Version **Full** pas encore      │
│    obtenue                          │
└─────────────────────────────────────┘
```

### Cas 2 : Carte déjà possédée (sans Full)
```
┌─────────────────────────────────────┐
│ Nom de la carte                     │
├─────────────────────────────────────┤
│ Catégorie : **Élèves**              │
│ 🎯 Tiré par : **NomUtilisateur**    │
│ 📊 Vous en avez maintenant : **3**  │
│ 💫 Version **Full** pas encore      │
│    obtenue                          │
└─────────────────────────────────────┘
```

### Cas 3 : Carte déjà possédée (avec Full)
```
┌─────────────────────────────────────┐
│ Nom de la carte                     │
├─────────────────────────────────────┤
│ Catégorie : **Élèves**              │
│ 🎯 Tiré par : **NomUtilisateur**    │
│ 📊 Vous en avez maintenant : **5**  │
│ ⭐ Vous possédez déjà la version     │
│    **Full** !                       │
└─────────────────────────────────────┘
```

### Cas 4 : Carte Full tirée
```
┌─────────────────────────────────────┐
│ Nom de la carte (Full)              │
├─────────────────────────────────────┤
│ Catégorie : **Élèves**              │
│ 🎯 Tiré par : **NomUtilisateur**    │
│ ✨ **NOUVELLE CARTE !**             │
└─────────────────────────────────────┘
```

### Cas 5 : Carte sans version Full possible
```
┌─────────────────────────────────────┐
│ Nom de la carte                     │
├─────────────────────────────────────┤
│ Catégorie : **Professeurs**         │
│ 🎯 Tiré par : **NomUtilisateur**    │
│ 📊 Vous en avez maintenant : **2**  │
└─────────────────────────────────────┘
```

## Fonctionnalités implémentées

✅ **Détection de nouvelle carte** : Affiche "NOUVELLE CARTE !" si c'est la première fois que l'utilisateur obtient cette carte

✅ **Comptage des exemplaires** : Affiche le nombre total d'exemplaires après ajout de la carte tirée

✅ **Statut des cartes Full** : 
- Indique si l'utilisateur possède déjà la version Full
- Seulement pour les cartes qui peuvent avoir une version Full
- N'affiche rien pour les cartes sans version Full possible

✅ **Ordre d'exécution correct** : L'embed est créé AVANT l'ajout à l'inventaire pour un affichage précis

✅ **Compatibilité** : Fonctionne avec tous les types de tirages (journalier, sacrificiel, etc.)
