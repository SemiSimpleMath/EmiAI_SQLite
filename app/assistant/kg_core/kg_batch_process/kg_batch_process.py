#!/usr/bin/env python3
"""
KG Batch Processing Pipeline

High-performance parallel and batch processing for knowledge graph ingestion.
Combines parallel processing with OpenAI Batch API for maximum throughput and cost efficiency.

Key Features:
- Parallel processing (5-10 pipelines)
- OpenAI Batch API integration (50% cost savings)
- Smart load balancing
- Fault tolerance and recovery
- Progress tracking and monitoring

Architecture:
- Main coordinator manages parallel pipelines
- Each pipeline processes independent conversation chunks
- Heavy operations (fact extraction, parsing) use batch API
- Real-time operations (merging, classification) use direct API
- Database operations are pipeline-isolated
"""

import json
import asyncio
import multiprocessing
import threading
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import uuid
import logging

# Core imports
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.knowledge_graph_utils import KnowledgeGraphUtils
from app.assistant.kg_core.knowledge_graph_db import Edge, Node
from app.models.base import get_session
from sqlalchemy import select, func

# Pipeline imports
from app.assistant.database.db_handler import UnifiedLog
from app.assistant.database.processed_entity_log import ProcessedEntityLog
from app.assistant.kg_core.log_preprocessing import read_unprocessed_logs_from_processed_entity_log

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    """Configuration for batch processing pipeline"""
    # Parallel processing
    num_pipelines: int = 8
    max_conversations_per_pipeline: int = 10
    
    # Batch API settings
    use_batch_api: bool = True
    batch_timeout_hours: int = 24
    batch_chunk_size: int = 20  # sentences per batch
    
    # Real-time processing
    real_time_chunk_size: int = 5  # sentences for real-time operations
    
    # Database settings
    commit_frequency: int = 5  # commit every N chunks
    
    # Performance monitoring
    enable_progress_tracking: bool = True
    enable_performance_monitoring: bool = True


@dataclass
class ConversationChunk:
    """Represents a chunk of conversations for processing"""
    chunk_id: str
    conversations: List[Dict[str, Any]]
    pipeline_id: int
    priority: int = 1  # 1=high, 2=medium, 3=low


@dataclass
class ProcessingResult:
    """Result of processing a conversation chunk"""
    chunk_id: str
    pipeline_id: int
    success: bool
    nodes_created: int
    edges_created: int
    processing_time: float
    error_message: Optional[str] = None


