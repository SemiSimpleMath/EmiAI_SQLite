"""
Merge Stage Processor

Processes all previous stage results to merge and consolidate nodes and edges.

NOTE: This stage uses V1's battle-tested helper functions to ensure feature parity.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineChunk, MergeResult, StageResult, StageCompletion
)
# from app.assistant.kg_core.kg_pipeline_v2.utils import wait_for_stage_data  # currently unused

# Import V1 helper functions for feature parity
from app.assistant.kg_core.kg_pipeline import process_nodes, process_edges

logger = logging.getLogger(__name__)

# NOTE: knowledge_graph_db and knowledge_graph_utils are imported lazily inside methods
# to avoid SQLAlchemy table redefinition errors when running as subprocess


def sanitize_null_values(value):
    """
    Convert various null representations to actual None
    Handles: "_null", "/null", "/", "", "null" (string), NUL character (\u0000)
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Check for NUL character first
        if '\x00' in value or '\u0000' in value:
            return None
        if value.strip() in ["_null", "/null", "/", "", "null", "_None", "/None"]:
            return None
    return value


def sanitize_date_field(value):
    """
    Try to convert a value to a valid date/timestamp.
    If it can't be converted, return None.
    """
    if value is None:
        return None
    
    # Try to parse as a date - if it fails, return None
    try:
        from dateutil import parser
        return parser.parse(str(value))
    except Exception:
        # If it can't be parsed, it's not a valid date (ValueError, TypeError, etc.)
        return None


