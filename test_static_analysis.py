#!/usr/bin/env python3
"""
Test statique pour vérifier que les modifications n'ont pas cassé la structure du code.
"""
import sys
import os
import ast
import py_compile

def test_syntax_compilation():
    """Test que tous les fichiers Python compilent correctement."""
    print("🧪 Test de compilation syntaxique...")
    
    python_files = []
    
    # Trouver tous les fichiers Python
    for root, dirs, files in os.walk('.'):
        # Ignorer les dossiers cachés et __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    failed_files = []
    
    for file_path in python_files:
        try:
            py_compile.compile(file_path, doraise=True)
            print(f"✅ {file_path}")
        except py_compile.PyCompileError as e:
            failed_files.append(f"{file_path}: {e}")
            print(f"❌ {file_path}: {e}")
        except Exception as e:
            failed_files.append(f"{file_path}: {e}")
            print(f"❌ {file_path}: {e}")
    
    if failed_files:
        print(f"\n⚠️ {len(failed_files)} fichier(s) ont des erreurs de compilation:")
        for error in failed_files:
            print(f"   - {error}")
        return False
    
    print(f"✅ Tous les {len(python_files)} fichiers Python compilent correctement")
    return True

def test_main_structure():
    """Test que la structure de main.py est correcte."""
    print("🧪 Test de la structure de main.py...")
    
    try:
        with open('main.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        # Vérifier les classes et fonctions importantes
        classes = []
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        
        expected_classes = ['CustomBot', 'HealthRequestHandler']
        expected_functions = ['main', 'check_bot_health', 'self_ping', 'start_http_server']
        
        missing_classes = [cls for cls in expected_classes if cls not in classes]
        missing_functions = [func for func in expected_functions if func not in functions]
        
        if missing_classes:
            print(f"❌ Classes manquantes: {missing_classes}")
            return False
        
        if missing_functions:
            print(f"❌ Fonctions manquantes: {missing_functions}")
            return False
        
        print("✅ Structure de main.py préservée")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de l'analyse de main.py: {e}")
        return False

def test_cogs_structure():
    """Test que la structure des cogs est préservée."""
    print("🧪 Test de la structure des cogs...")
    
    cog_files = [
        'cogs/inventaire.py',
        'cogs/Cards.py',
        'cogs/RPTracker.py',
        'cogs/bump.py',
        'cogs/vocabulaire.py',
        'cogs/souselement.py',
        'cogs/ticket.py',
        'cogs/validation.py',
        'cogs/InactiveUserTracker.py',
        'cogs/excès.py',
        'cogs/channel_monitor.py'
    ]
    
    missing_files = []
    syntax_errors = []
    
    for cog_file in cog_files:
        if not os.path.exists(cog_file):
            missing_files.append(cog_file)
            continue
        
        try:
            with open(cog_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Vérifier la syntaxe
            ast.parse(content)
            print(f"✅ {cog_file} - Syntaxe correcte")
            
        except SyntaxError as e:
            syntax_errors.append(f"{cog_file}: {e}")
            print(f"❌ {cog_file} - Erreur de syntaxe: {e}")
        except Exception as e:
            syntax_errors.append(f"{cog_file}: {e}")
            print(f"❌ {cog_file} - Erreur: {e}")
    
    if missing_files:
        print(f"❌ Fichiers manquants: {missing_files}")
        return False
    
    if syntax_errors:
        print(f"❌ Erreurs de syntaxe: {syntax_errors}")
        return False
    
    print("✅ Structure des cogs préservée")
    return True

def test_cards_system_files():
    """Test que les fichiers du système de cartes existent."""
    print("🧪 Test des fichiers du système de cartes...")
    
    cards_files = [
        'cogs/cards/config.py',
        'cogs/cards/models.py',
        'cogs/cards/utils.py',
        'cogs/cards/storage.py',
        'cogs/cards/discovery.py',
        'cogs/cards/vault.py',
        'cogs/cards/drawing.py',
        'cogs/cards/trading.py',
        'cogs/cards/forum.py',
        'cogs/cards/logging.py',
        'cogs/cards/views/menu_views.py',
        'cogs/cards/views/trade_views.py',
        'cogs/cards/views/gallery_views.py',
        'cogs/cards/views/modal_views.py'
    ]
    
    missing_files = []
    syntax_errors = []
    
    for cards_file in cards_files:
        if not os.path.exists(cards_file):
            missing_files.append(cards_file)
            continue
        
        try:
            with open(cards_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Vérifier la syntaxe
            ast.parse(content)
            print(f"✅ {cards_file}")
            
        except SyntaxError as e:
            syntax_errors.append(f"{cards_file}: {e}")
            print(f"❌ {cards_file} - Erreur de syntaxe: {e}")
        except Exception as e:
            syntax_errors.append(f"{cards_file}: {e}")
            print(f"❌ {cards_file} - Erreur: {e}")
    
    if missing_files:
        print(f"❌ Fichiers manquants: {missing_files}")
        return False
    
    if syntax_errors:
        print(f"❌ Erreurs de syntaxe: {syntax_errors}")
        return False
    
    print("✅ Fichiers du système de cartes préservés")
    return True

def test_new_utils_files():
    """Test que les nouveaux fichiers utils sont corrects."""
    print("🧪 Test des nouveaux fichiers utils...")
    
    utils_files = [
        'utils/__init__.py',
        'utils/health_monitor.py',
        'utils/connection_manager.py'
    ]
    
    for utils_file in utils_files:
        if not os.path.exists(utils_file):
            print(f"❌ Fichier manquant: {utils_file}")
            return False
        
        try:
            with open(utils_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Vérifier la syntaxe
            ast.parse(content)
            print(f"✅ {utils_file}")
            
        except SyntaxError as e:
            print(f"❌ {utils_file} - Erreur de syntaxe: {e}")
            return False
        except Exception as e:
            print(f"❌ {utils_file} - Erreur: {e}")
            return False
    
    print("✅ Nouveaux fichiers utils corrects")
    return True

def main():
    """Fonction principale de test."""
    print("🚀 Analyse statique du code...")
    print("=" * 50)
    
    tests = [
        ("Compilation syntaxique", test_syntax_compilation),
        ("Structure main.py", test_main_structure),
        ("Structure des cogs", test_cogs_structure),
        ("Fichiers système de cartes", test_cards_system_files),
        ("Nouveaux fichiers utils", test_new_utils_files),
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
    
    print("\n" + "=" * 50)
    print(f"📊 Résultats de l'analyse statique:")
    print(f"   ✅ Réussis: {passed}")
    print(f"   ❌ Échoués: {failed}")
    print(f"   📈 Taux de réussite: {(passed/(passed+failed)*100):.1f}%")
    
    if failed == 0:
        print("\n🎉 Toute la structure du code est préservée !")
        return 0
    else:
        print(f"\n⚠️ {failed} test(s) ont échoué. Vérifiez la structure du code.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
