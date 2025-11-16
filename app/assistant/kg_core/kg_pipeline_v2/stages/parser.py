"""
Parser Stage Processor

Processes conversation data to parse entities and relationships using the parser agent.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineChunk, ParserResult, StageResult, StageCompletion
)
from app.assistant.kg_core.kg_pipeline_v2.utils import wait_for_stage_data

logger = logging.getLogger(__name__)


class ParserProcessor:
    """Processes parser stage"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        self.agent = DI.agent_factory.create_agent("knowledge_graph_add::parser")
    
    def wait_for_data(self, batch_id: int = None, max_wait_time: int = 300) -> bool:
        """
        Wait for conversation boundary results to become available for parsing
        Reads from stage_results where stage_name = 'conversation_boundary'
        
        Args:
            batch_id: Specific batch ID to wait for (None for any batch)
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if data became available, False if timeout
        """
        logger.info(f"🔄 Parser waiting for conversation boundary results...")
        
        # Check if there are conversation boundary results available
        boundary_results = self.session.query(StageResult).filter(
            StageResult.stage_name == 'conversation_boundary'
        ).all()
        
        if boundary_results:
            logger.info(f"✅ Found {len(boundary_results)} conversation boundary results")
            return True
        else:
            logger.warning("⚠️ No conversation boundary results found")
            return False
    
    async def process(self, batch_size: int = 100) -> Dict[str, Any]:
        """
        Process conversation boundary results to extract atomic sentences
        
        Args:
            batch_size: Number of conversation chunks to process
            
        Returns:
            Dict containing processing results
        """
        try:
            # Read ONE unprocessed conversation boundary result from the waiting area
            logger.info(f"📖 Reading one chunk from conversation boundary waiting area...")
            
            # Get conversation boundary results that haven't been processed by parser stage yet
            # Use StageCompletion to track which chunks have been processed
            from sqlalchemy import select
            processed_chunk_ids = select(StageCompletion.chunk_id).filter(
                StageCompletion.stage_name == 'parser',
                StageCompletion.status == 'completed'
            ).scalar_subquery()
            
            boundary_result = self.session.query(StageResult).filter(
                StageResult.stage_name == 'conversation_boundary',
                ~StageResult.chunk_id.in_(processed_chunk_ids)
            ).first()
            
            if not boundary_result:
                logger.warning("⚠️ No unprocessed conversation boundary chunks available in waiting area")
                return {"processed_count": 0, "message": "No chunks to process"}
            
            boundary_results = [boundary_result]  # Process one chunk at a time
            
            logger.info(f"📊 Found {len(boundary_results)} conversation boundary results")
            
            # Process each conversation boundary result
            processed_count = 0
            parsed_sentences = []  # Store parsed sentences for fact extraction stage
            
            for i, boundary_result in enumerate(boundary_results):
                try:
                    # Extract conversation chunks from boundary result
                    result_data = boundary_result.result_data
                    conversation_chunks = result_data.get('conversation_chunks', [])
                    
                    logger.info(f"🔍 Processing conversation boundary result {i+1}/{len(boundary_results)} with {len(conversation_chunks)} chunks")
                    
                    # Process each conversation chunk
                    for chunk_idx, chunk in enumerate(conversation_chunks):
                        boundary_messages = chunk.get('boundary_messages', [])
                        message_bounds = chunk.get('message_bounds', [])
                        
                        # Extract timestamp from the first message (original message timestamp)
                        original_message_timestamp = None
                        if boundary_messages:
                            first_msg = boundary_messages[0]
                            original_message_timestamp = first_msg.get('timestamp')
                        
                        # Extract conversation text from boundary messages
                        conversation_text = ""
                        for msg in boundary_messages:
                            if msg.get('role') == 'user':
                                conversation_text += f"User: {msg.get('message', '')}\n"
                            elif msg.get('role') == 'assistant':
                                conversation_text += f"Assistant: {msg.get('message', '')}\n"
                        
                        if not conversation_text.strip():
                            logger.warning(f"Skipping empty conversation chunk {chunk_idx}")
                            continue
                        
                        # Call parser agent to extract atomic sentences
                        logger.info(f"🔍 Parsing conversation chunk {chunk_idx+1}: {conversation_text[:100]}...")
                        parser_input = {"text": conversation_text}
                        result = self.agent.action_handler(Message(agent_input=parser_input))
                        
                        # Parse agent response
                        if result and hasattr(result, 'data') and result.data:
                            parsed_sentences_data = result.data
                        else:
                            parsed_sentences_data = str(result)
                        
                        # Store parsed sentences for this chunk with timestamp
                        parsed_sentences.append({
                            'chunk_index': chunk_idx,
                            'conversation_text': conversation_text,
                            'parsed_sentences': parsed_sentences_data,
                            'original_message_timestamp': original_message_timestamp,  # Preserve timestamp
                            'boundary_result_id': str(boundary_result.chunk_id)  # Convert UUID to string
                        })
                        
                        processed_count += 1
                        logger.info(f"✅ Parsed chunk {chunk_idx+1}")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing conversation boundary result {i+1}: {e}")
                    continue
            
            # Store all parsed sentences for fact extraction stage
            if parsed_sentences:
                import uuid
                from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineBatch, PipelineChunk
                
                # Create a batch for parser results
                parser_batch = PipelineBatch(
                    batch_name="Parser Results",
                    status="processing"
                )
                self.session.add(parser_batch)
                self.session.flush()
                
                # Create a parser result chunk
                parser_chunk_id = str(uuid.uuid4())
                parser_chunk = PipelineChunk(
                    id=parser_chunk_id,
                    batch_id=parser_batch.id,
                    label="Parser Results",
                    node_type="ParserResult",
                    original_sentence=f"Parsed {processed_count} conversation chunks into atomic sentences"
                )
                
                self.session.add(parser_chunk)
                self.session.flush()
                
                # Save the stage result
                self.coordinator.save_stage_result(
                    parser_chunk_id,
                    'parser',
                    {
                        'parsed_sentences': parsed_sentences,
                        'processed_count': processed_count,
                        'stage': 'parser'
                    }
                )
                
                logger.info(f"📊 Stored {len(parsed_sentences)} parsed sentence chunks for fact extraction stage")
                logger.info(f"   Parser chunk ID: {parser_chunk_id}")
            
            # Mark the chunk as processed using StageCompletion
            from datetime import datetime
            stage_completion = StageCompletion(
                chunk_id=boundary_result.chunk_id,
                stage_name='parser',
                status='completed',
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            self.session.add(stage_completion)
            self.session.commit()
            
            logger.info(f"✅ Parser processing completed and marked as processed: {processed_count} chunks processed")
            
            return {
                "processed_count": processed_count,
                "total_chunks": len(parsed_sentences),
                "message": f"Processed {processed_count} conversation chunks successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Error in parser processing: {e}")
            raise


if __name__ == '__main__':
    """
    Run parser stage continuously with wait state
    """
    import app.assistant.tests.test_setup
    import asyncio
    import time
    from app.models.base import get_session
    from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
    
    async def run_parser_continuously():
        print("🚀 Starting Parser Stage (Stage 1)")
        print("=" * 50)
        print("📋 Mode: Continuous processing with wait state")
        print("⏹️  Press Ctrl+C to stop")
        print("=" * 50)
        
        session = get_session()
        coordinator = PipelineCoordinator(session)
        processor = ParserProcessor(coordinator, session)
        
        total_processed = 0
        chunk_count = 0
        wait_interval = 60  # Check every 60 seconds when waiting
        
        try:
            while True:
                chunk_count += 1
                print(f"\n🔄 Chunk {chunk_count}: Checking for unprocessed conversation boundaries...")
                
                # Check if data is available
                data_available = processor.wait_for_data(batch_id=None, max_wait_time=5)
                
                if not data_available:
                    print(f"⏸️  No data available. Waiting {wait_interval} seconds for conversation boundary stage...")
                    print(f"📊 Total processed so far: {total_processed} chunks")
                    time.sleep(wait_interval)
                    continue
                
                # Process the chunk
                print(f"📖 Processing chunk {chunk_count}...")
                result = await processor.process(batch_size=10)
                
                processed_count = result.get('processed_count', 0)
                total_processed += processed_count
                
                if processed_count > 0:
                    print(f"✅ Chunk {chunk_count} completed: {processed_count} conversations parsed")
                    print(f"📊 Total so far: {total_processed} chunks")
                else:
                    print(f"⏸️  No chunks processed. Waiting {wait_interval} seconds...")
                    time.sleep(wait_interval)
                    
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped by user (Ctrl+C)")
            print(f"📊 Processed {total_processed} chunks in {chunk_count} iterations before stopping")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()
            print("\n✅ Session closed")
    
    asyncio.run(run_parser_continuously())
