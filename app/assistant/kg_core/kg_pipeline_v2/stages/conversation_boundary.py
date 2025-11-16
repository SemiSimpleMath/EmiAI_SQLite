"""
Conversation Boundary Stage Processor

Processes input sentences to identify conversation boundaries using the conversation_boundary agent.
This is stage 0 - the first stage that parses input sentences.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineChunk, StageResult, StageCompletion
)

logger = logging.getLogger(__name__)


class ConversationBoundaryProcessor:
    """Processes conversation boundary stage (stage 0)"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        self.agent = DI.agent_factory.create_agent("knowledge_graph_add::conversation_boundary")
    
    def wait_for_data(self, batch_id: int = None, max_wait_time: int = 300) -> bool:
        """
        Wait for data to become available for conversation boundary processing
        Reads directly from processed_entity_log (the "waiting area" for stage 0)
        
        Args:
            batch_id: Specific batch ID to wait for (None for any batch)
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if data became available, False if timeout
        """
        logger.info(f"🔄 Conversation boundary waiting for data from processed_entity_log...")
        
        # Import here to avoid circular imports
        from app.assistant.kg_core.log_preprocessing import read_unprocessed_logs_from_processed_entity_log
        
        # Check if there are unprocessed logs in processed_entity_log
        log_entries = read_unprocessed_logs_from_processed_entity_log(
            batch_size=1,  # Just check if any exist
            source_filter=None,
            role_filter=["user", "assistant"]
        )
        
        if log_entries:
            logger.info(f"✅ Found {len(log_entries)} unprocessed logs in processed_entity_log")
            return True
        else:
            logger.warning("⚠️ No unprocessed logs found in processed_entity_log")
            return False
    
    async def process(self, batch_size: int = 100) -> Dict[str, Any]:
        """
        Process conversation boundary detection for unprocessed logs from processed_entity_log
        
        Args:
            batch_size: Number of logs to process in this batch
            
        Returns:
            Dict containing processing results
        """
        try:
            # Import here to avoid circular imports
            from app.assistant.kg_core.log_preprocessing import read_unprocessed_logs_from_processed_entity_log
            
            # Read unprocessed logs from processed_entity_log
            logger.info(f"📖 Reading {batch_size} unprocessed logs from processed_entity_log...")
            log_entries = read_unprocessed_logs_from_processed_entity_log(
                batch_size=batch_size,
                source_filter=None,
                role_filter=["user", "assistant"]
            )
            
            if not log_entries:
                logger.warning("⚠️ No unprocessed logs found in processed_entity_log")
                return {"processed_count": 0, "message": "No data to process"}
            
            logger.info(f"📊 Found {len(log_entries)} unprocessed log entries")
            
            # Process logs in batches (similar to original pipeline)
            # The conversation boundary stage processes messages to find conversation chunks
            # These chunks are then passed to the parser stage for atomic sentence extraction
            
            processed_count = 0
            conversation_chunks = []  # Store conversation chunks for parser stage
            
            # Convert log entries to boundary_messages format (like original pipeline)
            boundary_messages = []
            for i, log_entry in enumerate(log_entries):
                # Convert datetime to string for JSON serialization
                timestamp = log_entry.get("timestamp")
                if timestamp and hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                elif timestamp:
                    timestamp = str(timestamp)
                else:
                    timestamp = None
                
                boundary_messages.append({
                    "id": f"msg_{i}",
                    "role": log_entry.get("role", "unknown"),
                    "message": log_entry.get("message", "").strip(),
                    "timestamp": timestamp
                })
            
            if not boundary_messages:
                logger.warning("⚠️ No valid messages to process")
                return {"processed_count": 0, "message": "No valid messages to process"}
            
            try:
                # Call conversation boundary agent with messages list (like original pipeline)
                logger.info(f"🔍 Processing {len(boundary_messages)} messages for conversation boundaries...")
                boundary_input = {
                    "messages": boundary_messages,
                    "analysis_window_size": len(boundary_messages)
                }
                boundary_result = self.agent.action_handler(Message(agent_input=boundary_input)).data or {}
                message_bounds = boundary_result.get("message_bounds", [])
                
                logger.info(f"📊 Found {len(message_bounds)} message bounds")
                
                # Store conversation boundary results for parser stage
                conversation_chunks.append({
                    'boundary_messages': boundary_messages,
                    'message_bounds': message_bounds,
                    'boundary_result': boundary_result,
                    'processed_count': len(boundary_messages)
                })
                
                processed_count = len(boundary_messages)
                logger.info(f"✅ Processed {processed_count} messages for conversation boundaries")
                
            except Exception as e:
                logger.error(f"❌ Error processing conversation boundaries: {e}")
                raise
            
            # Store conversation boundary results for the parser stage to consume
            # The parser stage will read these boundaries and extract atomic sentences
            if conversation_chunks:
                import uuid
                from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineChunk
                
                # Create a batch first, then create the boundary chunk
                from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineBatch
                
                # Create a batch for conversation boundary results
                boundary_batch = PipelineBatch(
                    batch_name="Conversation Boundary Results",
                    status="processing"
                )
                self.session.add(boundary_batch)
                self.session.flush()  # Ensure the batch is saved
                
                # Create a temporary "conversation boundary" chunk to store results
                boundary_chunk_id = str(uuid.uuid4())
                boundary_chunk = PipelineChunk(
                    id=boundary_chunk_id,
                    batch_id=boundary_batch.id,  # Use the actual batch ID
                    label="Conversation Boundary Results",
                    node_type="ConversationBoundary",
                    original_sentence=f"Processed {processed_count} messages into {len(conversation_chunks)} conversation chunks"
                )
                
                self.session.add(boundary_chunk)
                self.session.flush()  # Ensure the chunk is saved
                
                # Now save the stage result with the valid chunk_id
                self.coordinator.save_stage_result(
                    boundary_chunk_id,
                    'conversation_boundary',
                    {
                        'conversation_chunks': conversation_chunks,
                        'processed_count': processed_count,
                        'stage': 'conversation_boundary'
                    }
                )
                
                logger.info(f"📊 Stored {len(conversation_chunks)} conversation chunks for parser stage")
                logger.info(f"   Boundary chunk ID: {boundary_chunk_id}")
            
            # Mark the logs as processed in processed_entity_log
            from app.assistant.kg_core.log_preprocessing import mark_processed_entity_logs_as_processed
            log_ids = [log_entry.get("id") for log_entry in log_entries]
            mark_processed_entity_logs_as_processed(log_ids)
            logger.info(f"✅ Marked {len(log_ids)} logs as processed in processed_entity_log")
            
            logger.info(f"✅ Conversation boundary processing completed: {processed_count}/{len(log_entries)} logs processed")
            
            return {
                "processed_count": processed_count,
                "total_logs": len(log_entries),
                "message": f"Processed {processed_count} logs successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Error in conversation boundary processing: {e}")
            raise


