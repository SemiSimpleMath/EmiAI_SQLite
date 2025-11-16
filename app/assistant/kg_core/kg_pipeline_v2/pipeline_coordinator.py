"""
Pipeline Coordinator for KG Pipeline V2

Manages independent stage processing with:
- Stage coordination and dependency management
- Data persistence and retrieval
- Error handling and recovery
- Progress tracking
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.base import get_session
from .database_schema import (
    PipelineBatch, PipelineChunk, PipelineEdge, StageResult, StageCompletion,
    FactExtractionResult, ParserResult, MetadataResult, MergeResult, TaxonomyResult
)

logger = logging.getLogger(__name__)


class PipelineCoordinator:
    """Coordinates independent stage processing"""
    
    def __init__(self, session: Session = None):
        self.session = session or get_session()
        
        # Define stage dependencies - FIXED ORDER: 0→1→2→3→4→5
        self.stage_dependencies = {
            'conversation_boundary': [],  # Stage 0: No dependencies
            'parser': ['conversation_boundary'],  # Stage 1: Needs Stage 0
            'fact_extraction': ['parser'],  # Stage 2: Needs Stage 1  
            'metadata': ['fact_extraction'],  # Stage 3: Needs Stage 2
            'merge': ['metadata'],  # Stage 4: Needs Stage 3
            'taxonomy': ['merge']  # Stage 5: Needs Stage 4
        }
        
        # Define stage order - FIXED: 0→1→2→3→4→5
        self.stage_order = [
            'conversation_boundary',  # Stage 0
            'parser',                 # Stage 1  
            'fact_extraction',        # Stage 2
            'metadata',               # Stage 3
            'merge',                  # Stage 4
            'taxonomy'                # Stage 5
        ]
    
    def create_batch(self, batch_name: str, metadata: Dict = None) -> PipelineBatch:
        """Create a new processing batch"""
        batch = PipelineBatch(
            batch_name=batch_name,
            status='pending',
            metadata=metadata or {}
        )
        self.session.add(batch)
        self.session.commit()
        return batch
    
    def add_node_to_batch(self, batch_id: int, node_data: Dict) -> PipelineChunk:
        """Add a chunk to a batch for processing"""
        node = PipelineChunk(
            batch_id=batch_id,
            label=node_data['label'],
            node_type=node_data['node_type'],
            original_sentence=node_data.get('original_sentence'),
            conversation_id=node_data.get('conversation_id'),
            message_id=node_data.get('message_id'),
            data_source=node_data.get('data_source'),
            original_timestamp=node_data.get('original_timestamp')
        )
        self.session.add(node)
        self.session.commit()
        return node
    
    def add_edge_to_batch(self, batch_id: int, edge_data: Dict) -> PipelineEdge:
        """Add an edge to a batch for processing"""
        edge = PipelineEdge(
            batch_id=batch_id,
            source_node_id=edge_data['source_node_id'],
            target_node_id=edge_data['target_node_id'],
            edge_type=edge_data.get('edge_type'),
            original_sentence=edge_data.get('original_sentence'),
            conversation_id=edge_data.get('conversation_id'),
            message_id=edge_data.get('message_id')
        )
        self.session.add(edge)
        self.session.commit()
        return edge
    
    def get_nodes_for_stage(self, stage_name: str, batch_id: int = None) -> List[PipelineChunk]:
        """Get chunks that are ready for a specific stage"""
        query = self.session.query(PipelineChunk)
        
        if batch_id:
            query = query.filter(PipelineChunk.batch_id == batch_id)
        
        # Check if stage has dependencies
        dependencies = self.stage_dependencies.get(stage_name, [])
        
        if dependencies:
            # Only return nodes where all dependencies are complete
            for dep in dependencies:
                query = query.join(
                    StageCompletion,
                    and_(
                        StageCompletion.chunk_id == PipelineChunk.id,
                        StageCompletion.stage_name == dep,
                        StageCompletion.status == 'completed'
                    )
                )
        
        # Exclude nodes already processed for this stage
        query = query.filter(
            ~PipelineChunk.id.in_(
                self.session.query(StageCompletion.chunk_id)
                .filter(StageCompletion.stage_name == stage_name)
            )
        )
        
        return query.all()
    
    def get_stage_result(self, node_id: str, stage_name: str) -> Optional[Dict]:
        """Get the result from a specific stage for a node"""
        result = self.session.query(StageResult).filter(
            and_(
                StageResult.chunk_id == node_id,
                StageResult.stage_name == stage_name
            )
        ).first()
        
        return result.result_data if result else None
    
    def get_full_node_data_with_stage_results(self, node_id: str) -> Dict[str, Any]:
        """
        Get complete node data including all previous stage results
        
        Args:
            node_id: ID of the node to get data for
            
        Returns:
            Dict containing node data plus all previous stage results
        """
        # Get the base node data
        node = self.session.query(PipelineChunk).filter(PipelineChunk.id == node_id).first()
        if not node:
            return {}
        
        # Start with basic node data
        node_data = {
            'id': str(node.id),
            'label': node.label,
            'node_type': node.node_type,
            'original_sentence': node.original_sentence,
            'conversation_id': node.conversation_id,
            'message_id': node.message_id,
            'data_source': node.data_source,
            'original_timestamp': node.original_timestamp.isoformat() if node.original_timestamp else None,
            'conversation_content': node.original_sentence  # For stages that need conversation content
        }
        
        # Add results from all completed stages
        for stage in self.stage_order:
            result = self.get_stage_result(str(node.id), stage)
            if result:
                node_data[f'{stage}_result'] = result
        
        return node_data
    
    def get_prerequisite_results(self, node_id: str, stage_name: str) -> Dict[str, Any]:
        """
        Get results from prerequisite stages for a given stage
        
        Args:
            node_id: ID of the node
            stage_name: Name of the current stage
            
        Returns:
            Dict containing results from prerequisite stages
        """
        prerequisites = {}
        dependencies = self.stage_dependencies.get(stage_name, [])
        
        for dep_stage in dependencies:
            result = self.get_stage_result(str(node_id), dep_stage)
            if result:
                prerequisites[dep_stage] = result
        
        return prerequisites
    
    def save_stage_result(self, chunk_id: str, stage_name: str, result_data: Dict, 
                         processing_time: float = None, agent_version: str = None) -> StageResult:
        """Save the result from a stage"""
        result = StageResult(
            chunk_id=chunk_id,
            stage_name=stage_name,
            result_data=result_data,
            processing_time=processing_time,
            agent_version=agent_version
        )
        self.session.add(result)
        self.session.commit()
        return result
    
    def mark_stage_complete(self, chunk_id: str, stage_name: str) -> None:
        """Mark a stage as completed for a chunk"""
        completion = self.session.query(StageCompletion).filter(
            and_(
                StageCompletion.chunk_id == chunk_id,
                StageCompletion.stage_name == stage_name
            )
        ).first()
        
        if completion:
            completion.status = 'completed'
            completion.completed_at = datetime.utcnow()
        else:
            completion = StageCompletion(
                chunk_id=chunk_id,
                stage_name=stage_name,
                status='completed',
                completed_at=datetime.utcnow()
            )
            self.session.add(completion)
        
        self.session.commit()
    
    def mark_stage_failed(self, chunk_id: str, stage_name: str, error_message: str) -> None:
        """Mark a stage as failed for a chunk"""
        completion = self.session.query(StageCompletion).filter(
            and_(
                StageCompletion.chunk_id == chunk_id,
                StageCompletion.stage_name == stage_name
            )
        ).first()
        
        if completion:
            completion.status = 'failed'
            completion.error_message = error_message
            completion.retry_count += 1
        else:
            completion = StageCompletion(
                chunk_id=chunk_id,
                stage_name=stage_name,
                status='failed',
                error_message=error_message,
                retry_count=1
            )
            self.session.add(completion)
        
        self.session.commit()
    
    def get_batch_status(self, batch_id: int) -> Dict[str, Any]:
        """Get the status of a batch"""
        batch = self.session.query(PipelineBatch).filter(
            PipelineBatch.id == batch_id
        ).first()
        
        if not batch:
            return {"error": "Batch not found"}
        
        # Get stage completion counts
        stage_counts = {}
        for stage in self.stage_order:
            completed = self.session.query(StageCompletion).filter(
                and_(
                    StageCompletion.stage_name == stage,
                    StageCompletion.status == 'completed',
                    StageCompletion.chunk_id.in_(
                        self.session.query(PipelineChunk.id)
                        .filter(PipelineChunk.batch_id == batch_id)
                    )
                )
            ).count()
            
            failed = self.session.query(StageCompletion).filter(
                and_(
                    StageCompletion.stage_name == stage,
                    StageCompletion.status == 'failed',
                    StageCompletion.chunk_id.in_(
                        self.session.query(PipelineChunk.id)
                        .filter(PipelineChunk.batch_id == batch_id)
                    )
                )
            ).count()
            
            stage_counts[stage] = {
                'completed': completed,
                'failed': failed
            }
        
        return {
            'batch_id': batch.id,
            'batch_name': batch.batch_name,
            'status': batch.status,
            'total_nodes': batch.total_nodes,
            'processed_nodes': batch.processed_nodes,
            'failed_nodes': batch.failed_nodes,
            'stage_counts': stage_counts,
            'created_at': batch.created_at,
            'started_at': batch.started_at,
            'completed_at': batch.completed_at
        }
    
    def get_failed_nodes(self, stage_name: str, batch_id: int = None) -> List[PipelineChunk]:
        """Get nodes that failed at a specific stage"""
        query = self.session.query(PipelineChunk).join(
            StageCompletion,
            and_(
                StageCompletion.chunk_id == PipelineChunk.id,
                StageCompletion.stage_name == stage_name,
                StageCompletion.status == 'failed'
            )
        )
        
        if batch_id:
            query = query.filter(PipelineChunk.batch_id == batch_id)
        
        return query.all()
    
    def retry_failed_stage(self, stage_name: str, batch_id: int = None) -> int:
        """Reset failed nodes for retry"""
        failed_nodes = self.get_failed_nodes(stage_name, batch_id)
        
        for node in failed_nodes:
            # Reset the stage completion status
            completion = self.session.query(StageCompletion).filter(
                and_(
                    StageCompletion.chunk_id == node.id,
                    StageCompletion.stage_name == stage_name
                )
            ).first()
            
            if completion:
                completion.status = 'pending'
                completion.error_message = None
                completion.started_at = None
                completion.completed_at = None
        
        self.session.commit()
        return len(failed_nodes)
    
    def save_node_data(self, node_data: Dict[str, Any]) -> None:
        """
        Save node data to the pipeline database
        
        Args:
            node_data: Dictionary containing node information
        """
        try:
            # Create PipelineChunk from data
            pipeline_node = PipelineChunk(
                id=node_data['id'],
                batch_id=node_data['batch_id'],
                label=node_data['label'],
                node_type=node_data['node_type'],
                original_message_id=node_data.get('original_message_id'),
                original_sentence=node_data.get('original_sentence'),
                source=node_data.get('source'),
                role=node_data.get('role'),
                timestamp=node_data.get('timestamp'),
                current_data=node_data  # Store all data as JSON
            )
            
            self.session.add(pipeline_node)
            self.session.flush()  # Ensure ID is generated
            
            logger.debug(f"Saved node: {node_data['id']}")
            
        except Exception as e:
            logger.error(f"Error saving node data: {e}")
            raise
    
    def update_batch_status(self, batch_id: int, status: str) -> None:
        """
        Update batch status
        
        Args:
            batch_id: ID of the batch to update
            status: New status for the batch
        """
        try:
            batch = self.session.query(PipelineBatch).filter(PipelineBatch.id == batch_id).first()
            if batch:
                batch.status = status
                batch.updated_at = datetime.utcnow()
                self.session.commit()
                logger.info(f"Updated batch {batch_id} status to: {status}")
            else:
                logger.warning(f"Batch {batch_id} not found")
                
        except Exception as e:
            logger.error(f"Error updating batch status: {e}")
            raise
