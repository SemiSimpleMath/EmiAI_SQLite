"""
Taxonomy Stage Processor

Processes merged nodes and edges to classify them into taxonomy using the taxonomy classifier.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
    PipelineChunk, TaxonomyResult, StageResult, StageCompletion
)
from app.assistant.kg_core.kg_pipeline_v2.utils import wait_for_stage_data

logger = logging.getLogger(__name__)


class TaxonomyProcessor:
    """Processes taxonomy stage"""
    
    def __init__(self, coordinator: PipelineCoordinator, session: Session):
        self.coordinator = coordinator
        self.session = session
        self.agent = DI.agent_factory.create_agent("knowledge_graph_add::taxonomy_classifier")
    
    def wait_for_data(self, batch_id: int = None, max_wait_time: int = 300) -> bool:
        """
        Wait for data to become available for taxonomy processing
        
        Args:
            batch_id: Specific batch ID to wait for (None for any batch)
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if data became available, False if timeout
        """
        logger.info(f"🔄 Taxonomy waiting for data (batch_id={batch_id})...")
        return wait_for_stage_data(
            self.coordinator, 
            self.session, 
            'taxonomy', 
            batch_id, 
            max_wait_time
        )
    
    async def process(self, node_data: Dict[str, Any], facts: Dict[str, Any], parsed: Dict[str, Any], metadata: Dict[str, Any], merged: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process taxonomy classification for a single node
        
        Args:
            node_data: Complete node data
            facts: Fact extraction results
            parsed: Parser results
            metadata: Metadata results
            merged: Merge results
            
        Returns:
            Dict containing taxonomy classifications
        """
        try:
            # Combine all input data
            combined_content = f"""
            Original: {node_data.get('conversation_content', '')}
            
            Extracted Facts: {facts.get('extracted_facts', '')}
            
            Parsed Entities: {parsed.get('parsed_entities', '')}
            Parsed Relationships: {parsed.get('parsed_relationships', '')}
            
            Metadata: {metadata.get('metadata', '')}
            
            Merged Nodes: {merged.get('merged_nodes', '')}
            Merged Edges: {merged.get('merged_edges', '')}
            """
            
            # Create message for agent
            message = Message(
                role="user",
                content=combined_content
            )
            
            # Call taxonomy agent
            logger.info(f"Classifying taxonomy for node: {node_data.get('id')}")
            result = await self.agent.process(message)
            
            # Parse agent response
            if hasattr(result, 'content'):
                taxonomy_content = result.content
            else:
                taxonomy_content = str(result)
            
            # Store result in database using coordinator
            self.coordinator.save_stage_result(
                node_data['id'],
                'taxonomy',
                {
                    'taxonomy_classifications': taxonomy_content,
                    'agent_response': result
                }
            )
            
            # Mark stage as complete
            self.coordinator.mark_stage_complete(node_data['id'], 'taxonomy')
            
            logger.info(f"✅ Taxonomy classification completed for node {node_data['id']}")
            
            return {
                "taxonomy_classifications": taxonomy_content,
                "agent_response": result
            }
            
        except Exception as e:
            logger.error(f"❌ Taxonomy classification failed for node {node_data.get('id')}: {str(e)}")
            
            # Mark as failed
            self.coordinator.mark_stage_failed(node_data['id'], 'taxonomy', str(e))
            
            raise e


if __name__ == '__main__':
    """
    Test taxonomy stage independently
    """
    import asyncio
    from app.models.base import get_session
    from app.assistant.kg_core.kg_pipeline_v2.pipeline_coordinator import PipelineCoordinator
    
    async def test_taxonomy():
        print("🧪 Testing Taxonomy Stage")
        print("=" * 50)
        
        session = get_session()
        coordinator = PipelineCoordinator(session)
        processor = TaxonomyProcessor(coordinator, session)
        
        # Test waiting for data
        print("🔄 Testing data waiting...")
        data_available = processor.wait_for_data(batch_id=None, max_wait_time=30)
        
        if not data_available:
            print("❌ No data available for processing")
            print("❌ Cannot proceed without data")
            exit(1)
        else:
            print("✅ Data available, processing...")
            # In real usage, you would process the available data here
        
        session.close()
    
    asyncio.run(test_taxonomy())
