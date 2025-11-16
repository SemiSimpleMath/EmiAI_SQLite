"""
Metadata Stage Processor

Processes fact extraction and parser results to add metadata using the meta_data_add agent.
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
                    print(f"🔍 DEBUG: Fact extraction result {i+1} data keys: {list(result_data.keys())}")
                    print(f"🔍 DEBUG: Full result data: {result_data}")
                    
                    extracted_facts = result_data.get('extracted_facts', [])
                    print(f"🔍 DEBUG: Extracted facts type: {type(extracted_facts)}, length: {len(extracted_facts) if isinstance(extracted_facts, list) else 'N/A'}")
                    
                    logger.info(f"🔍 Processing fact extraction result {i+1}/{len(fact_results)} with {len(extracted_facts)} facts")
                    logger.info(f"📊 Fact extraction result data keys: {list(result_data.keys())}")
                    
                    # If no extracted facts, skip this result
                    if not extracted_facts:
                        print(f"🔍 DEBUG: No extracted facts found in result {i+1}, skipping...")
                        logger.warning(f"No extracted facts found in result {i+1}")
                        continue
                    
                    # Process each extracted fact
                    for fact_idx, fact_data in enumerate(extracted_facts):
                        # Handle both old format (atomic_sentence) and new format (atomic_sentences list)
                        atomic_sentence = fact_data.get('atomic_sentence', '')
                        atomic_sentences = fact_data.get('atomic_sentences', [])
                        
                        # Use the list if available, otherwise fall back to single sentence
                        if atomic_sentences:
                            # Join all sentences for context
                            atomic_sentence = ' '.join(atomic_sentences)
                        
                        extracted_facts_data = fact_data.get('extracted_facts', {})
                        original_message_timestamp = fact_data.get('original_message_timestamp')  # Extract timestamp
                        
                        logger.info(f"📝 Fact {fact_idx+1}: atomic_sentence='{atomic_sentence[:50]}...', extracted_facts_data keys: {list(extracted_facts_data.keys()) if isinstance(extracted_facts_data, dict) else type(extracted_facts_data)}")
                        logger.info(f"📅 Original message timestamp: {original_message_timestamp}")
                        
                        if not atomic_sentence.strip():
                            logger.warning(f"Skipping empty atomic sentence at fact {fact_idx+1}")
                            continue
                        
                        # Extract nodes and edges from the extracted facts data
                        nodes = extracted_facts_data.get('nodes', [])
                        edges = extracted_facts_data.get('edges', [])
                        
                        print(f"🔍 DEBUG: Processing ALL {len(nodes)} nodes at once from fact {fact_idx+1}")
                        print(f"📅 DEBUG: Timestamp: {original_message_timestamp}")
                        
                        # Skip facts with no nodes (fact extraction failed or returned empty)
                        if not nodes:
                            logger.warning(f"⚠️ Skipping fact {fact_idx+1} - no nodes extracted")
                            continue
                        
                        # Process all nodes at once (simpler and faster)
                        logger.info(f"🔍 Adding metadata to {len(nodes)} nodes from fact {fact_idx+1}...")
                        
                        # Format the input for the metadata agent
                        # Pass ALL nodes at once with the atomic sentence
                        metadata_input = {
                            "nodes": nodes,  # All nodes from this fact
                            "edges": edges,  # All edges from this fact
                            "resolved_sentence": atomic_sentence,  # The atomic sentence for context (must be 'resolved_sentence' per config)
                            "message_timestamp": original_message_timestamp  # Pass actual timestamp!
                        }
                        result = self.agent.action_handler(Message(agent_input=metadata_input))
                        
                        # Parse agent response
                        if result and hasattr(result, 'data') and result.data:
                            metadata_data = result.data
                        else:
                            metadata_data = str(result)
                        
                        # DEBUG: Show what the agent returned
                        print(f"🔍 DEBUG: Metadata agent response type: {type(metadata_data)}")
                        if isinstance(metadata_data, dict):
                            print(f"🔍 DEBUG: Metadata agent response keys: {list(metadata_data.keys())}")
                        print(f"🔍 DEBUG: Metadata agent response: {str(metadata_data)[:500]}")
                        
                        # Extract the enriched nodes from the response and merge with original nodes
                        enriched_nodes = []
                        if isinstance(metadata_data, dict) and 'Nodes' in metadata_data:
                            metadata_nodes = metadata_data.get('Nodes', [])
                            logger.info(f"✅ Got {len(metadata_nodes)} enriched nodes from agent")
                            
                            # Clear temporal fields for Entity and Concept nodes in metadata response
                            for meta_node in metadata_nodes:
                                node_type = meta_node.get('node_type', '')
                                if node_type in ['Entity', 'Concept']:
                                    meta_node['valid_during'] = None
                                    meta_node['start_date'] = None
                                    meta_node['end_date'] = None
                                    meta_node['start_date_confidence'] = None
                                    meta_node['end_date_confidence'] = None
                            
                            # Merge metadata with original nodes by temp_id
                            for original_node in nodes:
                                # Find matching metadata by temp_id
                                matching_metadata = None
                                for meta_node in metadata_nodes:
                                    if meta_node.get('temp_id') == original_node.get('temp_id'):
                                        matching_metadata = meta_node
                                        break
                                
                                # Merge: start with original node, overlay metadata
                                enriched_node = original_node.copy()
                                if matching_metadata:
                                    enriched_node.update(matching_metadata)
                                    print(f"✅ Merged metadata for {original_node.get('label', 'unknown')}")
                                else:
                                    print(f"⚠️ No metadata found for {original_node.get('label', 'unknown')}, keeping original")
                                
                                enriched_nodes.append(enriched_node)
                            
                            logger.info(f"✅ Enriched {len(enriched_nodes)} nodes from fact {fact_idx+1}")
                        else:
                            logger.warning(f"Unexpected metadata response format, keeping original nodes")
                            print(f"⚠️ DEBUG: Falling back to original nodes (count: {len(nodes)})")
                            enriched_nodes = nodes  # Keep original
                        
                        # Rename 'core' to 'category' in enriched nodes (handles old fact extraction data)
                        for node in enriched_nodes:
                            if 'core' in node:
                                node['category'] = node.pop('core')
                        
                        # DEBUG: Show what we're about to store
                        if enriched_nodes:
                            print(f"🔍 DEBUG: About to store {len(enriched_nodes)} enriched nodes")
                            print(f"🔍 DEBUG: First enriched node keys: {list(enriched_nodes[0].keys())}")
                            print(f"🔍 DEBUG: First enriched node sample: label={enriched_nodes[0].get('label')}, node_type={enriched_nodes[0].get('node_type')}, category={enriched_nodes[0].get('category')}")
                        
                        # Store metadata for this fact with enriched nodes
                        metadata_results.append({
                            'fact_index': fact_idx,
                            'atomic_sentence': atomic_sentence,
                            'nodes': enriched_nodes,  # Enriched nodes
                            'edges': edges,  # Edges pass through unchanged
                            'fact_result_id': str(fact_result.chunk_id)  # Convert UUID to string
                        })
                        
                        processed_count += len(nodes)  # Count processed nodes
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
