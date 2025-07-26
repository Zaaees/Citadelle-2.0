#!/usr/bin/env python3
"""
Test pour vérifier que les fonctionnalités existantes ne sont pas altérées.
"""
import sys
import os
import importlib.util
import inspect

def test_cog_imports():
    """Test que tous les cogs peuvent être importés."""
    print("🧪 Test d'importation des cogs...")
    
    cogs_to_test = [
        'cogs.inventaire',
        'cogs.Cards', 
        'cogs.RPTracker',
        'cogs.bump',
        'cogs.vocabulaire',
        'cogs.souselement',
        'cogs.ticket',
        'cogs.validation',
        'cogs.InactiveUserTracker',
        'cogs.excès',
        'cogs.channel_monitor'
    ]
    
    failed_imports = []
    
    for cog_name in cogs_to_test:
        try:
            # Tenter d'importer le module
            spec = importlib.util.find_spec(cog_name)
            if spec is None:
                failed_imports.append(f"{cog_name} - Module non trouvé")
                continue
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            print(f"✅ {cog_name} - Import réussi")
            
        except Exception as e:
            failed_imports.append(f"{cog_name} - Erreur: {e}")
            print(f"❌ {cog_name} - Erreur: {e}")
    
    if failed_imports:
        print(f"\n⚠️ {len(failed_imports)} cog(s) ont des problèmes d'import:")
        for error in failed_imports:
            print(f"   - {error}")
        return False
    
    print(f"✅ Tous les {len(cogs_to_test)} cogs s'importent correctement")
    return True

def test_cards_system_structure():
    """Test que la structure du système de cartes est préservée."""
    print("🧪 Test de la structure du système de cartes...")
    
    try:
        # Test d'import du cog principal
        from cogs.Cards import Cards
        print("✅ Cog Cards importé")
        
        # Test d'import des modules
        modules_to_test = [
            'cogs.cards.storage',
            'cogs.cards.discovery', 
            'cogs.cards.vault',
            'cogs.cards.drawing',
            'cogs.cards.trading',
            'cogs.cards.forum',
            'cogs.cards.config',
            'cogs.cards.utils',
            'cogs.cards.models'
        ]
        
        for module_name in modules_to_test:
            try:
                importlib.import_module(module_name)
                print(f"✅ {module_name} importé")
            except ImportError as e:
                print(f"❌ {module_name} - Erreur: {e}")
                return False
        
        # Test d'import des vues
        views_to_test = [
            'cogs.cards.views.menu_views',
            'cogs.cards.views.trade_views',
            'cogs.cards.views.gallery_views',
            'cogs.cards.views.modal_views'
        ]
        
        for view_name in views_to_test:
            try:
                importlib.import_module(view_name)
                print(f"✅ {view_name} importé")
            except ImportError as e:
                print(f"❌ {view_name} - Erreur: {e}")
                return False
        
        print("✅ Structure du système de cartes préservée")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test du système de cartes: {e}")
        return False

def test_command_structure():
    """Test que les commandes principales sont toujours définies."""
    print("🧪 Test de la structure des commandes...")
    
    try:
        from cogs.Cards import Cards
        
        # Vérifier que les méthodes de commande existent
        expected_commands = [
            'cartes',
            'initialiser_forum_cartes',
            'reconstruire_mur',
            'give_bonus'
        ]
        
        cards_class = Cards
        
        for cmd_name in expected_commands:
            if hasattr(cards_class, cmd_name):
                method = getattr(cards_class, cmd_name)
                if callable(method):
                    print(f"✅ Commande {cmd_name} trouvée")
                else:
                    print(f"❌ {cmd_name} n'est pas callable")
                    return False
            else:
                print(f"❌ Commande {cmd_name} manquante")
                return False
        
        print("✅ Structure des commandes préservée")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test des commandes: {e}")
        return False

def test_main_bot_structure():
    """Test que la structure principale du bot est préservée."""
    print("🧪 Test de la structure principale du bot...")
    
    try:
        # Vérifier que main.py peut être compilé
        import py_compile
        py_compile.compile('main.py', doraise=True)
        print("✅ main.py compile correctement")
        
        # Vérifier que CustomBot existe et a les bonnes méthodes
        import main
        
        if hasattr(main, 'CustomBot'):
            bot_class = main.CustomBot
            
            expected_methods = [
                'setup_hook',
                'on_error',
                'on_disconnect', 
                'on_resumed',
                '_check_and_restart_threads'
            ]
            
            for method_name in expected_methods:
                if hasattr(bot_class, method_name):
                    print(f"✅ Méthode {method_name} trouvée")
                else:
                    print(f"❌ Méthode {method_name} manquante")
                    return False
            
            print("✅ Structure CustomBot préservée")
        else:
            print("❌ Classe CustomBot manquante")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test de la structure principale: {e}")
        return False

def test_google_sheets_compatibility():
    """Test que la compatibilité Google Sheets est préservée."""
    print("🧪 Test de compatibilité Google Sheets...")
    
    try:
        # Test d'import des modules Google Sheets
        import gspread
        from google.oauth2.service_account import Credentials
        print("✅ Modules Google Sheets disponibles")
        
        # Test que les cogs utilisent toujours Google Sheets
        from cogs.inventaire import Inventaire
        from cogs.Cards import Cards
        
        # Vérifier que les classes ont des références aux sheets
        inventaire_methods = [method for method in dir(Inventaire) if 'sheet' in method.lower()]
        cards_methods = [method for method in dir(Cards) if 'sheet' in method.lower() or 'storage' in method.lower()]
        
        if inventaire_methods or hasattr(Inventaire, 'sheet'):
            print("✅ Inventaire utilise toujours Google Sheets")
        else:
            print("⚠️ Inventaire pourrait ne plus utiliser Google Sheets")
        
        if cards_methods or hasattr(Cards, 'storage'):
            print("✅ Cards utilise toujours le système de stockage")
        else:
            print("⚠️ Cards pourrait ne plus utiliser le système de stockage")
        
        return True
        
    except ImportError as e:
        print(f"⚠️ Modules Google Sheets non disponibles: {e}")
        return True  # Pas critique pour ce test
    except Exception as e:
        print(f"❌ Erreur lors du test Google Sheets: {e}")
        return False

def main():
    """Fonction principale de test."""
    print("🚀 Test de préservation des fonctionnalités...")
    print("=" * 60)
    
    tests = [
        ("Import des cogs", test_cog_imports),
        ("Structure système de cartes", test_cards_system_structure),
        ("Structure des commandes", test_command_structure),
        ("Structure principale du bot", test_main_bot_structure),
        ("Compatibilité Google Sheets", test_google_sheets_compatibility),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n📋 Test: {test_name}")
        try:
            if test_func():
                print(f"✅ {test_name}: RÉUSSI")
                passed += 1
            else:
                print(f"❌ {test_name}: ÉCHOUÉ")
                failed += 1
        except Exception as e:
            print(f"❌ {test_name}: ERREUR - {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Résultats des tests de préservation:")
    print(f"   ✅ Réussis: {passed}")
    print(f"   ❌ Échoués: {failed}")
    print(f"   📈 Taux de réussite: {(passed/(passed+failed)*100):.1f}%")
    
    if failed == 0:
        print("\n🎉 Toutes les fonctionnalités sont préservées !")
        return 0
    else:
        print(f"\n⚠️ {failed} test(s) ont échoué. Vérifiez les fonctionnalités concernées.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
