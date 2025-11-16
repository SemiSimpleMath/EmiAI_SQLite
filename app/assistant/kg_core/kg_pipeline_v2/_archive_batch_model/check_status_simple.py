#!/usr/bin/env python3
"""
Simple Status Checker for KG Pipeline V2

Check the status of the pipeline and stages.
Run this file directly from IDE.
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineBatch, PipelineNode, StageResult, StageCompletion
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_pipeline_status(batch_id: int = None):
    """
    Check the status of the pipeline
    
    Args:
        batch_id: Specific batch ID to check (None for all batches)
        
    Returns:
        Dict containing status information
    """
    try:
        logger.info("📊 Checking KG Pipeline V2 status...")
        
        session: Session = get_session()
        coordinator = PipelineCoordinator(session)
        
        # Get total nodes
        query = session.query(PipelineNode)
        if batch_id:
            query = query.filter(PipelineNode.batch_id == batch_id)
        
        total_nodes = query.count()
        logger.info(f"Total nodes in pipeline: {total_nodes}")
        
        if total_nodes == 0:
            logger.info("No nodes found in the pipeline. Please load data first.")
            return {"total_nodes": 0, "stages": {}}
        
        # Check each stage
        stage_status = {}
        for stage_name in coordinator.stage_order:
            completed_count = session.query(StageCompletion).filter(
                and_(
                    StageCompletion.stage_name == stage_name,
                    StageCompletion.status == 'completed'
                )
            ).count()
            
            failed_count = session.query(StageCompletion).filter(
                and_(
                    StageCompletion.stage_name == stage_name,
                    StageCompletion.status == 'failed'
                )
            ).count()
            
            pending_count = total_nodes - completed_count - failed_count
            
            stage_status[stage_name] = {
                'completed': completed_count,
                'failed': failed_count,
                'pending': pending_count,
                'total': total_nodes
            }
            
            logger.info(f"Stage '{stage_name}':")
            logger.info(f"  - Completed: {completed_count}/{total_nodes}")
            logger.info(f"  - Pending: {pending_count}/{total_nodes}")
            logger.info(f"  - Failed: {failed_count}/{total_nodes}")
            
            if failed_count > 0:
                failed_nodes = session.query(StageCompletion.node_id, StageCompletion.error_message).filter(
                    and_(
                        StageCompletion.stage_name == stage_name,
                        StageCompletion.status == 'failed'
                    )
                ).limit(5).all()
                
                logger.warning(f"  First 5 failed nodes for stage '{stage_name}':")
                for node_id, error_msg in failed_nodes:
                    logger.warning(f"    - Node ID: {node_id}, Error: {error_msg[:100]}...")
        
        # Check batches
        batches = session.query(PipelineBatch).all()
        logger.info(f"\n📦 Batches: {len(batches)}")
        for batch in batches:
            logger.info(f"  - Batch {batch.id}: {batch.batch_name} ({batch.status})")
            logger.info(f"    Nodes: {batch.total_nodes}, Processed: {batch.processed_nodes}, Failed: {batch.failed_nodes}")
        
        session.close()
        logger.info("🎉 Pipeline status check complete!")
        
        return {
            "total_nodes": total_nodes,
            "stages": stage_status,
            "batches": len(batches)
        }
        
    except Exception as e:
        logger.error(f"❌ Error checking pipeline status: {str(e)}")
        return {"error": str(e)}


if __name__ == '__main__':
    """
    Run this file directly from IDE to check pipeline status
    """
    print("📊 KG Pipeline V2 - Check Status")
    print("=" * 50)
    
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
    
    print(f"\n🔄 Checking status...")
    print(f"   Batch ID: {batch_id}")
    
    try:
        status = check_pipeline_status(batch_id)
        
        if "error" in status:
            print(f"❌ Error checking status: {status['error']}")
            exit(1)
        else:
            print(f"✅ Status check completed!")
            print(f"   Total nodes: {status['total_nodes']}")
            print(f"   Batches: {status['batches']}")
            
    except Exception as e:
        print(f"❌ Error checking status: {str(e)}")
        exit(1)
