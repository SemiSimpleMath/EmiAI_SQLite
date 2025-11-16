#!/usr/bin/env python3
"""
Data Loader for KG Pipeline V2

Load data from the current pipeline format into the V2 database:
python load_data.py --batch-name "test_batch" --limit 100
"""

import argparse
import logging
from typing import List, Dict, Any

from app.models.base import get_session
from app.assistant.kg_core.log_preprocessing import read_unprocessed_logs_from_processed_entity_log
from .pipeline_coordinator import PipelineCoordinator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_conversation_data(batch_name: str, limit: int = None) -> int:
    """Load conversation data from the current pipeline into V2 format"""
    
    session = get_session()
    coordinator = PipelineCoordinator(session)
    
    try:
        # Create a new batch
        batch = coordinator.create_batch(batch_name, {
            'source': 'conversation_logs',
            'limit': limit
        })
        
        logger.info(f"📦 Created batch {batch.id}: {batch_name}")
        
        # Load unprocessed logs
        log_context_items = read_unprocessed_logs_from_processed_entity_log(limit=limit)
        
        logger.info(f"📥 Loaded {len(log_context_items)} conversation items")
        
        # Process each conversation
        nodes_created = 0
        edges_created = 0
        
        for item in log_context_items:
            try:
                # Extract conversation data
                conversation_text = item.get('conversation_text', '')
                block_ids = item.get('block_ids', [])
                data_source = item.get('data_source', 'unknown')
                timestamp_str = item.get('original_message_timestamp_str')
                
                # Create a node for this conversation
                node_data = {
                    'label': f"conversation_{len(block_ids)}_messages",
                    'node_type': 'Event',  # Conversations are events
                    'original_sentence': conversation_text,
                    'conversation_id': f"conv_{len(block_ids)}",
                    'message_id': block_ids[0] if block_ids else None,
                    'data_source': data_source,
                    'original_timestamp': timestamp_str
                }
                
                # Add node to batch
                node = coordinator.add_node_to_batch(batch.id, node_data)
                nodes_created += 1
                
                # Create edges between messages in the conversation
                for i in range(len(block_ids) - 1):
                    edge_data = {
                        'source_node_id': node.id,
                        'target_node_id': node.id,  # Self-reference for now
                        'edge_type': 'message_sequence',
                        'original_sentence': f"Message {i+1} -> Message {i+2}",
                        'conversation_id': f"conv_{len(block_ids)}",
                        'message_id': block_ids[i]
                    }
                    
                    edge = coordinator.add_edge_to_batch(batch.id, edge_data)
                    edges_created += 1
                
                if nodes_created % 10 == 0:
                    logger.info(f"📊 Created {nodes_created} nodes, {edges_created} edges")
                    
            except Exception as e:
                logger.error(f"❌ Failed to process conversation item: {str(e)}")
                continue
        
        # Update batch totals
        batch.total_nodes = nodes_created
        session.commit()
        
        logger.info(f"✅ Data loading completed:")
        logger.info(f"   Batch ID: {batch.id}")
        logger.info(f"   Nodes created: {nodes_created}")
        logger.info(f"   Edges created: {edges_created}")
        
        return batch.id
        
    except Exception as e:
        logger.error(f"💥 Data loading failed: {str(e)}")
        raise
    
    finally:
        session.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Load data into KG Pipeline V2')
    parser.add_argument('--batch-name', required=True, help='Name for the batch')
    parser.add_argument('--limit', type=int, help='Limit number of conversations to load')
    
    args = parser.parse_args()
    
    # Load data
    batch_id = load_conversation_data(
        batch_name=args.batch_name,
        limit=args.limit
    )
    
    print(f"✅ Data loaded successfully into batch {batch_id}")
    print(f"   Run: python check_pipeline_status.py --batch-id {batch_id}")


if __name__ == '__main__':
    main()
