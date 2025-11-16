"""
Test script for the Simple Entity Card Pipeline
"""

from app.assistant.kg_rag_pipeline.kg_rag_pipeline import (
    process_single_node,
    get_pipeline_stats,
    get_importance_stats,
    get_entity_card_database_stats
)
from app.assistant.entity_management.entity_cards import (
    get_entity_card_by_name,
    search_entity_cards,
    get_entity_cards_by_type,
    get_most_used_entity_cards,
    get_entity_card_for_prompt_injection
)
from app.models.base import get_session
from app.assistant.utils.logging_config import get_logger
from app.assistant.entity_management.entity_cards import EntityCard

logger = get_logger(__name__)


def test_pipeline_stats():
    """Test getting pipeline statistics"""
    print("Testing Pipeline Statistics...")
    
    stats = get_pipeline_stats()
    print(f"✅ Pipeline Stats:")
    print(f"  Total nodes: {stats['total_nodes']}")
    print(f"  Nodes with outgoing edges: {stats['nodes_with_outgoing_edges']}")
    print(f"  Nodes with multiple outgoing: {stats['nodes_with_multiple_outgoing']}")
    print(f"  Isolated nodes: {stats['isolated_nodes']}")


def test_importance_stats():
    """Test getting importance statistics"""
    print("\nTesting Importance Statistics...")
    
    importance_stats = get_importance_stats()
    print(f"✅ Importance Distribution:")
    print(f"  High importance (>=0.7): {importance_stats['high_importance']}")
    print(f"  Medium importance (0.4-0.69): {importance_stats['medium_importance']}")
    print(f"  Low importance (0.1-0.39): {importance_stats['low_importance']}")
    print(f"  Minimal importance (<0.1): {importance_stats['minimal_importance']}")


def test_database_stats():
    """Test getting database statistics"""
    print("\nTesting Database Statistics...")
    
    try:
        stats = get_entity_card_database_stats()
        print(f"✅ Entity Card Database Stats:")
        print(f"  Total cards: {stats['total_cards']}")
        print(f"  Active cards: {stats['active_cards']}")
        print(f"  Total usage: {stats['total_usage']}")
        
        if stats['type_stats']:
            print(f"  Type distribution:")
            for type_stat in stats['type_stats']:
                print(f"    {type_stat['entity_type']}: {type_stat['count']} cards")
    except Exception as e:
        print(f"❌ Error getting database stats: {e}")


def test_database_operations():
    """Test database operations"""
    print("\nTesting Database Operations...")
    
    session = get_session()
    
    try:
        # Test searching entity cards
        search_results = search_entity_cards(session, "test", limit=5)
        print(f"✅ Search results: {len(search_results)} cards found")
        
        # Test getting cards by type
        person_cards = get_entity_cards_by_type(session, "person", limit=5)
        print(f"✅ Person cards: {len(person_cards)} found")
        
        # Test getting most used cards
        most_used = get_most_used_entity_cards(session, limit=5)
        print(f"✅ Most used cards: {len(most_used)} found")
        
    except Exception as e:
        print(f"❌ Error testing database operations: {e}")
    finally:
        session.close()


def test_single_node():
    """Test processing a single node"""
    print("\nTesting Single Node Processing...")
    
    # Test with a node that likely exists
    result = process_single_node("Jukka")
    
    if result:
        print("✅ Successfully generated entity card:")
        print(f"  Entity Name: {result.get('entity_name', 'N/A')}")
        print(f"  Entity Type: {result.get('entity_type', 'N/A')}")
        print(f"  Summary: {result.get('summary', 'N/A')[:200]}...")
        print(f"  Key Facts: {len(result.get('key_facts', []))} facts")
        print(f"  Relationships: {len(result.get('relationships', []))} relationships")
        
        # Test database retrieval
        session = get_session()
        try:
            db_card = get_entity_card_by_name(session, result.get('entity_name', ''))
            if db_card:
                print(f"✅ Entity card found in database: {db_card.entity_name}")
            else:
                print("❌ Entity card not found in database")
        except Exception as e:
            print(f"❌ Error retrieving from database: {e}")
        finally:
            session.close()
    else:
        print("❌ Failed to generate entity card")


def test_agent_directly():
    """Test the agent directly with sample data"""
    print("\nTesting Agent Directly...")
    
    try:
        from app.assistant.ServiceLocator.service_locator import DI
        from app.assistant.utils.pydantic_classes import Message
        
        # Create the agent
        agent = DI.agent_factory.create_agent('entity_card_generator')
        print(f"✅ Agent created: {agent.name}")
        
        # Test with sample data
        test_data = {
            "entity_info": {
                "label": "Test Person",
                "type": "person",
                "description": "A test person for testing",
                "aliases": ["Test", "TestPerson"]
            },
            "relationships": [
                {
                    "direction": "out",
                    "edge_type": "works_at",
                    "connected_node": {
                        "label": "Test Company",
                        "type": "company",
                        "description": "A test company"
                    }
                }
            ],
            "batch_number": 1,
            "total_batches": 1
        }
        
        message = Message(
            data_type="entity_card_generation",
            sender="Test",
            receiver="entity_card_generator",
            content="Generate entity card",
            agent_input=test_data
        )
        
        result = agent.action_handler(message)
        
        if result and result.data:
            print("✅ Agent generated entity card:")
            print(f"  Entity Name: {result.data.get('entity_name', 'N/A')}")
            print(f"  Entity Type: {result.data.get('entity_type', 'N/A')}")
            print(f"  Summary: {result.data.get('summary', 'N/A')[:100]}...")
        else:
            print("❌ Agent failed to generate entity card")
            
    except Exception as e:
        print(f"❌ Error testing agent: {e}")


