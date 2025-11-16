#!/usr/bin/env python3
"""
Simple Data Loader for KG Pipeline V2

Load conversation data into the pipeline for processing.
Run this file directly from IDE.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineChunk

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_conversation_data(batch_name: str, conversation_count: int) -> int:
    """
    Load conversation data into the pipeline
    
    Args:
        batch_name: Name for this batch of data
        conversation_count: Number of conversation messages to process
        
    Returns:
        Batch ID of the created batch
    """
    try:
        logger.info(f"📥 Loading conversation data into pipeline...")
        logger.info(f"   Batch name: {batch_name}")
        logger.info(f"   Conversation count: {conversation_count}")
        
        session: Session = get_session()
        coordinator = PipelineCoordinator(session)
        
        # Create batch
        batch = coordinator.create_batch(batch_name)
        logger.info(f"✅ Created batch: {batch.id}")
        
        # Load data from processed_entity_log (entity-resolved sentences)
        # This is the same data source as the original kg_pipeline
        from app.assistant.kg_core.log_preprocessing import read_unprocessed_logs_from_processed_entity_log
        
        logger.info("📖 Loading data from processed_entity_log...")
        log_entries = read_unprocessed_logs_from_processed_entity_log(
            batch_size=conversation_count,
            source_filter=None,  # No source filter for now
            role_filter=["user", "assistant"]  # Only process user and assistant messages
        )
        
        if not log_entries:
            logger.warning("⚠️ No unprocessed logs found in processed_entity_log database")
            logger.info("💡 Make sure you have unprocessed logs in the processed_entity_log table")
            exit(1)
        
        logger.info(f"📊 Found {len(log_entries)} unprocessed log entries")
        
        # Convert log entries to pipeline nodes
        node_count = 0
        for i, log_entry in enumerate(log_entries):
            # Create a pipeline node for each log entry
            node_data = {
                'id': f"node_{batch.id}_{i}",
                'label': log_entry.get('message', '')[:100],  # Truncate long messages
                'node_type': 'Entity',  # Default type
                'original_message_id': log_entry.get('id'),
                'original_sentence': log_entry.get('message', ''),
                'source': log_entry.get('source', 'unknown'),
                'role': log_entry.get('role', 'unknown'),
                'timestamp': log_entry.get('timestamp'),
                'batch_id': batch.id
            }
            
            # Save node to database
            coordinator.save_node_data(node_data)
            node_count += 1
            
            if i % 10 == 0:  # Progress update every 10 nodes
                logger.info(f"   Processed {i+1}/{len(log_entries)} log entries...")
        
        # Update batch status
        coordinator.update_batch_status(batch.id, 'loaded')
        
        logger.info(f"✅ Data loading completed!")
        logger.info(f"   Batch ID: {batch.id}")
        logger.info(f"   Nodes loaded: {node_count}")
        logger.info(f"   Status: {batch.status}")
        
        return batch.id
        
    except Exception as e:
        logger.error(f"❌ Error loading data: {str(e)}")
        exit(1)
    
    finally:
        session.close()


if __name__ == '__main__':
    """
    Run this file directly from IDE to load data into the pipeline
    """
    print("📥 KG Pipeline V2 - Load Data")
    print("=" * 50)
    
    # Get batch name
    batch_name = input("Enter batch name: ").strip()
    if not batch_name:
        print("❌ Batch name is required")
        exit(1)
    
    # Get conversation count
    conversation_count_input = input("Enter number of conversation messages to process: ").strip()
    if not conversation_count_input:
        print("❌ Conversation count is required")
        exit(1)
    
    try:
        conversation_count = int(conversation_count_input)
    except ValueError:
        print("❌ Conversation count must be a number")
        exit(1)
    
    print(f"\n🔄 Loading data...")
    print(f"   Batch name: {batch_name}")
    print(f"   Conversation count: {conversation_count}")
    
    try:
        batch_id = load_conversation_data(batch_name, conversation_count)
        print(f"✅ Data loaded successfully!")
        print(f"   Batch ID: {batch_id}")
        print(f"   Check status: Run check_pipeline_status.py")
        
    except Exception as e:
        print(f"❌ Error loading data: {str(e)}")
        exit(1)
