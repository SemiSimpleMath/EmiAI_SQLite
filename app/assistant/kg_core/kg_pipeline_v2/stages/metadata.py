"""
Metadata Stage Processor

Processes fact extraction and parser results to add metadata using the meta_data_add agent.

NOTE: This stage uses V1's battle-tested helper functions to ensure feature parity.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineChunk, MetadataResult, StageResult, StageCompletion
)
from app.assistant.kg_core.kg_pipeline_v2.utils import wait_for_stage_data

# Import V1 helper functions for feature parity
from app.assistant.kg_core.kg_pipeline import add_metadata_to_nodes

logger = logging.getLogger(__name__)


class MetadataProcessor:
    """Processes metadata stage"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        self.agent = DI.agent_factory.create_agent("knowledge_graph_add::meta_data_add")
    
    def wait_for_data(self, batch_id: int = None, max_wait_time: int = 300) -> bool:
        """
        Wait for fact extraction results to become available for metadata processing
        Reads from stage_results where stage_name = 'fact_extraction'
        
        Args:
            batch_id: Specific batch ID to wait for (None for any batch)
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if data became available, False if timeout
        """
        logger.info(f"🔄 Metadata waiting for fact extraction results...")
        
        # Check if there are fact extraction results available
        fact_results = self.session.query(StageResult).filter(
            StageResult.stage_name == 'fact_extraction'
        ).all()
        
        if fact_results:
            logger.info(f"✅ Found {len(fact_results)} fact extraction results")
            return True
        else:
            logger.warning("⚠️ No fact extraction results found")
            return False
    
    async def process(self, batch_size: int = 100) -> Dict[str, Any]:
        """
        Process fact extraction results to add metadata
        
        Args:
            batch_size: Number of facts to process
            
        Returns:
            Dict containing processing results
        """
        try:
            # Read ONE unprocessed fact extraction result from the waiting area
            logger.info(f"📖 Reading one chunk from fact extraction waiting area...")
            
            # Get fact extraction results that haven't been processed by metadata stage yet
            # Use StageCompletion to track which chunks have been processed
            from sqlalchemy import select
            processed_chunk_ids = select(StageCompletion.chunk_id).filter(
                StageCompletion.stage_name == 'metadata',
                StageCompletion.status == 'completed'
            ).scalar_subquery()
            
            fact_result = self.session.query(StageResult).filter(
                StageResult.stage_name == 'fact_extraction',
                ~StageResult.chunk_id.in_(processed_chunk_ids)
            ).first()
            
            if not fact_result:
                logger.warning("⚠️ No unprocessed fact extraction chunks available in waiting area")
                return {"processed_count": 0, "message": "No chunks to process"}
            
            fact_results = [fact_result]  # Process one chunk at a time
            
            print(f"🔍 DEBUG: Found 1 unprocessed fact extraction result")
            
            logger.info(f"📊 Found {len(fact_results)} fact extraction results")
            print(f"🔍 DEBUG: Processing {len(fact_results)} fact extraction results")
            
            # Process each fact extraction result
            processed_count = 0
            metadata_results = []  # Store metadata for merge stage
            
            for i, fact_result in enumerate(fact_results):
                try:
                    # Extract facts from fact extraction result
                    result_data = fact_result.result_data
                    logger.info(f"🔍 DEBUG: Fact extraction result {i+1} data keys: {list(result_data.keys())}")
                    
                    extracted_facts = result_data.get('extracted_facts', [])
                    logger.info(f"🔍 Processing fact extraction result {i+1}/{len(fact_results)} with {len(extracted_facts)} facts")
                    
                    # If no extracted facts, skip this result
                    if not extracted_facts:
                        logger.warning(f"No extracted facts found in result {i+1}")
                        continue
                    
                    # Process each extracted fact
                    for fact_idx, fact_data in enumerate(extracted_facts):
                        # V1 FORMAT: Get conversation text and metadata from fact extraction
                        conversation_text = fact_data.get('conversation_text', '')
                        atomic_sentences = fact_data.get('atomic_sentences', [])
                        original_message_timestamp = fact_data.get('original_message_timestamp')
                        block_ids = fact_data.get('block_ids', [])  # V1 FEATURE
                        data_source = fact_data.get('data_source', 'unknown')  # V1 FEATURE
                        
                        # Fall back to joining atomic sentences if no conversation text
                        if not conversation_text and atomic_sentences:
                            conversation_text = ' '.join(atomic_sentences)
                        
                        extracted_facts_data = fact_data.get('extracted_facts', {})
                        
                        logger.info(f"📝 Fact {fact_idx+1}: conversation='{conversation_text[:50]}...'")
                        logger.info(f"📅 Original message timestamp: {original_message_timestamp}")
                        
                        if not conversation_text.strip():
                            logger.warning(f"Skipping empty conversation at fact {fact_idx+1}")
                            continue
                        
                        # Extract nodes and edges from the extracted facts data
                        nodes = extracted_facts_data.get('nodes', [])
                        edges = extracted_facts_data.get('edges', [])
                        
                        logger.info(f"🔍 Processing {len(nodes)} nodes from fact {fact_idx+1}")
                        
                        # Skip facts with no nodes
                        if not nodes:
                            logger.warning(f"⚠️ Skipping fact {fact_idx+1} - no nodes extracted")
                            continue
                        
                        # V1 FUNCTION: Add metadata to nodes one at a time with specific sentence context
                        logger.info(f"🔍 Adding metadata to {len(nodes)} nodes using V1 function...")
                        
                        metadata_result = add_metadata_to_nodes(
                            original_nodes=nodes,
                            original_edges=edges,
                            meta_data_agent=self.agent,
                            conversation_text=conversation_text,
                            original_message_timestamp_str=original_message_timestamp
                        )
                        
                        # V1 returns enriched_metadata as a dict keyed by temp_id
                        enriched_metadata = metadata_result.get("enriched_metadata", {})
                        logger.info(f"✅ Got metadata for {len(enriched_metadata)} nodes")
                        
                        # Merge enriched metadata back into nodes
                        enriched_nodes = []
                        for node in nodes:
                            temp_id = node.get("temp_id")
                            enriched_node = node.copy()
                            
                            if temp_id and temp_id in enriched_metadata:
                                # Merge metadata into node
                                enriched_node.update(enriched_metadata[temp_id])
                                logger.info(f"✅ Merged metadata for {node.get('label', 'unknown')}")
                            else:
                                logger.warning(f"⚠️ No metadata for {node.get('label', 'unknown')}, keeping original")
                            
                            # V1 FEATURE: Clear temporal fields for Entity and Concept nodes
                            node_type = enriched_node.get('node_type', '')
                            if node_type in ['Entity', 'Concept']:
                                enriched_node['valid_during'] = None
                                enriched_node['start_date'] = None
                                enriched_node['end_date'] = None
                                enriched_node['start_date_confidence'] = None
                                enriched_node['end_date_confidence'] = None
                            
                            # V1 FEATURE: Rename 'core' to 'category'
                            if 'core' in enriched_node:
                                enriched_node['category'] = enriched_node.pop('core')
                            
                            enriched_nodes.append(enriched_node)
                        
                        logger.info(f"✅ Enriched {len(enriched_nodes)} nodes from fact {fact_idx+1}")
                        
                        # Store metadata for this fact with V1 metadata
                        metadata_results.append({
                            'fact_index': fact_idx,
                            'conversation_text': conversation_text,
                            'nodes': enriched_nodes,
                            'edges': edges,
                            'block_ids': block_ids,  # V1 FEATURE
                            'data_source': data_source,  # V1 FEATURE
                            'original_message_timestamp': original_message_timestamp,  # V1 FEATURE
                            'fact_result_id': str(fact_result.chunk_id)
                        })
                        
                        processed_count += len(nodes)
                        logger.info(f"✅ Added metadata to {len(nodes)} nodes from fact {fact_idx+1}")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing fact extraction result {i+1}: {e}")
                    continue
            
            # Store all metadata for merge stage
            if metadata_results:
                import uuid
                from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineBatch, PipelineChunk
                
                # Create a batch for metadata results
                metadata_batch = PipelineBatch(
                    batch_name="Metadata Results",
                    status="processing"
                )
                self.session.add(metadata_batch)
                self.session.flush()
                
                # Create a metadata result chunk
                metadata_chunk_id = str(uuid.uuid4())
                metadata_chunk = PipelineChunk(
                    id=metadata_chunk_id,
                    batch_id=metadata_batch.id,
                    label="Metadata Results",
                    node_type="MetadataResult",
                    original_sentence=f"Added metadata to {processed_count} facts"
                )
                
                self.session.add(metadata_chunk)
                self.session.flush()
                
                # DEBUG: Show exactly what we're saving to the table
                import json
                print(f"\n{'='*80}")
                print(f"🔍 DEBUG: SAVING TO DATABASE")
                print(f"{'='*80}")
                print(f"Total metadata_results entries: {len(metadata_results)}")
                if metadata_results:
                    print(f"\nFirst metadata_results entry:")
                    print(json.dumps(metadata_results[0], indent=2, default=str))
                print(f"{'='*80}\n")
                
                # Save the stage result
                self.coordinator.save_stage_result(
                    metadata_chunk_id,
                    'metadata',
                    {
                        'metadata_results': metadata_results,
                        'processed_count': processed_count,
                        'stage': 'metadata'
                    }
                )
                
                logger.info(f"📊 Stored {len(metadata_results)} metadata results for merge stage")
                logger.info(f"   Metadata chunk ID: {metadata_chunk_id}")
            
            # Mark the chunk as processed using StageCompletion
            from datetime import datetime
            stage_completion = StageCompletion(
                chunk_id=fact_result.chunk_id,
                stage_name='metadata',
                status='completed',
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            self.session.add(stage_completion)
            self.session.commit()
            
            logger.info(f"✅ Metadata processing completed and marked as processed: {processed_count} facts processed")
            
            return {
                "processed_count": processed_count,
                "total_metadata": len(metadata_results),
                "message": f"Added metadata to {processed_count} facts successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Error in metadata processing: {e}")
            raise


if __name__ == '__main__':
    """
    Run metadata stage continuously with wait state
    """
    import app.assistant.tests.test_setup
    import asyncio
    import time
    from app.models.base import get_session
    from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
    
    async def run_metadata_continuously():
        print("🚀 Starting Metadata Stage (Stage 3)")
        print("=" * 50)
        print("📋 Mode: Continuous processing with wait state")
        print("⏹️  Press Ctrl+C to stop")
        print("=" * 50)
        
        session = get_session()
        coordinator = PipelineCoordinator(session)
        processor = MetadataProcessor(coordinator, session)
        
        total_processed = 0
        chunk_count = 0
        wait_interval = 60  # Check every 60 seconds when waiting
        
        try:
            while True:
                chunk_count += 1
                print(f"\n🔄 Chunk {chunk_count}: Checking for extracted facts...")
                
                # Check if data is available
                data_available = processor.wait_for_data(batch_id=None, max_wait_time=5)
                
                if not data_available:
                    print(f"⏸️  No data available. Waiting {wait_interval} seconds for fact extraction stage...")
                    print(f"📊 Total processed so far: {total_processed} nodes")
                    time.sleep(wait_interval)
                    continue
                
                # Process the chunk
                print(f"📖 Processing chunk {chunk_count}...")
                result = await processor.process(batch_size=10)
                
                processed_count = result.get('processed_count', 0)
                total_processed += processed_count
                
                if processed_count > 0:
                    print(f"✅ Chunk {chunk_count} completed: {processed_count} nodes enriched")
                    print(f"📊 Total so far: {total_processed} nodes")
                else:
                    print(f"⏸️  No nodes enriched. Waiting {wait_interval} seconds...")
                    time.sleep(wait_interval)
                    
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped by user (Ctrl+C)")
            print(f"📊 Processed {total_processed} nodes in {chunk_count} iterations before stopping")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()
            print("\n✅ Session closed")
    
    asyncio.run(run_metadata_continuously())
