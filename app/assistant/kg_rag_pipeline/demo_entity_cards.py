"""
Demo script for Entity Cards with Original Descriptions
Shows how entity cards store both original KG data and generated content
"""

from app.models.base import get_session
from app.assistant.entity_management.entity_cards import (
    get_entity_card_by_name,
    get_entity_card_for_prompt_injection,
    get_entity_card_stats,
    search_entity_cards
)
from app.assistant.kg_rag_pipeline.kg_rag_pipeline import process_single_node
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def demo_entity_card_creation():
    """Demo creating an entity card with original KG data"""
    print("=== Entity Card Creation Demo ===\n")
    
    # Process a single node to create an entity card
    print("Processing node 'Jukka' to create entity card...")
    result = process_single_node("Jukka")
    
    if result:
        print("✅ Entity card created successfully!")
        print(f"  Entity Name: {result.get('entity_name', 'N/A')}")
        print(f"  Entity Type: {result.get('entity_type', 'N/A')}")
        print(f"  Summary: {result.get('summary', 'N/A')[:200]}...")
    else:
        print("❌ Failed to create entity card")
    
    print()


def demo_entity_card_retrieval():
    """Demo retrieving entity cards from database"""
    print("=== Entity Card Retrieval Demo ===\n")
    
    session = get_session()
    
    try:
        # Get entity card by name
        entity_name = "Jukka"
        entity_card = get_entity_card_by_name(session, entity_name)
        
        if entity_card:
            print(f"✅ Retrieved entity card for '{entity_name}':")
            print(f"  ID: {entity_card.id}")
            print(f"  Type: {entity_card.entity_type}")
            print(f"  Source Node ID: {entity_card.source_node_id}")
            print(f"  Created: {entity_card.created_at}")
            print(f"  Usage Count: {entity_card.usage_count}")
            print()
            
            # Show original KG data
            print("📋 Original Knowledge Graph Data:")
            print(f"  Original Description: {entity_card.original_description or 'None'}")
            print(f"  Original Aliases: {entity_card.original_aliases or []}")
            print()
            
            # Show generated content
            print("🤖 Generated Content:")
            print(f"  Summary: {entity_card.summary[:200]}...")
            print(f"  Key Facts: {len(entity_card.key_facts or [])} facts")
            print(f"  Relationships: {len(entity_card.relationships or [])} relationships")
            print(f"  Processed Aliases: {entity_card.aliases or []}")
            print(f"  Confidence: {entity_card.confidence}")
            print()
            
            # Show metadata
            print("📊 Metadata:")
            print(f"  Batch: {entity_card.batch_number}/{entity_card.total_batches}")
            print(f"  Is Active: {entity_card.is_active}")
            print(f"  Last Used: {entity_card.last_used}")
            print(f"  Card Metadata: {entity_card.card_metadata}")
            print()
            
        else:
            print(f"❌ Entity card for '{entity_name}' not found")
            
    except Exception as e:
        print(f"❌ Error retrieving entity card: {e}")
    finally:
        session.close()


def demo_prompt_injection():
    """Demo prompt injection formatting"""
    print("=== Prompt Injection Demo ===\n")
    
    session = get_session()
    
    try:
        entity_name = "Jukka"
        formatted_card = get_entity_card_for_prompt_injection(session, entity_name)
        
        if formatted_card:
            print(f"✅ Prompt injection format for '{entity_name}':")
            print("=" * 60)
            print(formatted_card)
            print("=" * 60)
            print()
        else:
            print(f"❌ No entity card found for '{entity_name}'")
            
    except Exception as e:
        print(f"❌ Error with prompt injection: {e}")
    finally:
        session.close()


def demo_search_functionality():
    """Demo searching entity cards"""
    print("=== Search Functionality Demo ===\n")
    
    session = get_session()
    
    try:
        # Search by different terms
        search_terms = ["Jukka", "person", "work", "company"]
        
        for term in search_terms:
            results = search_entity_cards(session, term, limit=3)
            print(f"🔍 Search for '{term}': {len(results)} results")
            
            for i, card in enumerate(results, 1):
                print(f"  {i}. {card.entity_name} ({card.entity_type})")
                if card.original_description:
                    print(f"     Description: {card.original_description[:100]}...")
            print()
            
    except Exception as e:
        print(f"❌ Error with search: {e}")
    finally:
        session.close()


def demo_database_stats():
    """Demo database statistics"""
    print("=== Database Statistics Demo ===\n")
    
    session = get_session()
    
    try:
        stats = get_entity_card_stats(session)
        
        print("📊 Entity Card Database Statistics:")
        print(f"  Total Cards: {stats['total_cards']}")
        print(f"  Active Cards: {stats['active_cards']}")
        print(f"  Total Usage: {stats['total_usage']}")
        print()
        
        if stats['type_stats']:
            print("📈 Usage by Type:")
            for type_stat in stats['type_stats']:
                print(f"  {type_stat['entity_type']}: {type_stat['count']} cards, {type_stat['total_usage']} uses")
        else:
            print("  No type statistics available")
            
    except Exception as e:
        print(f"❌ Error getting statistics: {e}")
    finally:
        session.close()


def main():
    """Main demo function"""
    print("🎯 Entity Cards with Original Descriptions Demo\n")
    
    # Demo 1: Create entity card
    demo_entity_card_creation()
    
    # Demo 2: Retrieve and display entity card
    demo_entity_card_retrieval()
    
    # Demo 3: Prompt injection formatting
    demo_prompt_injection()
    
    # Demo 4: Search functionality
    demo_search_functionality()
    
    # Demo 5: Database statistics
    demo_database_stats()
    
    print("🎉 Demo Complete!")


if __name__ == "__main__":
    main()
