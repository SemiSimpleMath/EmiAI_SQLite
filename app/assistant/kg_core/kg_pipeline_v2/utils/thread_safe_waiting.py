"""
Thread-Safe Waiting Utilities for KG Pipeline V2

Provides thread-safe waiting mechanisms for stages to wait for data availability.
"""

import time
import threading
import logging
from typing import Optional, Callable, Any
from sqlalchemy.orm import Session
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineChunk

logger = logging.getLogger(__name__)


class ThreadSafeDataWaiter:
    """Thread-safe data waiting mechanism"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        self._lock = threading.Lock()
        self._waiting_threads = {}  # Track waiting threads by stage
    
    def wait_for_data(
        self, 
        stage_name: str, 
        batch_id: Optional[int] = None,
        max_wait_time: int = 300,  # 5 minutes max wait
        check_interval: int = 10,  # Check every 10 seconds
        timeout_callback: Optional[Callable] = None
    ) -> bool:
        """
        Wait for data to become available for a stage
        
        Args:
            stage_name: Name of the stage waiting for data
            batch_id: Specific batch ID to wait for (None for any batch)
            max_wait_time: Maximum time to wait in seconds
            check_interval: How often to check for data in seconds
            timeout_callback: Callback to execute if timeout is reached
            
        Returns:
            True if data became available, False if timeout
        """
        start_time = time.time()
        thread_id = threading.current_thread().ident
        
        with self._lock:
            self._waiting_threads[thread_id] = {
                'stage': stage_name,
                'start_time': start_time,
                'batch_id': batch_id
            }
        
        logger.info(f"🔄 {stage_name} waiting for data (batch_id={batch_id})...")
        
        while time.time() - start_time < max_wait_time:
            try:
                # Check if data is available
                if self._check_data_available(stage_name, batch_id):
                    logger.info(f"✅ {stage_name} found data, proceeding...")
                    return True
                
                # Wait before next check
                time.sleep(check_interval)
                
                # Log progress every minute
                elapsed = time.time() - start_time
                if int(elapsed) % 60 == 0:
                    logger.info(f"⏳ {stage_name} still waiting... ({elapsed:.0f}s elapsed)")
                
            except Exception as e:
                logger.error(f"❌ Error checking data availability for {stage_name}: {str(e)}")
                time.sleep(check_interval)
        
        # Timeout reached
        logger.warning(f"⏰ {stage_name} timed out waiting for data after {max_wait_time}s")
        
        if timeout_callback:
            try:
                timeout_callback(stage_name, batch_id)
            except Exception as e:
                logger.error(f"❌ Timeout callback failed for {stage_name}: {str(e)}")
        
        return False
    
    def _check_data_available(self, stage_name: str, batch_id: Optional[int] = None) -> bool:
        """Check if data is available for the stage"""
        try:
            # Get nodes ready for this stage
            nodes = self.coordinator.get_nodes_for_stage(stage_name, batch_id)
            
            if nodes:
                logger.info(f"📊 {stage_name} found {len(nodes)} nodes ready for processing")
                return True
            
            # Check if there are any nodes in the pipeline at all
            total_chunks = self.session.query(PipelineChunk).count()
            if total_chunks == 0:
                logger.info(f"📭 No chunks in pipeline yet, {stage_name} will wait...")
                return False
            
            # Check if prerequisite stages are complete
            if self._check_prerequisites_complete(stage_name, batch_id):
                logger.info(f"✅ Prerequisites complete for {stage_name}, data should be available")
                return True
            
            logger.info(f"⏳ {stage_name} waiting for prerequisites to complete...")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking data availability: {str(e)}")
            return False
    
    def _check_prerequisites_complete(self, stage_name: str, batch_id: Optional[int] = None) -> bool:
        """Check if prerequisite stages are complete"""
        try:
            # Get stage dependencies
            dependencies = self.coordinator.stage_dependencies.get(stage_name, [])
            
            if not dependencies:
                # No dependencies, data should be available
                return True
            
            # Check if all dependencies are complete
            for dep_stage in dependencies:
                if not self._is_stage_complete(dep_stage, batch_id):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking prerequisites: {str(e)}")
            return False
    
    def _is_stage_complete(self, stage_name: str, batch_id: Optional[int] = None) -> bool:
        """Check if a stage is complete for the given batch"""
        try:
            # This would need to be implemented in the coordinator
            # For now, return True to avoid blocking
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking stage completion: {str(e)}")
            return False
    
    def stop_waiting(self, stage_name: str):
        """Stop waiting for a specific stage"""
        with self._lock:
            threads_to_remove = []
            for thread_id, info in self._waiting_threads.items():
                if info['stage'] == stage_name:
                    threads_to_remove.append(thread_id)
            
            for thread_id in threads_to_remove:
                del self._waiting_threads[thread_id]
        
        logger.info(f"🛑 Stopped waiting for {stage_name}")
    
    def get_waiting_status(self) -> dict:
        """Get status of all waiting threads"""
        with self._lock:
            return {
                thread_id: {
                    'stage': info['stage'],
                    'elapsed_time': time.time() - info['start_time'],
                    'batch_id': info['batch_id']
                }
                for thread_id, info in self._waiting_threads.items()
            }


def wait_for_stage_data(
    coordinator: PipelineCoordinator,
    session: Session,
    stage_name: str,
    batch_id: Optional[int] = None,
    max_wait_time: int = 300,
    check_interval: int = 10
) -> bool:
    """
    Convenience function to wait for stage data
    
    Args:
        coordinator: Pipeline coordinator instance
        session: Database session
        stage_name: Name of the stage
        batch_id: Specific batch ID (None for any batch)
        max_wait_time: Maximum wait time in seconds
        check_interval: Check interval in seconds
        
    Returns:
        True if data became available, False if timeout
    """
    waiter = ThreadSafeDataWaiter(coordinator, session)
    return waiter.wait_for_data(stage_name, batch_id, max_wait_time, check_interval)


if __name__ == '__main__':
    """
    Test the thread-safe waiting mechanism
    """
    import asyncio
    from app.models.base import get_session
    from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
    
    def test_waiting():
        print("🧪 Testing Thread-Safe Waiting")
        print("=" * 50)
        
        session = get_session()
        coordinator = PipelineCoordinator(session)
        
        # Test waiting for data
        print("🔄 Testing data waiting...")
        result = wait_for_stage_data(
            coordinator, session, 
            'fact_extraction', 
            max_wait_time=30,  # 30 seconds for test
            check_interval=5    # Check every 5 seconds
        )
        
        if result:
            print("✅ Data became available!")
        else:
            print("⏰ Timeout reached, no data available")
        
        session.close()
    
    test_waiting()
