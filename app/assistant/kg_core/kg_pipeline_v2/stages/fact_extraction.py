"""
Fact Extraction Stage Processor

Processes conversation data to extract facts using the fact_extractor agent.

NOTE: This stage uses V1's battle-tested helper functions to ensure feature parity.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineChunk, FactExtractionResult, StageResult, StageCompletion
)
from app.assistant.kg_core.kg_pipeline_v2.utils import wait_for_stage_data

# Import V1 helper functions for feature parity
from app.assistant.kg_core.kg_pipeline import extract_facts_from_sentences

logger = logging.getLogger(__name__)

# Track fact extractor calls for debugging (V1 feature)
_fact_extractor_call_count = 0


class FactExtractionProcessor:
    """Processes fact extraction stage"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        self.agent = DI.agent_factory.create_agent("knowledge_graph_add::fact_extractor")
    
    def wait_for_data(self, batch_id: int = None, max_wait_time: int = 300) -> bool:
        """
        Wait for parser results to become available for fact extraction
        Reads from stage_results where stage_name = 'parser'
        
        Args:
            batch_id: Specific batch ID to wait for (None for any batch)
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if data became available, False if timeout
        """
        logger.info(f"🔄 Fact extraction waiting for parser results...")
        
        # Check if there are parser results available
        parser_results = self.session.query(StageResult).filter(
            StageResult.stage_name == 'parser'
        ).all()
        
        if parser_results:
            logger.info(f"✅ Found {len(parser_results)} parser results")
            return True
        else:
            logger.warning("⚠️ No parser results found")
            return False
    
    async def process(self, batch_size: int = 100) -> Dict[str, Any]:
        """
        Process parser results to extract facts from atomic sentences
        
        Uses V1 helper function:
        - extract_facts_from_sentences(): Extract facts with proper timestamp and core->category mapping
        
        Args:
            batch_size: Number of parsed sentences to process
            
        Returns:
            Dict containing processing results
        """
        global _fact_extractor_call_count
        
        try:
            # Read ONE unprocessed parser result from the waiting area
            logger.info(f"📖 Reading one chunk from parser waiting area...")
            
            # Get parser results that haven't been processed by fact extraction stage yet
            # Use StageCompletion to track which chunks have been processed
            from sqlalchemy import select
            processed_chunk_ids = select(StageCompletion.chunk_id).filter(
                StageCompletion.stage_name == 'fact_extraction',
                StageCompletion.status == 'completed'
            ).scalar_subquery()
            
            parser_result = self.session.query(StageResult).filter(
                StageResult.stage_name == 'parser',
                ~StageResult.chunk_id.in_(processed_chunk_ids)
            ).first()
            
            if not parser_result:
                logger.warning("⚠️ No unprocessed parser chunks available in waiting area")
                return {"processed_count": 0, "message": "No chunks to process"}
            
            parser_results = [parser_result]  # Process one chunk at a time
            
            logger.info(f"📊 Found {len(parser_results)} parser results")
            
            # Process each parser result
            processed_count = 0
            extracted_facts = []  # Store extracted facts for metadata stage
            
            for i, parser_result in enumerate(parser_results):
                try:
                    # Extract parsed sentences from parser result
                    result_data = parser_result.result_data
                    parsed_sentences = result_data.get('parsed_sentences', [])
                    
                    logger.info(f"🔍 Processing parser result {i+1}/{len(parser_results)} with {len(parsed_sentences)} conversation entries")
                    
                    # V1 FEATURE: Process each conversation entry separately (from parser stage)
                    for sentence_idx, sentence_data in enumerate(parsed_sentences):
                        # V1 FORMAT: Parser now provides atomic_sentences and metadata directly
                        atomic_sentences = sentence_data.get('atomic_sentences', [])
                        conversation_text = sentence_data.get('conversation_text', '')
                        original_message_timestamp = sentence_data.get('original_message_timestamp')
                        block_ids = sentence_data.get('block_ids', [])
                        data_source = sentence_data.get('data_source', 'unknown')
                        
                        if not atomic_sentences:
                            logger.warning(f"⚠️ No atomic sentences in entry {sentence_idx+1}, skipping")
                            continue
                        
                        # V1 FUNCTION: Extract facts using V1 helper
                        _fact_extractor_call_count += 1
                        logger.info(f"🔍 Extracting facts from {len(atomic_sentences)} sentences (call #{_fact_extractor_call_count})...")
                        
                        facts_result = extract_facts_from_sentences(
                            atomic_sentences=atomic_sentences,
                            fact_extractor_agent=self.agent,
                            conversation_text=conversation_text,
                            original_message_timestamp_str=original_message_timestamp,
                            fact_extractor_call_count=_fact_extractor_call_count
                        )
                        
                        nodes = facts_result.get("original_nodes", [])
                        edges = facts_result.get("original_edges", [])
                        
                        logger.info(f"📊 Extracted {len(nodes)} nodes and {len(edges)} edges")
                        
                        # Store extracted facts with V1 metadata
                        extracted_facts.append({
                            'sentence_index': sentence_idx,
                            'atomic_sentences': atomic_sentences,
                            'conversation_text': conversation_text,
                            'extracted_facts': {
                                'nodes': nodes,
                                'edges': edges
                            },
                            'block_ids': block_ids,  # V1 FEATURE: Track message IDs
                            'data_source': data_source,  # V1 FEATURE: Track data source
                            'original_message_timestamp': original_message_timestamp,
                            'parser_result_id': str(parser_result.chunk_id)
                        })
                        
                        processed_count += len(atomic_sentences)
                        logger.info(f"✅ Extracted facts from entry {sentence_idx+1}: {len(nodes)} nodes, {len(edges)} edges")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing parser result {i+1}: {e}")
                    continue
            
            # Store all extracted facts for metadata stage
            if extracted_facts:
                import uuid
                from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineBatch, PipelineChunk
                
                # Create a batch for fact extraction results
                fact_batch = PipelineBatch(
                    batch_name="Fact Extraction Results",
                    status="processing"
                )
                self.session.add(fact_batch)
                self.session.flush()
                
                # Create a fact extraction result chunk
                fact_chunk_id = str(uuid.uuid4())
                fact_chunk = PipelineChunk(
                    id=fact_chunk_id,
                    batch_id=fact_batch.id,
                    label="Fact Extraction Results",
                    node_type="FactExtractionResult",
                    original_sentence=f"Extracted facts from {processed_count} atomic sentences"
                )
                
                self.session.add(fact_chunk)
                self.session.flush()
                
                # DEBUG: Show exactly what we're saving to the database
                import json
                print(f"\n{'='*80}")
                print(f"🔍 FACT EXTRACTION DEBUG: SAVING TO DATABASE")
                print(f"{'='*80}")
                print(f"Total extracted_facts entries: {len(extracted_facts)}")
                if extracted_facts:
                    print(f"\nFirst extracted_facts entry:")
                    first_fact = extracted_facts[0]
                    print(json.dumps(first_fact, indent=2, default=str))
                    if 'extracted_facts' in first_fact and 'nodes' in first_fact['extracted_facts']:
                        nodes = first_fact['extracted_facts']['nodes']
                        if nodes:
                            print(f"\nFirst node from first fact:")
                            print(json.dumps(nodes[0], indent=2, default=str))
                print(f"{'='*80}\n")
                
                # Save the stage result
                self.coordinator.save_stage_result(
                    fact_chunk_id,
                    'fact_extraction',
                    {
                        'extracted_facts': extracted_facts,
                        'processed_count': processed_count,
                        'stage': 'fact_extraction'
                    }
                )
                
                logger.info(f"📊 Stored {len(extracted_facts)} extracted facts for metadata stage")
                logger.info(f"   Fact extraction chunk ID: {fact_chunk_id}")
            
            # Mark the chunk as processed using StageCompletion
            from datetime import datetime
            stage_completion = StageCompletion(
                chunk_id=parser_result.chunk_id,
                stage_name='fact_extraction',
                status='completed',
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            self.session.add(stage_completion)
            self.session.commit()
            
            logger.info(f"✅ Fact extraction processing completed and marked as processed: {processed_count} facts extracted")
            
            return {
                "processed_count": processed_count,
                "total_facts": len(extracted_facts),
                "message": f"Extracted {processed_count} facts successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Error in fact extraction processing: {e}")
            raise


if __name__ == '__main__':
    """
    Run fact extraction stage continuously with wait state
    """
    import app.assistant.tests.test_setup
    import asyncio
    import time
    from app.models.base import get_session
    from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
    
    async def run_fact_extraction_continuously():
        print("🚀 Starting Fact Extraction Stage (Stage 2)")
        print("=" * 50)
        print("📋 Mode: Continuous processing with wait state")
        print("⏹️  Press Ctrl+C to stop")
        print("=" * 50)
        
        session = get_session()
        coordinator = PipelineCoordinator(session)
        processor = FactExtractionProcessor(coordinator, session)
        
        total_processed = 0
        chunk_count = 0
        wait_interval = 60  # Check every 60 seconds when waiting
        
        try:
            while True:
                chunk_count += 1
                print(f"\n🔄 Chunk {chunk_count}: Checking for parsed sentences...")
                
                # Check if data is available
                data_available = processor.wait_for_data(batch_id=None, max_wait_time=5)
                
                if not data_available:
                    print(f"⏸️  No data available. Waiting {wait_interval} seconds for parser stage...")
                    print(f"📊 Total processed so far: {total_processed} facts")
                    time.sleep(wait_interval)
                    continue
                
                # Process the chunk
                print(f"📖 Processing chunk {chunk_count}...")
                result = await processor.process(batch_size=10)
                
                processed_count = result.get('processed_count', 0)
                total_processed += processed_count
                
                if processed_count > 0:
                    print(f"✅ Chunk {chunk_count} completed: {processed_count} facts extracted")
                    print(f"📊 Total so far: {total_processed} facts")
                else:
                    print(f"⏸️  No facts extracted. Waiting {wait_interval} seconds...")
                    time.sleep(wait_interval)
                    
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped by user (Ctrl+C)")
            print(f"📊 Processed {total_processed} facts in {chunk_count} iterations before stopping")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()
            print("\n✅ Session closed")
    
    asyncio.run(run_fact_extraction_continuously())