class MergeProcessor:
    """Processes merge stage"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        # Node merge agents (same as V1)
        self.merge_agent = DI.agent_factory.create_agent("knowledge_graph_add::node_merger")
        self.node_data_merger = DI.agent_factory.create_agent("knowledge_graph_add::node_data_merger")
        # Edge merge agent (from V1 - LLM-based intelligent edge merging)
        self.edge_merge_agent = DI.agent_factory.create_agent("knowledge_graph_add::edge_merger")
    
    def wait_for_data(self, batch_id: int = None, max_wait_time: int = 300) -> bool:
        """
        Wait for metadata results to become available for merge processing
        Reads from stage_results where stage_name = 'metadata'
        
        Args:
            batch_id: Specific batch ID to wait for (None for any batch)
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if data became available, False if timeout
        """
        logger.info("Merge waiting for metadata results...")
        
        # Check if there are metadata results available
        metadata_results = self.session.query(StageResult).filter(
            StageResult.stage_name == 'metadata'
        ).all()
        
        if metadata_results:
            logger.info(f"Found {len(metadata_results)} metadata results")
            return True
        else:
            logger.warning("No metadata results found")
            return False
    
    async def process(self, batch_size: int = 1) -> Dict[str, Any]:
        """
        Process ONE chunk from metadata results and merge with existing KG database.
        
        Uses V1 helper functions for:
        - process_nodes(): Full node processing with LLM merge, metadata enrichment
        - process_edges(): Full edge processing with LLM merge, orphan detection
        
        Args:
            batch_size: Number of chunks to process (default 1 for one chunk at a time)
            
        Returns:
            Dict containing processing results
        """
        try:
            # Read ONE unprocessed metadata result (one chunk) from the waiting area
            logger.info("Reading one chunk from metadata waiting area...")
            
            # Get one metadata result that hasn't been processed by merge stage yet
            # Use StageCompletion to track which chunks have been processed
            processed_chunk_ids = select(StageCompletion.chunk_id).filter(
                StageCompletion.stage_name == 'merge',
                StageCompletion.status == 'completed'
            ).scalar_subquery()
            
            metadata_result = self.session.query(StageResult).filter(
                StageResult.stage_name == 'metadata',
                ~StageResult.chunk_id.in_(processed_chunk_ids)
            ).first()
            
            if not metadata_result:
                logger.warning("No metadata chunks available in waiting area")
                return {"processed_count": 0, "message": "No chunks to process"}
            
            # Lazy import to avoid SQLAlchemy table redefinition when running as subprocess
            from app.assistant.kg_core.knowledge_graph_utils import KnowledgeGraphUtils
            
            # Initialize KG utils for this chunk
            kg_utils = KnowledgeGraphUtils()
            
            # Extract the chunk data
            result_data = metadata_result.result_data
            
            logger.info(f"DEBUG: result_data keys: {list(result_data.keys())}")
            metadata_results_list = result_data.get('metadata_results', [])
            logger.info(f"Total metadata_results entries: {len(metadata_results_list)}")
            
            if not metadata_results_list:
                logger.warning("Empty metadata results list in chunk")
                return {"processed_count": 0, "message": "Empty chunk"}
            
            logger.info(f"Processing chunk with {len(metadata_results_list)} metadata entries")
            
            # Track totals
            total_nodes_processed = 0
            total_edges_created = 0
            total_edges_merged = 0
            total_edges_skipped = 0
            
            # V1 FEATURE: Process each metadata entry separately (preserves conversation context)
            for conv_idx, metadata_entry in enumerate(metadata_results_list):
                # Extract V1 metadata from entry
                nodes = metadata_entry.get('nodes', [])
                edges = metadata_entry.get('edges', [])
                conversation_text = metadata_entry.get('conversation_text', '')
                block_ids = metadata_entry.get('block_ids', [])
                data_source = metadata_entry.get('data_source', 'unknown')
                original_message_timestamp = metadata_entry.get('original_message_timestamp')
                
                logger.info(f"🔍 Processing entry {conv_idx+1}/{len(metadata_results_list)}: {len(nodes)} nodes, {len(edges)} edges")
                
                if not nodes:
                    logger.warning(f"Skipping entry {conv_idx+1} - no nodes")
                    continue
                
                # Build enriched_metadata dict from nodes (V1 format: temp_id -> metadata)
                # The metadata has already been enriched by the metadata stage
                enriched_metadata = {}
                for node in nodes:
                    temp_id = node.get("temp_id")
                    if temp_id:
                        enriched_metadata[temp_id] = node
                
                # Build atomic sentences list for edge processing
                all_atomic_sentences = []
                for node in nodes:
                    sentence = node.get("sentence", "")
                    if sentence:
                        all_atomic_sentences.append(sentence)
                
                sentence_window_text = " ".join(all_atomic_sentences)
                
                # V1 FUNCTION: Process nodes with full LLM merge logic
                logger.info(f"Processing {len(nodes)} nodes using V1 process_nodes...")
                try:
                    nodes_result = process_nodes(
                        original_nodes=nodes,
                        enriched_metadata=enriched_metadata,
                        original_edges=edges,
                        conversation_text=conversation_text,
                        sentence_window_text=sentence_window_text,
                        data_source=data_source,
                        original_message_timestamp_str=original_message_timestamp,
                        kg_utils=kg_utils,
                        merge_agent=self.merge_agent,
                        node_data_merger=self.node_data_merger,
                        block_ids=block_ids,
                        sentence_id=None
                    )
                    
                    node_map = nodes_result.get("node_map", {})
                    passthrough_edges = nodes_result.get("edges", edges)
                    
                    total_nodes_processed += len(node_map)
                    logger.info(f"Processed {len(node_map)} nodes")
                    
                except Exception as e:
                    logger.error(f"Failed to process nodes: {e}")
                    continue
                
                # V1 FUNCTION: Process edges with LLM merge and orphan detection
                logger.info(f"Processing {len(passthrough_edges)} edges using V1 process_edges...")
                try:
                    edges_result = process_edges(
                        edges=passthrough_edges,
                        node_map=node_map,
                        conversation_text=conversation_text,
                        all_atomic_sentences=all_atomic_sentences,
                        data_source=data_source,
                        original_message_timestamp_str=original_message_timestamp,
                        kg_utils=kg_utils,
                        edge_merge_agent=self.edge_merge_agent,
                        conv_idx=conv_idx,
                        block_ids=block_ids,
                        sentence_id=None
                    )
                    
                    total_edges_created += edges_result.get("edges_created", 0)
                    total_edges_merged += edges_result.get("edges_merged", 0)
                    total_edges_skipped += edges_result.get("edges_skipped_missing_nodes", 0)
                    
                    logger.info(f"Edge summary: {edges_result.get('edges_created', 0)} created, "
                               f"{edges_result.get('edges_merged', 0)} merged")
                    
                except RuntimeError as e:
                    # V1 FEATURE: Orphan node detection raises RuntimeError
                    logger.error(f"Data integrity error: {e}")
                    # Continue processing other entries
                    continue
                except Exception as e:
                    logger.error(f"Failed to process edges: {e}")
                    continue
            
            logger.info(f"Total: {total_nodes_processed} nodes, "
                       f"{total_edges_created} edges created, {total_edges_merged} edges merged")
            
            # Commit changes for this chunk
            try:
                kg_utils.session.commit()
                total_edges_processed = total_edges_created + total_edges_merged
                logger.info(f"Committed chunk: {total_nodes_processed} nodes, {total_edges_processed} edges")
            except Exception as e:
                logger.error(f"Failed to commit chunk: {e}")
                kg_utils.session.rollback()
                kg_utils.close()
                raise
            
            # Close KG utils
            kg_utils.close()
            
            # Mark the chunk as processed using StageCompletion
            from datetime import datetime
            stage_completion = StageCompletion(
                chunk_id=metadata_result.chunk_id,
                stage_name='merge',
                status='completed',
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
            self.session.add(stage_completion)
            self.session.commit()
            
            total_edges_processed = total_edges_created + total_edges_merged
            logger.info(f"Chunk processing completed: {total_nodes_processed} nodes, {total_edges_processed} edges")
            
            return {
                "processed_count": total_nodes_processed + total_edges_processed,
                "nodes_processed": total_nodes_processed,
                "edges_processed": total_edges_processed,
                "edges_created": total_edges_created,
                "edges_merged": total_edges_merged,
                "edges_skipped": total_edges_skipped,
                "message": f"Processed 1 chunk: {total_nodes_processed} nodes and {total_edges_processed} edges into knowledge graph"
            }
            
        except Exception as e:
            logger.error(f"Error in merge processing: {e}")
            raise
    


if __name__ == '__main__':
    """
    Run merge stage continuously with wait state
    """
    import app.assistant.tests.test_setup
    import asyncio
    import time
    from app.models.base import get_session
    from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
    
    async def run_merge_continuously():
        print("Starting Merge Stage (Stage 4)")
        print("=" * 50)
        print("Mode: Continuous processing with wait state")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        
        session = get_session()
        coordinator = PipelineCoordinator(session)
        processor = MergeProcessor(coordinator, session)
        
        total_nodes = 0
        total_edges = 0
        chunk_count = 0
        wait_interval = 60  # Check every 60 seconds when waiting
        
        try:
            while True:
                chunk_count += 1
                print(f"\nChunk {chunk_count}: Checking for enriched metadata...")
                
                # Check if data is available
                data_available = processor.wait_for_data(batch_id=None, max_wait_time=5)
                
                if not data_available:
                    print(f"No data available. Waiting {wait_interval} seconds for metadata stage...")
                    print(f"Total processed so far: {total_nodes} nodes, {total_edges} edges")
                    time.sleep(wait_interval)
                    continue
                
                # Process the chunk
                print(f"Processing chunk {chunk_count}...")
                result = await processor.process(batch_size=10)
                
                nodes_processed = result.get('nodes_processed', 0)
                edges_processed = result.get('edges_processed', 0)
                total_nodes += nodes_processed
                total_edges += edges_processed
                
                if nodes_processed > 0 or edges_processed > 0:
                    print(f"[OK] Chunk {chunk_count} completed: {nodes_processed} nodes, {edges_processed} edges merged into KG")
                    print(f"Total so far: {total_nodes} nodes, {total_edges} edges")
                else:
                    print(f"No data merged. Waiting {wait_interval} seconds...")
                    time.sleep(wait_interval)
                    
        except KeyboardInterrupt:
            print("\n\nStopped by user (Ctrl+C)")
            print(f"Processed {total_nodes} nodes and {total_edges} edges in {chunk_count} iterations before stopping")
        except Exception as e:
            print(f"\n[ERR] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()
            print("\n[OK] Session closed")
    
    asyncio.run(run_merge_continuously())
