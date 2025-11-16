"""
Merge Stage Processor

Processes all previous stage results to merge and consolidate nodes and edges.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineChunk, MergeResult, StageResult, StageCompletion
)
from app.assistant.kg_core.kg_pipeline_v2.utils import wait_for_stage_data

logger = logging.getLogger(__name__)


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
    except:
        # If it can't be parsed, it's not a valid date
        return None


class MergeProcessor:
    """Processes merge stage"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        self.merge_agent = DI.agent_factory.create_agent("knowledge_graph_add::node_merger")
        self.node_data_merger = DI.agent_factory.create_agent("knowledge_graph_add::node_data_merger")
    
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
        logger.info(f"🔄 Merge waiting for metadata results...")
        
        # Check if there are metadata results available
        metadata_results = self.session.query(StageResult).filter(
            StageResult.stage_name == 'metadata'
        ).all()
        
        if metadata_results:
            logger.info(f"✅ Found {len(metadata_results)} metadata results")
            return True
        else:
            logger.warning("⚠️ No metadata results found")
            return False
    
    async def process(self, batch_size: int = 1) -> Dict[str, Any]:
        """
        Process ONE chunk from metadata results and merge with existing KG database.
        This matches the original kg_pipeline.py behavior where each chunk is processed independently.
        
        Args:
            batch_size: Number of chunks to process (default 1 for one chunk at a time)
            
        Returns:
            Dict containing processing results
        """
        try:
            # Import KnowledgeGraphUtils to access the KG database
            from app.assistant.kg_core.knowledge_graph_utils import KnowledgeGraphUtils
            
            # Read ONE unprocessed metadata result (one chunk) from the waiting area
            logger.info(f"📖 Reading one chunk from metadata waiting area...")
            
            # Get one metadata result that hasn't been processed by merge stage yet
            # Use StageCompletion to track which chunks have been processed
            from sqlalchemy import select
            processed_chunk_ids = select(StageCompletion.chunk_id).filter(
                StageCompletion.stage_name == 'merge',
                StageCompletion.status == 'completed'
            ).scalar_subquery()
            
            metadata_result = self.session.query(StageResult).filter(
                StageResult.stage_name == 'metadata',
                ~StageResult.chunk_id.in_(processed_chunk_ids)
            ).first()
            
            if not metadata_result:
                logger.warning("⚠️ No metadata chunks available in waiting area")
                return {"processed_count": 0, "message": "No chunks to process"}
            
            # Initialize KG utils for this chunk
            kg_utils = KnowledgeGraphUtils()
            
            # Extract the chunk data
            result_data = metadata_result.result_data
            
            # DEBUG: Show exactly what we're reading from the table
            import json
            print(f"\n{'='*80}")
            print(f"🔍 DEBUG: READING FROM DATABASE")
            print(f"{'='*80}")
            print(f"result_data keys: {list(result_data.keys())}")
            metadata_results_list = result_data.get('metadata_results', [])
            print(f"Total metadata_results entries: {len(metadata_results_list)}")
            if metadata_results_list:
                print(f"\nFirst metadata_results entry:")
                print(json.dumps(metadata_results_list[0], indent=2, default=str))
            print(f"{'='*80}\n")
            
            if not metadata_results_list:
                logger.warning("⚠️ Empty metadata results list in chunk")
                return {"processed_count": 0, "message": "Empty chunk"}
            
            logger.info(f"🔍 Processing chunk with {len(metadata_results_list)} metadata entries")
            
            # DEBUG: Show structure of first metadata entry
            if metadata_results_list:
                first_entry = metadata_results_list[0]
                print(f"🔍 DEBUG: First metadata entry keys: {list(first_entry.keys())}")
                print(f"🔍 DEBUG: First metadata entry structure: {str(first_entry)[:500]}")
                logger.info(f"🔍 DEBUG: First metadata entry keys: {list(first_entry.keys())}")
                logger.info(f"🔍 DEBUG: First metadata entry structure: {str(first_entry)[:500]}")
            
            # Collect all nodes and edges from all metadata entries in this chunk
            all_nodes = []
            all_edges = []
            
            for i, metadata_entry in enumerate(metadata_results_list):
                # Metadata stage stores nodes and edges directly (not in 'extracted_facts')
                nodes = metadata_entry.get('nodes', [])
                edges = metadata_entry.get('edges', [])
                
                print(f"🔍 DEBUG: Entry {i+1} has {len(nodes)} nodes and {len(edges)} edges")
                logger.info(f"🔍 DEBUG: Entry {i+1} has {len(nodes)} nodes and {len(edges)} edges")
                
                all_nodes.extend(nodes)
                all_edges.extend(edges)
            
            logger.info(f"📊 Chunk contains {len(all_nodes)} nodes and {len(all_edges)} edges")
            
            # Define canonical entities that should never be duplicated
            CANONICAL_ENTITIES = {"Jukka", "Emi"}
            
            # Process nodes one at a time, finding candidates for each
            node_map = {}
            for node in all_nodes:
                temp_id = node.get("temp_id")
                label = node.get("label", "")
                node_type = node.get("node_type", "")
                category = node.get("category")
                
                logger.info(f"🔍 Processing node: {label} (type: {node_type})")
                
                # Check if this is a canonical entity (Jukka or Emi)
                if label in CANONICAL_ENTITIES:
                    logger.info(f"🔑 Canonical entity detected: {label} - looking for existing node")
                    
                    # Find the existing canonical node (should be exactly one)
                    from app.assistant.kg_core.knowledge_graph_db import Node
                    canonical_node = kg_utils.session.query(Node).filter(
                        Node.label == label
                    ).first()
                    
                    if canonical_node:
                        logger.info(f"✅ Using existing canonical node: {label} (ID: {canonical_node.id})")
                        node_map[temp_id] = canonical_node
                        continue
                    else:
                        logger.warning(f"⚠️ Canonical entity '{label}' not found in KG - will create it")
                        # Fall through to normal creation logic
                
                # Use kg_utils.add_node which:
                # 1. Finds 1-3 similar nodes in KG database
                # 2. Calls merge agent to decide merge or create
                # 3. Returns the node (merged or new)
                try:
                    new_node, status = kg_utils.add_node(
                        node_type=node_type.title() if node_type else "Unknown",
                        label=label,
                        aliases=node.get("aliases", []),
                        description="",
                        category=category,
                        attributes={},
                        valid_during=sanitize_null_values(node.get("valid_during")),
                        hash_tags=node.get("hash_tags"),
                        start_date=sanitize_date_field(node.get("start_date")),
                        end_date=sanitize_date_field(node.get("end_date")),
                        start_date_confidence=sanitize_null_values(node.get("start_date_confidence")),
                        end_date_confidence=sanitize_null_values(node.get("end_date_confidence")),
                        semantic_label=sanitize_null_values(node.get("semantic_label")),
                        goal_status=sanitize_null_values(node.get("goal_status")),
                        confidence=node.get("confidence"),
                        importance=node.get("importance"),
                        source=sanitize_null_values(node.get("source")),
                        original_message_id=sanitize_null_values(node.get("original_message_id")),
                        original_sentence=node.get("sentence"),
                        sentence_id=sanitize_null_values(node.get("sentence_id")),
                        # Pass both merge agents
                        merge_agent=self.merge_agent,
                        node_data_merger=self.node_data_merger
                    )
                    
                    node_map[temp_id] = new_node
                    
                    if status == "created":
                        logger.info(f"✅ NODE CREATED: '{label}' (ID: {new_node.id})")
                    elif status == "merged":
                        logger.info(f"🔀 NODE MERGED: '{label}' merged into existing node (ID: {new_node.id})")
                    else:
                        logger.info(f"✅ NODE {status.upper()}: '{label}' (ID: {new_node.id})")
                        
                except Exception as e:
                    logger.error(f"❌ Failed to process node '{label}': {e}")
                    continue
            
            # Process edges for this chunk
            for edge in all_edges:
                source_temp_id = edge.get("source")
                target_temp_id = edge.get("target")
                edge_label = edge.get("label")
                sentence = edge.get("sentence", "")
                
                source_node = node_map.get(source_temp_id)
                target_node = node_map.get(target_temp_id)
                
                if not source_node or not target_node:
                    logger.warning(f"⚠️ Skipping edge due to missing nodes: {source_temp_id} -> {target_temp_id}")
                    continue
                
                try:
                    edge_obj, status = kg_utils.safe_add_relationship_by_id(
                        source_id=source_node.id,
                        target_id=target_node.id,
                        relationship_type=edge_label.title() if edge_label else "Unknown",
                        attributes={},
                        sentence=sentence,
                        original_message_timestamp=None,
                        confidence=None,
                        importance=None,
                        source=node.get("source"),
                        original_message_id=node.get("original_message_id"),
                        sentence_id=node.get("sentence_id"),
                        relationship_descriptor=edge.get("relationship_descriptor")
                    )
                    
                    if status == "created":
                        logger.info(f"✅ EDGE CREATED: {source_node.label} -> {edge_label} -> {target_node.label}")
                    elif status == "merged":
                        logger.info(f"🔀 EDGE MERGED: {source_node.label} -> {edge_label} -> {target_node.label}")
                    else:
                        logger.info(f"✅ EDGE {status.upper()}: {source_node.label} -> {edge_label} -> {target_node.label}")
                        
                except Exception as e:
                    logger.error(f"❌ Failed to process edge: {e}")
                    continue
            
            # Commit changes for this chunk
            try:
                kg_utils.session.commit()
                logger.info(f"✅ Committed chunk: {len(node_map)} nodes, {len(edges)} edges")
            except Exception as e:
                logger.error(f"❌ Failed to commit chunk: {e}")
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
            
            logger.info(f"✅ Chunk processing completed and marked as processed: {len(node_map)} nodes, {len(edges)} edges")
            
            return {
                "processed_count": len(node_map) + len(edges),
                "nodes_processed": len(node_map),
                "edges_processed": len(edges),
                "message": f"Processed 1 chunk: {len(node_map)} nodes and {len(edges)} edges into knowledge graph"
            }
            
        except Exception as e:
            logger.error(f"❌ Error in merge processing: {e}")
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
        print("🚀 Starting Merge Stage (Stage 4)")
        print("=" * 50)
        print("📋 Mode: Continuous processing with wait state")
        print("⏹️  Press Ctrl+C to stop")
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
                print(f"\n🔄 Chunk {chunk_count}: Checking for enriched metadata...")
                
                # Check if data is available
                data_available = processor.wait_for_data(batch_id=None, max_wait_time=5)
                
                if not data_available:
                    print(f"⏸️  No data available. Waiting {wait_interval} seconds for metadata stage...")
                    print(f"📊 Total processed so far: {total_nodes} nodes, {total_edges} edges")
                    time.sleep(wait_interval)
                    continue
                
                # Process the chunk
                print(f"📖 Processing chunk {chunk_count}...")
                result = await processor.process(batch_size=10)
                
                nodes_processed = result.get('nodes_processed', 0)
                edges_processed = result.get('edges_processed', 0)
                total_nodes += nodes_processed
                total_edges += edges_processed
                
                if nodes_processed > 0 or edges_processed > 0:
                    print(f"✅ Chunk {chunk_count} completed: {nodes_processed} nodes, {edges_processed} edges merged into KG")
                    print(f"📊 Total so far: {total_nodes} nodes, {total_edges} edges")
                else:
                    print(f"⏸️  No data merged. Waiting {wait_interval} seconds...")
                    time.sleep(wait_interval)
                    
        except KeyboardInterrupt:
            print("\n\n⏹️  Stopped by user (Ctrl+C)")
            print(f"📊 Processed {total_nodes} nodes and {total_edges} edges in {chunk_count} iterations before stopping")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()
            print("\n✅ Session closed")
    
    asyncio.run(run_merge_continuously())