class ProgressTracker:
    """Tracks progress across all parallel pipelines"""
    
    def __init__(self, total_conversations: int):
        self.total_conversations = total_conversations
        self.completed_conversations = 0
        self.failed_conversations = 0
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.pipeline_stats = {}
    
    def update_progress(self, pipeline_id: int, completed: int, failed: int = 0):
        """Update progress for a specific pipeline"""
        with self.lock:
            self.completed_conversations += completed
            self.failed_conversations += failed
            
            if pipeline_id not in self.pipeline_stats:
                self.pipeline_stats[pipeline_id] = {'completed': 0, 'failed': 0}
            
            self.pipeline_stats[pipeline_id]['completed'] += completed
            self.pipeline_stats[pipeline_id]['failed'] += failed
            
            # Calculate progress percentage
            total_processed = self.completed_conversations + self.failed_conversations
            progress_pct = (total_processed / self.total_conversations) * 100
            
            # Calculate ETA
            elapsed_time = time.time() - self.start_time
            if total_processed > 0:
                eta_seconds = (elapsed_time / total_processed) * (self.total_conversations - total_processed)
                eta_minutes = eta_seconds / 60
            else:
                eta_minutes = 0
            
            logger.info(f"Progress: {progress_pct:.1f}% ({total_processed}/{self.total_conversations}) | "
                       f"Pipeline {pipeline_id}: +{completed} completed, +{failed} failed | "
                       f"ETA: {eta_minutes:.1f} minutes")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get processing summary"""
        with self.lock:
            elapsed_time = time.time() - self.start_time
            return {
                'total_conversations': self.total_conversations,
                'completed_conversations': self.completed_conversations,
                'failed_conversations': self.failed_conversations,
                'success_rate': (self.completed_conversations / self.total_conversations) * 100,
                'elapsed_time_minutes': elapsed_time / 60,
                'pipeline_stats': self.pipeline_stats.copy()
            }


class BatchAPIManager:
    """Manages OpenAI Batch API operations"""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.batch_jobs = {}
        self.batch_results = {}
    
    async def submit_batch_job(self, job_id: str, inputs: List[Dict[str, Any]], agent_type: str) -> str:
        """Submit a batch job to OpenAI Batch API"""
        # TODO: Implement OpenAI Batch API submission
        # This would create a batch job with the inputs and return a batch ID
        logger.info(f"Submitting batch job {job_id} for {agent_type} with {len(inputs)} inputs")
        
        # Placeholder implementation
        batch_id = f"batch_{job_id}_{int(time.time())}"
        self.batch_jobs[batch_id] = {
            'job_id': job_id,
            'agent_type': agent_type,
            'inputs': inputs,
            'status': 'submitted',
            'submitted_at': datetime.utcnow()
        }
        
        return batch_id
    
    async def check_batch_status(self, batch_id: str) -> str:
        """Check the status of a batch job"""
        if batch_id not in self.batch_jobs:
            return 'not_found'
        
        # TODO: Implement actual batch status checking
        # For now, simulate completion after some time
        job = self.batch_jobs[batch_id]
        elapsed = (datetime.utcnow() - job['submitted_at']).total_seconds()
        
        if elapsed > 300:  # 5 minutes simulation
            job['status'] = 'completed'
            return 'completed'
        else:
            return 'running'
    
    async def get_batch_results(self, batch_id: str) -> List[Dict[str, Any]]:
        """Get results from a completed batch job"""
        if batch_id not in self.batch_jobs:
            return []
        
        job = self.batch_jobs[batch_id]
        if job['status'] != 'completed':
            return []
        
        # TODO: Implement actual batch result retrieval
        # For now, return placeholder results
        results = []
        for i, input_data in enumerate(job['inputs']):
            results.append({
                'input_index': i,
                'result': f"Batch result for {job['agent_type']} input {i}",
                'success': True
            })
        
        return results


class ParallelPipeline:
    """Individual pipeline for processing conversation chunks"""
    
    def __init__(self, pipeline_id: int, config: ProcessingConfig, progress_tracker: ProgressTracker):
        self.pipeline_id = pipeline_id
        self.config = config
        self.progress_tracker = progress_tracker
        self.batch_manager = BatchAPIManager(config)
        
        # Initialize agents for this pipeline
        self.fact_extractor_agent = DI.agent_factory.create_agent("knowledge_graph_add::fact_extractor")
        self.parser_agent = DI.agent_factory.create_agent("knowledge_graph_add::parser")
        self.meta_data_agent = DI.agent_factory.create_agent("knowledge_graph_add::meta_data_add")
        self.merge_agent = DI.agent_factory.create_agent("knowledge_graph_add::node_merger")
        self.node_data_merger = DI.agent_factory.create_agent("knowledge_graph_add::node_data_merger")
        self.edge_merge_agent = DI.agent_factory.create_agent("knowledge_graph_add::edge_merger")
        
        # Database session for this pipeline
        self.session = get_session()
        self.kg_utils = KnowledgeGraphUtils(self.session)
    
    async def process_conversation_chunk(self, chunk: ConversationChunk) -> ProcessingResult:
        """Process a single conversation chunk"""
        start_time = time.time()
        nodes_created = 0
        edges_created = 0
        
        try:
            logger.info(f"Pipeline {self.pipeline_id}: Processing chunk {chunk.chunk_id} with {len(chunk.conversations)} conversations")
            
            for conv in chunk.conversations:
                # Process each conversation
                result = await self.process_single_conversation(conv)
                nodes_created += result.get('nodes_created', 0)
                edges_created += result.get('edges_created', 0)
            
            processing_time = time.time() - start_time
            self.progress_tracker.update_progress(self.pipeline_id, len(chunk.conversations))
            
            return ProcessingResult(
                chunk_id=chunk.chunk_id,
                pipeline_id=self.pipeline_id,
                success=True,
                nodes_created=nodes_created,
                edges_created=edges_created,
                processing_time=processing_time
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Pipeline {self.pipeline_id}: Error processing chunk {chunk.chunk_id}: {str(e)}")
            self.progress_tracker.update_progress(self.pipeline_id, 0, len(chunk.conversations))
            
            return ProcessingResult(
                chunk_id=chunk.chunk_id,
                pipeline_id=self.pipeline_id,
                success=False,
                nodes_created=0,
                edges_created=0,
                processing_time=processing_time,
                error_message=str(e)
            )
    
    async def process_single_conversation(self, conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single conversation using the pipeline"""
        # TODO: Implement the actual conversation processing logic
        # This would be similar to the existing pipeline but optimized for parallel processing
        
        # Placeholder implementation
        logger.info(f"Pipeline {self.pipeline_id}: Processing conversation {conversation.get('id', 'unknown')}")
        
        # Simulate processing time
        await asyncio.sleep(0.1)
        
        return {
            'nodes_created': 2,
            'edges_created': 1,
            'success': True
        }
    
    def cleanup(self):
        """Cleanup resources for this pipeline"""
        if self.session:
            self.session.close()


