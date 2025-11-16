#!/usr/bin/env python3
"""
Pipeline Status Checker for KG Pipeline V2

Check the status of pipeline processing:
python check_pipeline_status.py
python check_pipeline_status.py --batch-id 1
"""

import argparse
import logging
from typing import Dict, Any

from app.models.base import get_session
from .pipeline_coordinator import PipelineCoordinator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_pipeline_status(batch_id: int = None) -> Dict[str, Any]:
    """Check the status of pipeline processing"""
    
    session = get_session()
    coordinator = PipelineCoordinator(session)
    
    try:
        if batch_id:
            # Check specific batch
            status = coordinator.get_batch_status(batch_id)
            return status
        else:
            # Check all batches
            batches = session.query(coordinator.session.query(PipelineBatch).all())
            
            batch_statuses = []
            for batch in batches:
                status = coordinator.get_batch_status(batch.id)
                batch_statuses.append(status)
            
            return {
                'total_batches': len(batch_statuses),
                'batches': batch_statuses
            }
    
    except Exception as e:
        logger.error(f"Error checking pipeline status: {str(e)}")
        return {'error': str(e)}
    
    finally:
        session.close()


def print_status(status: Dict[str, Any]):
    """Print status in a readable format"""
    
    if 'error' in status:
        print(f"❌ Error: {status['error']}")
        return
    
    if 'batches' in status:
        # Multiple batches
        print(f"📊 Pipeline Status - {status['total_batches']} batches")
        print("=" * 60)
        
        for batch in status['batches']:
            print(f"Batch {batch['batch_id']}: {batch['batch_name']}")
            print(f"  Status: {batch['status']}")
            print(f"  Nodes: {batch['processed_nodes']}/{batch['total_nodes']} processed, {batch['failed_nodes']} failed")
            
            if 'stage_counts' in batch:
                print("  Stage Progress:")
                for stage, counts in batch['stage_counts'].items():
                    print(f"    {stage}: {counts['completed']} completed, {counts['failed']} failed")
            
            print()
    
    else:
        # Single batch
        batch = status
        print(f"📊 Batch {batch['batch_id']} Status: {batch['batch_name']}")
        print("=" * 60)
        print(f"Status: {batch['status']}")
        print(f"Total Nodes: {batch['total_nodes']}")
        print(f"Processed: {batch['processed_nodes']}")
        print(f"Failed: {batch['failed_nodes']}")
        
        if 'stage_counts' in batch:
            print("\nStage Progress:")
            for stage, counts in batch['stage_counts'].items():
                total = counts['completed'] + counts['failed']
                print(f"  {stage}: {counts['completed']} completed, {counts['failed']} failed (total: {total})")
        
        print(f"\nCreated: {batch['created_at']}")
        if batch['started_at']:
            print(f"Started: {batch['started_at']}")
        if batch['completed_at']:
            print(f"Completed: {batch['completed_at']}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Check KG Pipeline V2 status')
    parser.add_argument('--batch-id', type=int, help='Check specific batch ID')
    
    args = parser.parse_args()
    
    # Check status
    status = check_pipeline_status(batch_id=args.batch_id)
    
    # Print results
    print_status(status)


if __name__ == '__main__':
    main()
