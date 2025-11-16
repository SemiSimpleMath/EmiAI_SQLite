#!/usr/bin/env python3
"""
Run Stage with Proper Data Flow

This script runs a specific stage with proper data flow from previous stages.
It reads from database tables written by previous stages.
"""

import argparse
import asyncio
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.stages import (
    ConversationBoundaryProcessor, FactExtractionProcessor, ParserProcessor,
    MetadataProcessor, MergeProcessor, TaxonomyProcessor
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

STAGE_PROCESSORS = {
    "conversation_boundary": ConversationBoundaryProcessor,
    "fact_extraction": FactExtractionProcessor,
    "parser": ParserProcessor,
    "metadata": MetadataProcessor,
    "merge": MergeProcessor,
    "taxonomy": TaxonomyProcessor
}


async def run_stage_with_data_flow(stage_name: str, batch_id: int = None, batch_size: int = 100, resume_failed: bool = False):
    """
    Run a specific stage with proper data flow from previous stages
    
    Args:
        stage_name: Name of the stage to run
        batch_id: Specific batch ID (None for all batches)
        batch_size: Number of nodes to process in one batch
        resume_failed: Whether to resume failed nodes
    """
    logger.info(f"🚀 Starting stage: {stage_name}")
    logger.info(f"   Batch ID: {batch_id or 'All'}")
    logger.info(f"   Batch size: {batch_size}")
    logger.info(f"   Resume failed: {resume_failed}")
    
    session: Session = get_session()
    coordinator = PipelineCoordinator(session)
    
    if stage_name not in STAGE_PROCESSORS:
        logger.error(f"❌ Unknown stage: {stage_name}")
        return {"success": False, "error": f"Unknown stage: {stage_name}"}
    
    try:
        # Get nodes ready for this stage
        nodes = coordinator.get_nodes_for_stage(stage_name, batch_id)
        if not nodes:
            logger.info(f"📭 No nodes found for stage: {stage_name}")
            return {"success": True, "processed": 0, "failed": 0}
        
        logger.info(f"📊 Found {len(nodes)} nodes ready for {stage_name}")
        
        # Create processor
        processor_class = STAGE_PROCESSORS[stage_name]
        processor = processor_class(coordinator, session)
        
        processed_count = 0
        failed_count = 0
        
        # Process nodes in batches
        for i in range(0, len(nodes), batch_size):
            batch_nodes = nodes[i:i + batch_size]
            logger.info(f"🔄 Processing batch {i//batch_size + 1}: {len(batch_nodes)} nodes")
            
            for node in batch_nodes:
                try:
                    logger.info(f"   Processing node {node.id} for stage {stage_name}")
                    
                    # Get complete node data with all previous stage results
                    full_node_data = coordinator.get_full_node_data_with_stage_results(str(node.id))
                    
                    # Get prerequisite results for this stage
                    prerequisites = coordinator.get_prerequisite_results(str(node.id), stage_name)
                    
                    # Process the node based on stage
                    if stage_name == "conversation_boundary":
                        result = await processor.process(full_node_data)
                    elif stage_name == "fact_extraction":
                        result = await processor.process(full_node_data)
                    elif stage_name == "parser":
                        result = await processor.process(full_node_data)
                    elif stage_name == "metadata":
                        # Metadata needs facts + parser results
                        facts = prerequisites.get('fact_extraction', {})
                        parsed = prerequisites.get('parser', {})
                        result = await processor.process(full_node_data, facts, parsed)
                    elif stage_name == "merge":
                        # Merge needs facts + parser + metadata results
                        facts = prerequisites.get('fact_extraction', {})
                        parsed = prerequisites.get('parser', {})
                        metadata = prerequisites.get('metadata', {})
                        result = await processor.process(full_node_data, facts, parsed, metadata)
                    elif stage_name == "taxonomy":
                        # Taxonomy needs all previous results
                        facts = prerequisites.get('fact_extraction', {})
                        parsed = prerequisites.get('parser', {})
                        metadata = prerequisites.get('metadata', {})
                        merged = prerequisites.get('merge', {})
                        result = await processor.process(full_node_data, facts, parsed, metadata, merged)
                    
                    # Save result to database
                    coordinator.save_stage_result(
                        str(node.id), 
                        stage_name, 
                        result,
                        processing_time=0.0,  # Could track actual time
                        agent_version=f"{stage_name}_v1"
                    )
                    
                    # Mark stage as complete
                    coordinator.mark_stage_complete(str(node.id), stage_name)
                    
                    processed_count += 1
                    logger.info(f"   ✅ Completed node {node.id}")
                    
                except Exception as e:
                    logger.error(f"   ❌ Failed node {node.id}: {str(e)}")
                    coordinator.mark_stage_failed(str(node.id), stage_name, str(e))
                    failed_count += 1
            
            # Commit batch
            session.commit()
            logger.info(f"✅ Batch {i//batch_size + 1} completed")
        
        logger.info(f"🎉 Stage {stage_name} completed!")
        logger.info(f"   Processed: {processed_count}")
        logger.info(f"   Failed: {failed_count}")
        
        return {
            "success": True,
            "processed": processed_count,
            "failed": failed_count
        }
        
    except Exception as e:
        logger.error(f"❌ Stage {stage_name} failed: {str(e)}")
        return {"success": False, "error": str(e)}
    
    finally:
        session.close()


if __name__ == "__main__":
    """
    Run this file directly from IDE to run a stage with proper data flow
    """
    print("🚀 KG Pipeline V2 - Run Stage with Data Flow")
    print("=" * 50)
    
    # Get stage from user - FIXED ORDER: 0→1→2→3→4→5
    stages = ['conversation_boundary', 'parser', 'fact_extraction', 'metadata', 'merge', 'taxonomy']
    
    print("Available stages:")
    for i, stage in enumerate(stages, 1):
        print(f"  {i}. {stage}")
    
    try:
        stage_choice = int(input("Select stage (1-6): ")) - 1
        if stage_choice < 0 or stage_choice >= len(stages):
            print("❌ Invalid stage selection")
            exit(1)
        
        stage_name = stages[stage_choice]
        
        # Get batch ID
        batch_id_input = input("Enter batch ID: ").strip()
        if not batch_id_input:
            print("❌ Batch ID is required")
            exit(1)
        
        try:
            batch_id = int(batch_id_input)
        except ValueError:
            print("❌ Batch ID must be a number")
            exit(1)
        
        # Get batch size
        batch_size_input = input("Enter batch size: ").strip()
        if not batch_size_input:
            print("❌ Batch size is required")
            exit(1)
        
        try:
            batch_size = int(batch_size_input)
        except ValueError:
            print("❌ Batch size must be a number")
            exit(1)
        
        # Get resume failed option
        resume_failed_input = input("Resume failed nodes? (y/N): ").strip().lower()
        if resume_failed_input not in ['y', 'n']:
            print("❌ Must enter 'y' or 'n'")
            exit(1)
        resume_failed = resume_failed_input == 'y'
        
        print(f"\n🔄 Running stage: {stage_name}")
        print(f"   Batch ID: {batch_id or 'All'}")
        print(f"   Batch size: {batch_size}")
        print(f"   Resume failed: {resume_failed}")
        
        # Run the stage
        asyncio.run(run_stage_with_data_flow(
            stage_name, 
            batch_id, 
            batch_size, 
            resume_failed
        ))
        
    except ValueError:
        print("❌ Invalid input")
        exit(1)
    except Exception as e:
        print(f"❌ Error running stage: {str(e)}")
        exit(1)