class KGBatchProcessor:
    """Main coordinator for parallel batch processing"""
    
    def __init__(self, config: ProcessingConfig = None):
        self.config = config or ProcessingConfig()
        self.progress_tracker = None
        self.pipelines = []
        self.batch_manager = BatchAPIManager(self.config)
    
    async def process_logs(self, log_context_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Main entry point for processing logs with parallel batch processing"""
        logger.info(f"Starting parallel batch processing with {self.config.num_pipelines} pipelines")
        
        # Initialize progress tracker
        total_conversations = len(log_context_items)
        self.progress_tracker = ProgressTracker(total_conversations)
        
        # Split conversations into chunks for parallel processing
        conversation_chunks = self._split_conversations_into_chunks(log_context_items)
        logger.info(f"Split {total_conversations} conversations into {len(conversation_chunks)} chunks")
        
        # Start parallel processing
        start_time = time.time()
        results = await self._run_parallel_processing(conversation_chunks)
        total_time = time.time() - start_time
        
        # Generate summary
        summary = self._generate_processing_summary(results, total_time)
        
        logger.info(f"Parallel batch processing completed in {total_time:.2f} seconds")
        return summary
    
    def _split_conversations_into_chunks(self, conversations: List[Dict[str, Any]]) -> List[ConversationChunk]:
        """Split conversations into chunks for parallel processing"""
        chunks = []
        conversations_per_chunk = self.config.max_conversations_per_pipeline
        
        for i in range(0, len(conversations), conversations_per_chunk):
            chunk_conversations = conversations[i:i + conversations_per_chunk]
            pipeline_id = (i // conversations_per_chunk) % self.config.num_pipelines
            
            chunk = ConversationChunk(
                chunk_id=f"chunk_{i}_{i + len(chunk_conversations)}",
                conversations=chunk_conversations,
                pipeline_id=pipeline_id
            )
            chunks.append(chunk)
        
        return chunks
    
    async def _run_parallel_processing(self, chunks: List[ConversationChunk]) -> List[ProcessingResult]:
        """Run parallel processing across multiple pipelines"""
        # Group chunks by pipeline
        pipeline_chunks = {}
        for chunk in chunks:
            if chunk.pipeline_id not in pipeline_chunks:
                pipeline_chunks[chunk.pipeline_id] = []
            pipeline_chunks[chunk.pipeline_id].append(chunk)
        
        # Create pipelines
        pipelines = []
        for pipeline_id in range(self.config.num_pipelines):
            if pipeline_id in pipeline_chunks:
                pipeline = ParallelPipeline(pipeline_id, self.config, self.progress_tracker)
                pipelines.append(pipeline)
        
        # Process chunks in parallel
        tasks = []
        for pipeline in pipelines:
            pipeline_chunks_for_pipeline = pipeline_chunks.get(pipeline.pipeline_id, [])
            for chunk in pipeline_chunks_for_pipeline:
                task = pipeline.process_conversation_chunk(chunk)
                tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Cleanup pipelines
        for pipeline in pipelines:
            pipeline.cleanup()
        
        # Filter out exceptions and return results
        valid_results = [r for r in results if isinstance(r, ProcessingResult)]
        return valid_results
    
    def _generate_processing_summary(self, results: List[ProcessingResult], total_time: float) -> Dict[str, Any]:
        """Generate processing summary"""
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        total_nodes = sum(r.nodes_created for r in successful_results)
        total_edges = sum(r.edges_created for r in successful_results)
        
        summary = {
            'total_processing_time': total_time,
            'total_chunks_processed': len(results),
            'successful_chunks': len(successful_results),
            'failed_chunks': len(failed_results),
            'total_nodes_created': total_nodes,
            'total_edges_created': total_edges,
            'nodes_per_second': total_nodes / total_time if total_time > 0 else 0,
            'edges_per_second': total_edges / total_time if total_time > 0 else 0,
            'pipeline_performance': self.progress_tracker.get_summary() if self.progress_tracker else {},
            'errors': [r.error_message for r in failed_results if r.error_message]
        }
        
        return summary


# Main entry point
async def main():
    """Main entry point for testing"""
    config = ProcessingConfig(
        num_pipelines=4,
        max_conversations_per_pipeline=5,
        use_batch_api=True
    )
    
    processor = KGBatchProcessor(config)
    
    # Mock data for testing
    mock_conversations = [
        {'id': f'conv_{i}', 'messages': [{'role': 'user', 'content': f'Message {i}'}]}
        for i in range(20)
    ]
    
    result = await processor.process_logs(mock_conversations)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

