"""
Test script to demonstrate the agent's decision-making process for entity card creation
"""

from app.assistant.kg_rag_pipeline.kg_rag_pipeline import process_single_node, run_entity_card_pipeline
from app.assistant.entity_management.entity_cards import get_entity_card_by_name, get_entity_card_database_stats
from app.models.base import get_session
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def test_agent_decisions():
    """Test the agent's decision-making process with different types of entities"""
    print("=== Testing Agent Decision-Making Process ===\n")
    
    # Test cases: entities that should and shouldn't get cards
    test_entities = [
        # Should get cards (specific, useful for injection)
        "Katy",  # Specific person name
        "Microsoft",  # Specific company
        "Python",  # Specific technology
        "San Francisco",  # Specific location
        "Karjalohja",  # Leaf node - specific location
        "Saxophone",  # Leaf node - specific instrument
        
        # Should NOT get cards (generic, would create noise)
        "friend",  # Generic relationship
        "meeting",  # Generic activity
        "work",  # Generic concept
    ]
    
    for entity_name in test_entities:
        print(f"Testing entity: '{entity_name}'")
        print("-" * 50)
        
        try:
            result = process_single_node(entity_name)
            
            if result:
                if isinstance(result, dict) and result.get("decision") == "rejected":
                    print(f"❌ Agent REJECTED: {result.get('reason', 'Not useful for prompt injection')}")
                else:
                    print(f"✅ Agent APPROVED: Generated entity card")
                    print(f"   Entity Name: {result.get('entity_name', 'N/A')}")
                    print(f"   Entity Type: {result.get('entity_type', 'N/A')}")
                    print(f"   Summary: {result.get('summary', 'N/A')[:100]}...")
                    print(f"   Key Facts: {len(result.get('key_facts', []))} facts")
                    print(f"   Relationships: {len(result.get('relationships', []))} relationships")
            else:
                print(f"❌ Processing failed or node not found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()


def test_pipeline_with_agent_decisions():
    """Test the full pipeline with agent decision-making"""
    print("=== Testing Full Pipeline with Agent Decisions ===\n")
    
    try:
        # Run pipeline with minimum 1 outgoing edge (no importance filtering)
        result = run_entity_card_pipeline(min_outgoing_edges=1)
        
        print(f"✅ Pipeline Results:")
        print(f"  Processed: {result['processed']} cards created")
        print(f"  Errors: {result['errors']} processing errors")
        print(f"  Skipped: {result['skipped']} hardcoded skips")
        print(f"  Agent Rejected: {result['agent_rejected']} not useful for injection")
        
        # Show database stats
        db_stats = get_entity_card_database_stats()
        print(f"\n📊 Database Stats:")
        print(f"  Total cards: {db_stats['total_cards']}")
        print(f"  Active cards: {db_stats['active_cards']}")
        print(f"  Total usage: {db_stats['total_usage']}")
        
    except Exception as e:
        print(f"❌ Pipeline error: {e}")


def test_specific_entity_analysis():
    """Test detailed analysis of a specific entity"""
    print("=== Testing Specific Entity Analysis ===\n")
    
    # Test with a specific entity that should get a card
    entity_name = "Katy"  # Change this to test different entities
    
    print(f"Analyzing entity: '{entity_name}'")
    print("=" * 60)
    
    try:
        result = process_single_node(entity_name)
        
        if result and not isinstance(result, dict):
            print(f"✅ Entity Card Generated:")
            print(f"  Name: {result.get('entity_name')}")
            print(f"  Type: {result.get('entity_type')}")
            print(f"  Summary: {result.get('summary')}")
            print(f"  Key Facts:")
            for i, fact in enumerate(result.get('key_facts', []), 1):
                print(f"    {i}. {fact}")
            print(f"  Relationships:")
            for i, rel in enumerate(result.get('relationships', []), 1):
                print(f"    {i}. {rel}")
            print(f"  Confidence: {result.get('confidence')}")
            
            # Check if it's in the database
            session = get_session()
            try:
                db_card = get_entity_card_by_name(session, entity_name)
                if db_card:
                    print(f"\n📋 Database Entry:")
                    print(f"  ID: {db_card.id}")
                    print(f"  Created: {db_card.created_at}")
                    print(f"  Usage Count: {db_card.usage_count}")
                    print(f"  Is Active: {db_card.is_active}")
                else:
                    print(f"\n❌ Not found in database")
            finally:
                session.close()
                
        elif isinstance(result, dict) and result.get("decision") == "rejected":
            print(f"❌ Agent Decision: REJECTED")
            print(f"  Reason: {result.get('reason')}")
        else:
            print(f"❌ Processing failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("🧠 Entity Card Pipeline - Agent Decision Testing\n")
    
    # Test individual entity decisions
    test_agent_decisions()
    
    # Test full pipeline
    test_pipeline_with_agent_decisions()
    
    # Test specific entity analysis
    test_specific_entity_analysis()
    
    print("\n✅ Testing completed!")