def test_filtered_pipeline():
    """Test the filtered pipeline with different thresholds"""
    print("\nTesting Filtered Pipeline...")
    
    # Test with different minimum outgoing edge counts
    for min_edges in [1, 2, 3]:
        print(f"\nTesting with minimum {min_edges} outgoing edges:")
        try:
            result = run_entity_card_pipeline_with_filter(min_outgoing_edges=min_edges)
            print(f"  ✅ Processed: {result['processed']}, Errors: {result['errors']}")
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_importance_filtered_pipeline():
    """Test the importance filtered pipeline with different thresholds"""
    print("\nTesting Importance Filtered Pipeline...")
    
    # Test with different importance thresholds
    for min_importance in [0.1, 0.3, 0.5, 0.7]:
        print(f"\nTesting with minimum importance {min_importance}:")
        try:
            result = run_entity_card_pipeline_with_filters(min_outgoing_edges=1, min_importance=min_importance)
            print(f"  ✅ Processed: {result['processed']}, Errors: {result['errors']}")
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_combined_filters():
    """Test combining edge count and importance filters"""
    print("\nTesting Combined Filters...")
    
    # Test different combinations
    test_configs = [
        {"min_edges": 1, "min_importance": 0.3},
        {"min_edges": 2, "min_importance": 0.5},
        {"min_edges": 3, "min_importance": 0.7},
    ]
    
    for config in test_configs:
        print(f"\nTesting with {config['min_edges']}+ edges and importance >= {config['min_importance']}:")
        try:
            result = run_entity_card_pipeline_with_filters(
                min_outgoing_edges=config['min_edges'], 
                min_importance=config['min_importance']
            )
            print(f"  ✅ Processed: {result['processed']}, Errors: {result['errors']}")
        except Exception as e:
            print(f"  ❌ Error: {e}")


def test_full_pipeline():
    """Test the full pipeline (commented out for safety)"""
    print("\nTesting Full Pipeline...")
    print("⚠️  This would process ALL nodes with outgoing edges. Uncomment to run.")
    
    # Uncomment to run the full pipeline
    # result = run_entity_card_pipeline()
    # print(f"Pipeline result: {result}")


def test_prompt_injection_format():
    """Test the prompt injection formatting with original descriptions"""
    print("\nTesting Prompt Injection Format...")
    
    session = get_session()
    
    try:
        # Test with a known entity (if any exist)
        test_entities = ["Jukka", "Test Person", "Test Entity"]
        
        for entity_name in test_entities:
            formatted_card = get_entity_card_for_prompt_injection(session, entity_name)
            if formatted_card:
                print(f"✅ Prompt injection format for '{entity_name}':")
                print(f"  Length: {len(formatted_card)} characters")
                print(f"  Preview: {formatted_card[:200]}...")
                print()
                break
        else:
            print("⚠️  No entity cards found to test prompt injection format")
            
    except Exception as e:
        print(f"❌ Error testing prompt injection format: {e}")
    finally:
        session.close()


def test_original_data_storage():
    """Test that original KG data is properly stored"""
    print("\nTesting Original Data Storage...")
    
    session = get_session()
    
    try:
        # Get a sample entity card
        entity_cards = session.query(EntityCard).limit(1).all()
        
        if entity_cards:
            card = entity_cards[0]
            print(f"✅ Entity card '{card.entity_name}' original data:")
            print(f"  Original description: {card.original_description is not None}")
            print(f"  Original aliases: {len(card.original_aliases or [])} aliases")
            print(f"  Processed aliases: {len(card.aliases or [])} aliases")
            
            if card.original_description:
                print(f"  Description preview: {card.original_description[:100]}...")
            
            if card.original_aliases:
                print(f"  Original aliases: {', '.join(card.original_aliases)}")
        else:
            print("⚠️  No entity cards found to test original data storage")
            
    except Exception as e:
        print(f"❌ Error testing original data storage: {e}")
    finally:
        session.close()


def main():
    """Main test function"""
    print("=== Simple Entity Card Pipeline Test ===\n")
    
    # Test 1: Pipeline statistics
    test_pipeline_stats()
    
    # Test 2: Importance statistics
    test_importance_stats()
    
    # Test 3: Database statistics
    test_database_stats()
    
    # Test 4: Database operations
    test_database_operations()
    
    # Test 5: Agent directly
    test_agent_directly()
    
    # Test 6: Single node processing
    test_single_node()
    
    # Test 7: Edge count filtered pipeline
    test_filtered_pipeline()
    
    # Test 8: Importance filtered pipeline
    test_importance_filtered_pipeline()
    
    # Test 9: Combined filters
    test_combined_filters()
    
    # Test 10: Full pipeline (commented out)
    test_full_pipeline()
    
    # Test 11: Prompt injection format
    test_prompt_injection_format()

    # Test 12: Original data storage
    test_original_data_storage()
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()
