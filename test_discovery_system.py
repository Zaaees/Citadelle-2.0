#!/usr/bin/env python3
"""
Test script pour vérifier le nouveau système de découverte des cartes.
Ce script teste les nouvelles fonctionnalités sans nécessiter Discord.
"""

import os
import sys
import json
from datetime import datetime
from unittest.mock import Mock, MagicMock

# Ajouter le répertoire parent au path pour importer le cog
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_discovery_system():
    """Test basique du système de découverte."""
    print("🧪 Test du nouveau système de découverte des cartes")
    
    # Mock des dépendances Discord et Google Sheets
    mock_bot = Mock()
    mock_sheet = Mock()
    mock_sheet.get_all_values.return_value = [
        ["Card_Category", "Card_Name", "Discoverer_ID", "Discoverer_Name", "Discovery_Timestamp", "Discovery_Index"],
        ["Élèves", "Test Card 1", "123456789", "TestUser1", "2024-01-01T10:00:00", "1"],
        ["Professeurs", "Test Card 2", "987654321", "TestUser2", "2024-01-01T11:00:00", "2"]
    ]
    mock_sheet.append_row = Mock()
    mock_sheet.append_rows = Mock()
    
    # Créer une instance mock du cog Cards
    from cogs.Cards import Cards
    
    # Mock les méthodes qui nécessitent des credentials Google
    Cards.__init__ = Mock(return_value=None)
    
    cards_cog = Cards(mock_bot)
    cards_cog.sheet_discoveries = mock_sheet
    cards_cog.discoveries_cache = None
    cards_cog.discoveries_cache_time = 0
    cards_cog._discoveries_lock = Mock()
    cards_cog._discoveries_lock.__enter__ = Mock(return_value=None)
    cards_cog._discoveries_lock.__exit__ = Mock(return_value=None)
    
    # Test 1: Récupération des cartes découvertes
    print("📋 Test 1: Récupération des cartes découvertes")
    discovered = cards_cog.get_discovered_cards()
    expected = {("Élèves", "Test Card 1"), ("Professeurs", "Test Card 2")}
    assert discovered == expected, f"Attendu {expected}, obtenu {discovered}"
    print("✅ Test 1 réussi")
    
    # Test 2: Récupération d'informations de découverte spécifique
    print("📋 Test 2: Récupération d'informations de découverte")
    info = cards_cog.get_discovery_info("Élèves", "Test Card 1")
    expected_info = {
        'discoverer_id': 123456789,
        'discoverer_name': 'TestUser1',
        'timestamp': '2024-01-01T10:00:00',
        'discovery_index': 1
    }
    assert info == expected_info, f"Attendu {expected_info}, obtenu {info}"
    print("✅ Test 2 réussi")
    
    # Test 3: Enregistrement d'une nouvelle découverte
    print("📋 Test 3: Enregistrement d'une nouvelle découverte")
    # Mock datetime.now() pour un timestamp prévisible
    original_datetime = datetime
    datetime.now = Mock(return_value=Mock(isoformat=Mock(return_value="2024-01-01T12:00:00")))
    
    discovery_index = cards_cog.log_discovery("Maître", "New Card", 555666777, "NewUser")
    
    # Vérifier que append_row a été appelé avec les bonnes données
    expected_call = ["Maître", "New Card", "555666777", "NewUser", "2024-01-01T12:00:00", "3"]
    mock_sheet.append_row.assert_called_with(expected_call)
    assert discovery_index == 3, f"Attendu index 3, obtenu {discovery_index}"
    print("✅ Test 3 réussi")
    
    # Restaurer datetime
    datetime.now = original_datetime.now
    
    print("🎉 Tous les tests sont passés avec succès!")
    print("\n📝 Résumé des fonctionnalités testées:")
    print("- ✅ Récupération des cartes découvertes depuis la nouvelle feuille")
    print("- ✅ Récupération d'informations détaillées de découverte")
    print("- ✅ Enregistrement de nouvelles découvertes avec index automatique")
    print("\n🚀 Le nouveau système de découverte est prêt à être déployé!")

if __name__ == "__main__":
    test_discovery_system()
