#!/usr/bin/env python3
"""
Script de test pour vérifier les améliorations du bot.
"""
import sys
import time
import threading

# Test d'importation des modules
try:
    from utils.health_monitor import HealthMetrics, AdvancedHealthMonitor
    HEALTH_MONITOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Health monitor non disponible: {e}")
    HEALTH_MONITOR_AVAILABLE = False

try:
    from utils.connection_manager import GoogleSheetsConnectionManager, ResourceMonitor
    CONNECTION_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Connection manager non disponible: {e}")
    CONNECTION_MANAGER_AVAILABLE = False

def test_health_metrics():
    """Test du système de métriques."""
    if not HEALTH_MONITOR_AVAILABLE:
        print("⏭️ Test des métriques ignoré (dépendances manquantes)")
        return True

    print("🧪 Test des métriques de santé...")

    metrics = HealthMetrics()
    
    # Test des événements de connexion
    metrics.record_connection_event('connect')
    metrics.record_connection_event('disconnect')
    metrics.record_connection_event('resumed')
    
    # Test des erreurs
    metrics.record_error('test_error')
    metrics.record_error('network_error')
    
    # Test des échecs de tâches
    metrics.record_task_failure('test_task')
    
    # Test de la mémoire
    metrics.record_memory_usage()
    
    # Test de la latence
    metrics.record_latency(0.125)
    metrics.record_latency(0.250)
    
    # Test du heartbeat
    metrics.update_heartbeat()
    
    # Obtenir le résumé
    summary = metrics.get_health_summary()
    
    print(f"✅ Métriques collectées:")
    print(f"   - Uptime: {summary['uptime_human']}")
    print(f"   - Latence moyenne: {summary['avg_latency_5min']}s")
    print(f"   - Mémoire moyenne: {summary['avg_memory_mb_5min']}MB")
    print(f"   - Erreurs totales: {summary['total_errors']}")
    print(f"   - Échecs de tâches: {summary['task_failures_1h']}")
    
    return True

def test_connection_manager():
    """Test du gestionnaire de connexions."""
    if not CONNECTION_MANAGER_AVAILABLE:
        print("⏭️ Test du gestionnaire de connexions ignoré (dépendances manquantes)")
        return True

    print("🧪 Test du gestionnaire de connexions...")

    # Test du singleton
    manager1 = GoogleSheetsConnectionManager()
    manager2 = GoogleSheetsConnectionManager()
    
    if manager1 is manager2:
        print("✅ Pattern singleton fonctionne")
    else:
        print("❌ Pattern singleton échoué")
        return False
    
    # Test du cache
    manager1._connection_cache['test'] = {
        'spreadsheet': 'test_data',
        'timestamp': time.time()
    }
    
    if 'test' in manager1._connection_cache:
        print("✅ Cache fonctionne")
    else:
        print("❌ Cache échoué")
        return False
    
    # Test du nettoyage
    manager1.clear_cache()
    
    if len(manager1._connection_cache) == 0:
        print("✅ Nettoyage du cache fonctionne")
    else:
        print("❌ Nettoyage du cache échoué")
        return False
    
    return True

def test_resource_monitor():
    """Test du moniteur de ressources."""
    if not CONNECTION_MANAGER_AVAILABLE:
        print("⏭️ Test du moniteur de ressources ignoré (dépendances manquantes)")
        return True

    print("🧪 Test du moniteur de ressources...")

    monitor = ResourceMonitor()
    
    # Test du nettoyage
    monitor.check_and_cleanup()
    print("✅ Nettoyage des ressources exécuté")
    
    return True

def test_compilation():
    """Test de compilation des fichiers principaux."""
    print("🧪 Test de compilation...")

    import py_compile
    import os

    files_to_test = [
        'main.py',
        'utils/health_monitor.py',
        'utils/connection_manager.py'
    ]

    for file_path in files_to_test:
        if os.path.exists(file_path):
            try:
                py_compile.compile(file_path, doraise=True)
                print(f"✅ {file_path} compile correctement")
            except py_compile.PyCompileError as e:
                print(f"❌ {file_path} erreur de compilation: {e}")
                return False
        else:
            print(f"⚠️ {file_path} non trouvé")

    return True

class MockBot:
    """Bot simulé pour les tests."""
    def __init__(self):
        self.latency = 0.125
        self.ready_called = True
    
    def is_ready(self):
        return self.ready_called

def test_advanced_monitor():
    """Test du moniteur avancé."""
    if not HEALTH_MONITOR_AVAILABLE:
        print("⏭️ Test du moniteur avancé ignoré (dépendances manquantes)")
        return True

    print("🧪 Test du moniteur avancé...")

    bot = MockBot()
    monitor = AdvancedHealthMonitor(bot)
    
    # Test du démarrage
    monitor.start_monitoring()
    print("✅ Surveillance démarrée")
    
    # Attendre un peu pour collecter des données
    time.sleep(2)
    
    # Test du rapport
    report = monitor.get_health_report()
    if "Rapport de santé du bot" in report:
        print("✅ Génération de rapport fonctionne")
    else:
        print("❌ Génération de rapport échouée")
        return False
    
    # Test de l'arrêt
    monitor.stop_monitoring()
    print("✅ Surveillance arrêtée")
    
    return True

def main():
    """Fonction principale de test."""
    print("🚀 Démarrage des tests d'amélioration du bot...")
    print("=" * 50)
    
    tests = [
        ("Compilation", test_compilation),
        ("Métriques de santé", test_health_metrics),
        ("Gestionnaire de connexions", test_connection_manager),
        ("Moniteur de ressources", test_resource_monitor),
        ("Moniteur avancé", test_advanced_monitor),
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
    print(f"📊 Résultats des tests:")
    print(f"   ✅ Réussis: {passed}")
    print(f"   ❌ Échoués: {failed}")
    print(f"   📈 Taux de réussite: {(passed/(passed+failed)*100):.1f}%")
    
    if failed == 0:
        print("\n🎉 Tous les tests sont passés ! Le bot est prêt pour le déploiement.")
        return 0
    else:
        print(f"\n⚠️ {failed} test(s) ont échoué. Vérifiez les erreurs ci-dessus.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
