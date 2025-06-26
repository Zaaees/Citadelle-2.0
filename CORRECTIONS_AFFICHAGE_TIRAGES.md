# Corrections de l'Affichage des Tirages et Logique Sacrificiel

## 🐛 Problèmes Identifiés et Corrigés

### 1. **Tirage journalier en éphémère** ✅ CORRIGÉ
**Problème :** La première carte du tirage journalier s'affichait en message éphémère.
**Cause :** `await interaction.response.defer(ephemeral=True)` dans le bouton du tirage journalier.
**Solution :** Changé en `ephemeral=False` pour rendre tous les messages publics.

### 2. **Tirage sacrificiel en éphémère** ✅ CORRIGÉ
**Problème :** Le tirage sacrificiel s'affichait aussi en éphémère.
**Cause :** Même problème que le tirage journalier + message de confirmation final en éphémère.
**Solution :** 
- Changé `defer(ephemeral=True)` en `defer(ephemeral=False)`
- Changé le message de confirmation final en `ephemeral=False`

### 3. **Fausse détection "tirage sacrificiel déjà fait"** ✅ CORRIGÉ
**Problème :** Le système indiquait incorrectement qu'un tirage sacrificiel avait déjà été fait.
**Cause :** La feuille `sheet_sacrificial_draw` n'était PAS initialisée dans le nouveau système `CardsStorage`.
**Solution :** Ajout de l'initialisation de la feuille "Tirages Sacrificiels" dans `CardsStorage._init_worksheets()`.

## ✅ Corrections Apportées

### 1. Fichier `cogs/cards/views/menu_views.py`

#### 🔧 CORRECTION MAJEURE : Nouvelle logique d'affichage

**Problème identifié :** `edit_original_response()` hérite TOUJOURS du caractère éphémère initial, même avec `defer(ephemeral=False)`.

**Solution :** Utiliser uniquement `followup.send(ephemeral=False)` pour toutes les cartes.

#### Ligne 29-33 - Bouton tirage journalier
```python
# Avant
await interaction.response.defer(ephemeral=False)

# Après
await interaction.response.send_message(
    "🌅 **Tirage journalier en cours...**",
    ephemeral=True
)
```

#### Ligne 89-93 - Affichage des cartes (tirage journalier)
```python
# Avant
first_embed, first_file = embed_msgs[0]
await interaction.edit_original_response(content=None, embed=first_embed, attachments=[first_file])
for em, f in embed_msgs[1:]:
    await interaction.followup.send(embed=em, file=f, ephemeral=False)

# Après
for em, f in embed_msgs:
    await interaction.followup.send(embed=em, file=f, ephemeral=False)
```

#### Ligne 118-122 - Bouton tirage sacrificiel
```python
# Avant
await interaction.response.defer(ephemeral=False)

# Après
await interaction.response.send_message(
    "⚔️ **Préparation du tirage sacrificiel...**",
    ephemeral=True
)
```

#### Ligne 315-319 - Vue de confirmation sacrificiel
```python
# Avant
await interaction.response.defer(ephemeral=True)

# Après
await interaction.response.send_message(
    "⚔️ **Sacrifice en cours...**",
    ephemeral=True
)
```

### 2. Fichier `cogs/cards/storage.py`

#### Ajout de l'initialisation de la feuille sacrificielle (lignes 57-64)
```python
# Feuille des tirages sacrificiels
try:
    self.sheet_sacrificial_draw = self.spreadsheet.worksheet("Tirages Sacrificiels")
except gspread.exceptions.WorksheetNotFound:
    self.sheet_sacrificial_draw = self.spreadsheet.add_worksheet(
        title="Tirages Sacrificiels", rows="1000", cols="2"
    )
```

### 3. Fichier `cogs/cards/drawing.py`

#### Ajout de méthode de nettoyage du cache (lignes 321-343)
```python
def clear_sacrificial_cache(self, user_id: int = None):
    """Nettoie le cache du tirage sacrificiel."""
    # ... logique de nettoyage
```

### 4. Fichier `cogs/Cards.py`

#### Ajout de commande admin de debug (lignes 1325-1337)
```python
@commands.command(name="clear_sacrificial_cache")
@commands.has_permissions(administrator=True)
async def clear_sacrificial_cache(self, ctx, member: discord.Member = None):
    """Nettoie le cache du tirage sacrificiel."""
    # ... logique de commande
```

## 🎯 Résultats Attendus

- ✅ **Tirages journaliers** : Toutes les cartes s'affichent en public (NOUVEAU MESSAGES)
- ✅ **Tirages sacrificiels** : Affichage public de la carte obtenue (NOUVEAU MESSAGE)
- ✅ **Détection correcte** : Plus de faux positifs pour "tirage déjà fait"
- ✅ **Cache fonctionnel** : Système de cache du tirage sacrificiel opérationnel
- ✅ **Debug disponible** : Commande admin pour nettoyer le cache si nécessaire
- ✅ **Pas d'héritage éphémère** : Chaque carte = nouveau message public indépendant

## 🧪 Tests Recommandés

### Tests Immédiats
1. **Tirage journalier** : Vérifier que toutes les cartes s'affichent en public
2. **Tirage sacrificiel** : Vérifier que la carte obtenue s'affiche en public
3. **Détection sacrificiel** : Vérifier qu'un nouveau tirage sacrificiel est autorisé

### Tests de Debug (si problème persiste)
```
!clear_sacrificial_cache @utilisateur
```
ou
```
!clear_sacrificial_cache
```

## 📋 Changements Techniques

### Avant
- Messages éphémères (visibles seulement par l'utilisateur)
- `edit_original_response()` héritait du caractère éphémère
- Feuille "Tirages Sacrificiels" manquante
- Cache sacrificiel non fonctionnel

### Après
- Messages publics (visibles par tous) via `followup.send(ephemeral=False)`
- Chaque carte = nouveau message public indépendant
- Feuille "Tirages Sacrificiels" correctement initialisée
- Cache sacrificiel fonctionnel avec outils de debug
- Messages de statut éphémères séparés des cartes publiques

## 🚀 Impact Final

Ces corrections garantissent que :
1. **Toutes les cartes** des tirages s'affichent en **public**
2. **Aucun héritage** du caractère éphémère
3. **Logique cohérente** entre tirages journaliers et sacrificiels
4. **Affichage propre** avec messages de statut séparés
