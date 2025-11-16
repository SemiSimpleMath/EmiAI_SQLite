#!/usr/bin/env python3
"""
Debug script for entity card injection
"""

from app.assistant.entity_management.entity_card_injector import entity_card_injector
from app.models.base import get_session
from app.assistant.entity_management.entity_cards import get_entity_card_stats

def debug_injection():
    """Debug entity card injection"""
    
    print("=== Debugging Entity Card Injection ===\n")
    
    # 1. Check if we have entity cards
    session = get_session()
    stats = get_entity_card_stats(session)
    print(f"Entity cards in database: {stats['total_cards']} total, {stats['active_cards']} active")
    
    # 2. Test basic entity detection
    test_text = "Tell me about Seija"
    print(f"\nTest text: '{test_text}'")
    
    detected = entity_card_injector.detect_entities_in_text(test_text)
    print(f"Detected entities: {detected}")
    
    # 3. Test alias lookup
    print(f"\nTesting alias lookup for 'Joko':")
    canonical = entity_card_injector.find_entity_by_name_or_alias("Joko")
    print(f"Joko -> {canonical}")
    
    # 4. Test full injection
    print(f"\nTesting full injection:")
    enhanced, injected = entity_card_injector.inject_entity_cards_into_text(test_text, "chat")
    print(f"Injected entities: {injected}")
    print(f"Enhanced text preview: {enhanced[:300]}...")
    
    # 5. Test with alias
    alias_text = "Tell me about Joko"
    print(f"\nTest with alias: '{alias_text}'")
    enhanced2, injected2 = entity_card_injector.inject_entity_cards_into_text(alias_text, "chat")
    print(f"Injected entities: {injected2}")
    print(f"Enhanced text preview: {enhanced2[:300]}...")
    
    session.close()

if __name__ == "__main__":
    debug_injection()
