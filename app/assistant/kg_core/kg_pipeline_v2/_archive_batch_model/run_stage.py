#!/usr/bin/env python3
"""
Stage Runner for KG Pipeline V2

Run individual stages independently:
python run_stage.py --stage fact_extraction --batch-size 100
python run_stage.py --stage parser --batch-size 100
python run_stage.py --stage metadata --batch-size 100
"""

import argparse
import logging
import sys
from typing import List

from app.models.base import get_session
from .pipeline_coordinator import PipelineCoordinator
from .stage_processors import (
    FactExtractionProcessor, ParserProcessor, MetadataProcessor, 
    MergeProcessor, TaxonomyProcessor
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_stage_processor(stage_name: str, coordinator: PipelineCoordinator):
    """Get the appropriate stage processor"""
    processors = {
        'fact_extraction': FactExtractionProcessor,
        'parser': ParserProcessor,
        'metadata': MetadataProcessor,
        'merge': MergeProcessor,
        'taxonomy': TaxonomyProcessor
    }
    
    if stage_name not in processors:
        raise ValueError(f"Unknown stage: {stage_name}")
    
    return processors[stage_name](coordinator)


def run_stage(stage_name: str, batch_id: int = None, batch_size: int = 100, 
              resume_failed: bool = False) -> Dict[str, Any]:
    """Run a specific stage for all eligible nodes"""
    
    session = get_session()
    coordinator = PipelineCoordinator(session)
    
    try:
        # Get stage processor
        processor = get_stage_processor(stage_name, coordinator)
        
        # Get nodes to process
        if resume_failed:
            nodes = coordinator.get_failed_nodes(stage_name, batch_id)
            logger.info(f"🔄 Resuming failed {stage_name} processing for {len(nodes)} nodes")
        else:
            nodes = coordinator.get_nodes_for_stage(stage_name, batch_id)
            logger.info(f"🚀 Starting {stage_name} processing for {len(nodes)} nodes")
        
        if not nodes:
            logger.info(f"✅ No nodes to process for stage {stage_name}")
            return {
                'success': True,
                'message': 'No nodes to process',
                'processed': 0,
                'failed': 0
            }
        
        # Process nodes in batches
        processed = 0
        failed = 0
        
        for i in range(0, len(nodes), batch_size):
            batch_nodes = nodes[i:i + batch_size]
            logger.info(f"📦 Processing batch {i//batch_size + 1} ({len(batch_nodes)} nodes)")
            
            for node in batch_nodes:
                try:
                    processor.process_node(node)
                    processed += 1
                    
                    if processed % 10 == 0:
                        logger.info(f"✅ Processed {processed} nodes")
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"❌ Failed to process node {node.id}: {str(e)}")
        
        # Update batch status if batch_id provided
        if batch_id:
            batch = session.query(coordinator.session.query(PipelineBatch).filter(
                PipelineBatch.id == batch_id
            ).first())
            
            if batch:
                batch.processed_nodes += processed
                batch.failed_nodes += failed
                session.commit()
        
        logger.info(f"🎉 Stage {stage_name} completed: {processed} processed, {failed} failed")
        
        return {
            'success': True,
            'stage': stage_name,
            'processed': processed,
            'failed': failed,
            'total_nodes': len(nodes)
        }
        
    except Exception as e:
        logger.error(f"💥 Stage {stage_name} failed: {str(e)}")
        return {
            'success': False,
            'stage': stage_name,
            'error': str(e)
        }
    
    finally:
        session.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Run KG Pipeline V2 stages')
    parser.add_argument('--stage', required=True, 
                       choices=['fact_extraction', 'parser', 'metadata', 'merge', 'taxonomy'],
                       help='Stage to run')
    parser.add_argument('--batch-id', type=int, help='Specific batch ID to process')
    parser.add_argument('--batch-size', type=int, default=100, 
                       help='Number of nodes to process per batch')
    parser.add_argument('--resume-failed', action='store_true',
                       help='Resume failed nodes for this stage')
    
    args = parser.parse_args()
    
    # Run the stage
    result = run_stage(
        stage_name=args.stage,
        batch_id=args.batch_id,
        batch_size=args.batch_size,
        resume_failed=args.resume_failed
    )
    
    # Print results
    if result['success']:
        print(f"✅ {result['stage']} completed successfully")
        print(f"   Processed: {result['processed']}")
        print(f"   Failed: {result['failed']}")
        if 'total_nodes' in result:
            print(f"   Total nodes: {result['total_nodes']}")
    else:
        print(f"❌ {result['stage']} failed: {result['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
