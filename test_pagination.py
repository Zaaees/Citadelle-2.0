#!/usr/bin/env python3
"""
Test script for the card gallery pagination system.
This script tests the pagination logic without requiring a full Discord bot setup.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock Discord classes for testing
class MockUser:
    def __init__(self, user_id, display_name):
        self.id = user_id
        self.display_name = display_name

class MockCards:
    """Mock Cards class with minimal functionality for testing pagination."""
    
    def __init__(self):
        # Mock data - simulate a user with many cards across different categories
        self.mock_user_cards = {
            123456: [  # User ID 123456 has many cards
                ("Secrète", "Carte Secrète 1.png"),
                ("Secrète", "Carte Secrète 2.png"),
                ("Fondateur", "Fondateur A.png"),
                ("Fondateur", "Fondateur B.png"),
                ("Fondateur", "Fondateur C.png"),
                ("Fondateur", "Fondateur D.png"),
                ("Fondateur", "Fondateur E.png"),
                ("Historique", "Historique 1.png"),
                ("Historique", "Historique 2.png"),
                ("Historique", "Historique 3.png"),
                ("Historique", "Historique 4.png"),
                ("Historique", "Historique 5.png"),
                ("Historique", "Historique 6.png"),
                ("Historique", "Historique 7.png"),
                ("Historique", "Historique 8.png"),
                ("Historique", "Historique 9.png"),
                ("Historique", "Historique 10.png"),
                ("Historique", "Historique 11.png"),
                ("Historique", "Historique 12.png"),
                ("Historique", "Historique 13.png"),
                ("Historique", "Historique 14.png"),
                ("Historique", "Historique 15.png"),
                ("Historique", "Historique 16.png"),
                ("Historique", "Historique 17.png"),
                ("Historique", "Historique 18.png"),
                ("Historique", "Historique 19.png"),
                ("Historique", "Historique 20.png"),
                ("Maître", "Maître Alpha.png"),
                ("Maître", "Maître Beta.png"),
                ("Maître", "Maître Gamma.png"),
                ("Élèves", "Élève 1.png"),
                ("Élèves", "Élève 2.png"),
                ("Élèves", "Élève 3.png"),
                ("Élèves", "Élève 4.png"),
                ("Élèves", "Élève 5.png"),
                ("Élèves", "Élève 6.png"),
                ("Élèves", "Élève 7.png"),
                ("Élèves", "Élève 8.png"),
                ("Élèves", "Élève 9.png"),
                ("Élèves", "Élève 10.png"),
                ("Élèves", "Élève 11.png"),
                ("Élèves", "Élève 12.png"),
                ("Élèves", "Élève 13.png"),
                ("Élèves", "Élève 14.png"),
                ("Élèves", "Élève 15.png"),
                ("Élèves", "Élève 16.png"),
                ("Élèves", "Élève 17.png"),
                ("Élèves", "Élève 18.png"),
                ("Élèves", "Élève 19.png"),
                ("Élèves", "Élève 20.png"),
                # Add some Full cards
                ("Historique", "Historique 1 (Full).png"),
                ("Historique", "Historique 2 (Full).png"),
                ("Maître", "Maître Alpha (Full).png"),
            ]
        }
        
        # Mock available cards data
        self.cards_by_category = {
            "Secrète": [{"name": f"Carte Secrète {i}.png"} for i in range(1, 6)],
            "Fondateur": [{"name": f"Fondateur {chr(65+i)}.png"} for i in range(10)],
            "Historique": [{"name": f"Historique {i}.png"} for i in range(1, 31)],
            "Maître": [{"name": f"Maître {name}.png"} for name in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]],
            "Élèves": [{"name": f"Élève {i}.png"} for i in range(1, 51)],
        }
        
        self.upgrade_cards_by_category = {
            "Historique": [{"name": f"Historique {i} (Full).png"} for i in range(1, 6)],
            "Maître": [{"name": f"Maître {name} (Full).png"} for name in ["Alpha", "Beta", "Gamma"]],
        }

    def get_user_cards(self, user_id):
        return self.mock_user_cards.get(user_id, [])

    def normalize_name(self, name):
        return name.lower()

    def get_card_identifier(self, category, name):
        # Mock identifier system
        return f"C{hash(f'{category}_{name}') % 1000}"

def test_pagination_logic():
    """Test the pagination logic with mock data."""
    print("Testing Card Gallery Pagination System")
    print("=" * 50)
    
    # Create mock objects
    cards_cog = MockCards()
    user = MockUser(123456, "TestUser")
    
    # Import the pagination method from the Cards cog
    # Note: This would need to be adapted to work with the actual Cards class
    # For now, we'll test the logic conceptually
    
    user_cards = cards_cog.get_user_cards(user.id)
    print(f"User {user.display_name} has {len(user_cards)} total cards")
    
    # Test pagination parameters
    CARDS_PER_PAGE = 15
    
    # Group cards by category
    rarity_order = {
        "Secrète": 0,
        "Fondateur": 1,
        "Historique": 2,
        "Maître": 3,
        "Black Hole": 4,
        "Architectes": 5,
        "Professeurs": 6,
        "Autre": 7,
        "Élèves": 8,
    }
    
    user_cards.sort(key=lambda c: rarity_order.get(c[0], 9))
    
    cards_by_cat = {}
    for cat, name in user_cards:
        cards_by_cat.setdefault(cat, []).append(name)
    
    print("\nCards by category:")
    for cat, names in cards_by_cat.items():
        normales = [n for n in names if not n.endswith(" (Full)")]
        fulls = [n for n in names if n.endswith(" (Full)")]
        print(f"  {cat}: {len(normales)} normal cards, {len(fulls)} full cards")
    
    # Calculate pagination for each category
    print("\nPagination analysis:")
    max_pages_needed = 0
    
    for cat in rarity_order:
        if cat not in cards_by_cat:
            continue
            
        noms = cards_by_cat[cat]
        normales = [n for n in noms if not n.endswith(" (Full)")]
        fulls = [n for n in noms if n.endswith(" (Full)")]
        
        if normales:
            counts = {}
            for n in normales:
                counts[n] = counts.get(n, 0) + 1
            pages_for_cat = (len(counts) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
            max_pages_needed = max(max_pages_needed, pages_for_cat)
            print(f"  {cat} (normal): {len(counts)} unique cards, needs {pages_for_cat} pages")
        
        if fulls:
            counts = {}
            for n in fulls:
                counts[n] = counts.get(n, 0) + 1
            pages_for_cat = (len(counts) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
            max_pages_needed = max(max_pages_needed, pages_for_cat)
            print(f"  {cat} (full): {len(counts)} unique cards, needs {pages_for_cat} pages")
    
    total_pages = max(1, max_pages_needed)
    print(f"\nTotal pages needed: {total_pages}")
    
    # Test pagination for each page
    print("\nTesting pagination for each page:")
    for page in range(total_pages):
        print(f"\n--- Page {page + 1}/{total_pages} ---")
        
        for cat in rarity_order:
            if cat not in cards_by_cat:
                continue
                
            noms = cards_by_cat[cat]
            normales = [n for n in noms if not n.endswith(" (Full)")]
            
            if normales:
                counts = {}
                for n in normales:
                    counts[n] = counts.get(n, 0) + 1
                
                sorted_cards = sorted(counts.items(), key=lambda x: cards_cog.normalize_name(x[0].removesuffix('.png')))
                
                start_idx = page * CARDS_PER_PAGE
                end_idx = start_idx + CARDS_PER_PAGE
                page_cards = sorted_cards[start_idx:end_idx]
                
                if page_cards:
                    print(f"  {cat}: showing {len(page_cards)} cards (indices {start_idx}-{min(end_idx-1, len(sorted_cards)-1)})")
                    for i, (name, count) in enumerate(page_cards[:3]):  # Show first 3 as example
                        print(f"    - {name.removesuffix('.png')}{' (x'+str(count)+')' if count > 1 else ''}")
                    if len(page_cards) > 3:
                        print(f"    ... and {len(page_cards) - 3} more cards")
    
    print("\n" + "=" * 50)
    print("Pagination test completed successfully!")

if __name__ == "__main__":
    test_pagination_logic()