if __name__ == '__main__':
    """
    Run conversation boundary stage continuously
    """
    import app.assistant.tests.test_setup
    import asyncio
    from app.models.base import get_session
    from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
    from app.assistant.kg_core.kg_pipeline_v2.utils import wait_for_stage_data
    
    async def run_conversation_boundary_continuously():
        print("🚀 Starting Conversation Boundary Stage (Stage 0)")
        print("=" * 50)
        print("📋 Mode: Continuous processing with wait state")
        print("⏹️  Press Ctrl+C to stop")
        print("=" * 50)
        
        session = get_session()
        coordinator = PipelineCoordinator(session)
        processor = ConversationBoundaryProcessor(coordinator, session)
        
        batch_size = 10  # Process 10 messages at a time
        total_processed = 0
        batch_count = 0
        wait_interval = 60  # Check every 60 seconds when waiting
        
        try:
            while True:
                batch_count += 1
                print(f"\n🔄 Batch {batch_count}: Checking for unprocessed logs...")
                
                # Check if data is available
                data_available = processor.wait_for_data(batch_id=None, max_wait_time=5)
                
                if not data_available:
                    print(f"⏸️  No unprocessed logs available. Waiting {wait_interval} seconds for new data...")
                    print(f"📊 Total processed so far: {total_processed} messages")
                    import time
                    time.sleep(wait_interval)
                    continue
                
                # Process the batch
                print(f"📖 Processing batch {batch_count} ({batch_size} messages)...")
                result = await processor.process(batch_size=batch_size)
                
                processed_count = result.get('processed_count', 0)
                total_processed += processed_count
                
                if processed_count > 0:
                    print(f"✅ Batch {batch_count} completed: {processed_count} messages processed")
                    print(f"📊 Total so far: {total_processed} messages")
                else:
                    print(f"⏸️  No messages processed. Waiting {wait_interval} seconds...")
                    import time
                    time.sleep(wait_interval)
                    
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped by user (Ctrl+C)")
            print(f"📊 Processed {total_processed} messages in {batch_count} batches before stopping")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()
            print("\n✅ Session closed")
    
    asyncio.run(run_conversation_boundary_continuously())
