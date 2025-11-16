"""
KG Explorer Pipeline Orchestrator

This orchestrator manages the sequential execution of the KG explorer pipeline:
1. Node Selector - Identifies promising nodes for exploration
2. Explorer - Discovers relationships and performs temporal reasoning
3. Reporter - Summarizes findings and suggests next steps
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_logger
from app.assistant.kg_core.knowledge_graph_db import Node

from app.assistant.kg_explorer_pipeline.data_models.pipeline_state import PipelineState, PipelineStage
from app.assistant.kg_explorer_pipeline.data_models.exploration_node import ExplorationNode
from app.assistant.kg_explorer_pipeline.data_models.exploration_result import ExplorationResult
from app.assistant.kg_explorer_pipeline.stages.node_selector import KGNodeSelector
from app.assistant.kg_explorer_pipeline.stages.explorer import KGExplorer
from app.assistant.kg_explorer_pipeline.stages.reporter import KGReporter
from app.assistant.kg_explorer_pipeline.utils.exploration_manager import ExplorationManager

logger = get_logger(__name__)

class KGExplorerPipelineOrchestrator:
    """
    Orchestrates the KG explorer pipeline execution.
    """
    
    def __init__(self):
        self.pipeline_id = str(uuid.uuid4())
        self.state = PipelineState(
            pipeline_id=self.pipeline_id,
            started_at=datetime.now(timezone.utc)
        )
        
        # Initialize pipeline stages
        self.node_selector = KGNodeSelector()
        self.explorer = KGExplorer()
        self.reporter = KGReporter()
        self.exploration_manager = ExplorationManager()
        
    def run_pipeline(self, exploration_config: Optional[Dict] = None, max_nodes: int = 5) -> PipelineState:
        """
        Run the complete KG explorer pipeline.
        
        Args:
            exploration_config: Configuration for exploration (focus areas, depth, etc.)
            max_nodes: Maximum number of nodes to explore
            
        Returns:
            PipelineState: Final state of the pipeline
        """
        print(f"🚀 [DEBUG] Starting KG Explorer Pipeline: {self.pipeline_id}")
        print(f"🔧 [DEBUG] Exploration config: {exploration_config}")
        print(f"🔧 [DEBUG] Max nodes: {max_nodes}")
        
        logger.info(f"🚀 Starting KG Explorer Pipeline: {self.pipeline_id}")
        
        try:
            # Stage 1: Node Selection
            print(f"🔍 [DEBUG] Stage 1: Starting node selection...")
            self.state.current_stage = PipelineStage.NODE_SELECTION
            selected_nodes = self._run_node_selection_stage(max_nodes, exploration_config)
            
            print(f"🔍 [DEBUG] Node selection completed. Selected {len(selected_nodes) if selected_nodes else 0} nodes")
            
            if not selected_nodes:
                print("⚠️ [DEBUG] No promising nodes found for exploration")
                logger.warning("⚠️ No promising nodes found for exploration")
                self.state.current_stage = PipelineStage.COMPLETED
                self.state.completed_at = datetime.now(timezone.utc)
                return self.state
            
            # Stage 2: Exploration
            print(f"🧠 [DEBUG] Stage 2: Starting exploration of {len(selected_nodes)} nodes...")
            self.state.current_stage = PipelineStage.EXPLORATION
            exploration_results = self._run_exploration_stage(selected_nodes, exploration_config)
            
            print(f"🧠 [DEBUG] Exploration completed. Got {len(exploration_results) if exploration_results else 0} results")
            
            # Stage 3: Reporting
            print(f"📊 [DEBUG] Stage 3: Starting reporting...")
            self.state.current_stage = PipelineStage.REPORTING
            final_report = self._run_reporting_stage(exploration_results)
            
            print(f"📊 [DEBUG] Reporting completed. Report keys: {list(final_report.keys()) if final_report else 'None'}")
            
            # Update final state
            self.state.current_stage = PipelineStage.COMPLETED
            self.state.completed_at = datetime.now(timezone.utc)
            self.state.final_report = final_report
            
            print(f"✅ [DEBUG] KG Explorer Pipeline completed successfully!")
            logger.info(f"✅ KG Explorer Pipeline completed: {self.pipeline_id}")
            return self.state
            
        except Exception as e:
            print(f"❌ [DEBUG] KG Explorer Pipeline failed: {e}")
            print(f"❌ [DEBUG] Exception type: {type(e).__name__}")
            import traceback
            print(f"❌ [DEBUG] Traceback: {traceback.format_exc()}")
            logger.error(f"❌ KG Explorer Pipeline failed: {e}")
            self.state.current_stage = PipelineStage.FAILED
            self.state.error_message = str(e)
            self.state.completed_at = datetime.now(timezone.utc)
            return self.state
    
    def _run_node_selection_stage(self, max_nodes: int, exploration_config: Optional[Dict] = None) -> List[ExplorationNode]:
        """
        Run the node selection stage to identify promising nodes for exploration.
        """
        print(f"🔍 [DEBUG] Running node selection stage (max_nodes={max_nodes})")
        logger.info(f"🔍 Running node selection stage (max_nodes={max_nodes})")
        
        try:
            # Get candidate nodes from the knowledge graph
            print(f"🔍 [DEBUG] Getting candidate nodes from knowledge graph...")
            candidate_nodes = self._get_candidate_nodes(max_nodes * 3, exploration_config)
            
            print(f"🔍 [DEBUG] Found {len(candidate_nodes) if candidate_nodes else 0} candidate nodes")
            
            if not candidate_nodes:
                print("⚠️ [DEBUG] No candidate nodes found")
                logger.warning("⚠️ No candidate nodes found")
                return []
            
            # Use node selector agent to choose the best candidates
            print(f"🔍 [DEBUG] Selecting promising nodes from candidates...")
            selected_nodes = self.node_selector.select_nodes(
                candidate_nodes, 
                max_nodes
            )
            
            print(f"🔍 [DEBUG] Selected {len(selected_nodes) if selected_nodes else 0} nodes for exploration")
            logger.info(f"✅ Selected {len(selected_nodes)} nodes for exploration")
            return selected_nodes
            
        except Exception as e:
            print(f"❌ [DEBUG] Node selection stage failed: {e}")
            print(f"❌ [DEBUG] Exception type: {type(e).__name__}")
            import traceback
            print(f"❌ [DEBUG] Traceback: {traceback.format_exc()}")
            logger.error(f"❌ Node selection stage failed: {e}")
            return []
    
    def _run_exploration_stage(self, selected_nodes: List[ExplorationNode], exploration_config: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Run the exploration stage to discover relationships and perform temporal reasoning.
        Returns list of dicts with structured actionable_recommendations from kg_explorer_manager.
        """
        print(f"🧠 [DEBUG] Running exploration stage for {len(selected_nodes)} nodes")
        logger.info(f"🧠 Running exploration stage for {len(selected_nodes)} nodes")
        
        exploration_results = []
        
        for i, node in enumerate(selected_nodes, 1):
            print(f"🧠 [DEBUG] Exploring node {i}/{len(selected_nodes)}: {node.label}")
            logger.info(f"🔍 Exploring node {i}/{len(selected_nodes)}: {node.label}")
            
            try:
                # Explore the node - returns structured dict with actionable_recommendations
                print(f"🧠 [DEBUG] Calling explorer.explore_node for {node.label}...")
                result = self.explorer.explore_node(node, exploration_config)
                
                # Result is a dict with: what_i_am_thinking, exploration_summary, actionable_recommendations
                recommendations = result.get('actionable_recommendations', []) if isinstance(result, dict) else []
                print(f"🧠 [DEBUG] Exploration result for {node.label}: {len(recommendations)} actionable recommendations")
                
                exploration_results.append(result)
                
                print(f"✅ [DEBUG] Explored node {node.label}: {len(recommendations)} recommendations")
                logger.info(f"✅ Explored node {node.label}: {len(recommendations)} recommendations")
                
            except Exception as e:
                print(f"❌ [DEBUG] Failed to explore node {node.label}: {e}")
                print(f"❌ [DEBUG] Exception type: {type(e).__name__}")
                import traceback
                print(f"❌ [DEBUG] Traceback: {traceback.format_exc()}")
                logger.error(f"❌ Failed to explore node {node.label}: {e}")
                # Create empty result dict for failed exploration
                empty_result = {
                    "error": str(e),
                    "exploration_summary": f"Failed to explore {node.label}",
                    "actionable_recommendations": []
                }
                exploration_results.append(empty_result)
        
        print(f"🧠 [DEBUG] Exploration stage completed: {len(exploration_results)} results")
        logger.info(f"✅ Exploration stage completed: {len(exploration_results)} results")
        return exploration_results
    
    def _run_reporting_stage(self, exploration_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compile exploration results into a final report.
        No need for a separate reporter - just aggregate the actionable_recommendations.
        """
        print(f"📊 [DEBUG] Compiling final report for {len(exploration_results)} results")
        logger.info(f"📊 Compiling final report for {len(exploration_results)} results")
        
        try:
            # Aggregate all actionable_recommendations from all explored nodes
            all_recommendations = []
            summaries = []
            
            for result in exploration_results:
                if isinstance(result, dict):
                    recommendations = result.get('actionable_recommendations', [])
                    all_recommendations.extend(recommendations)
                    
                    summary = result.get('exploration_summary', '')
                    if summary:
                        summaries.append(summary)
            
            print(f"📊 [DEBUG] Total recommendations: {len(all_recommendations)}")
            print(f"📊 [DEBUG] Total summaries: {len(summaries)}")
            
            # Create final report with all recommendations
            report = {
                "exploration_results": exploration_results,  # Original structured results
                "all_actionable_recommendations": all_recommendations,  # Flat list for easy consumption
                "summaries": summaries,
                "total_recommendations": len(all_recommendations),
                "total_nodes_explored": len(exploration_results)
            }
            
            logger.info(f"✅ Report compiled: {len(all_recommendations)} total actionable recommendations")
            return report
            
        except Exception as e:
            print(f"❌ [DEBUG] Reporting failed: {e}")
            print(f"❌ [DEBUG] Exception type: {type(e).__name__}")
            import traceback
            print(f"❌ [DEBUG] Traceback: {traceback.format_exc()}")
            logger.error(f"❌ Reporting failed: {e}")
            return {
                "error": str(e),
                "exploration_results": exploration_results,
                "all_actionable_recommendations": [],
                "summaries": [],
                "total_recommendations": 0,
                "total_nodes_explored": 0
            }
    
    def _get_candidate_nodes(self, limit: int, exploration_config: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Get candidate nodes from the knowledge graph for exploration.
        For entity relationship mode: prioritize entities (people, family members, organizations).
        """
        print(f"🔍 [DEBUG] Getting candidate nodes (limit={limit})")
        
        try:
            # Get database session (same as repair pipeline)
            print(f"🔍 [DEBUG] Getting database session...")
            from app.models.base import get_session
            from app.assistant.kg_core.knowledge_graph_db import Node
            from sqlalchemy import func
            session = get_session()
            print(f"🔍 [DEBUG] Database session obtained: {type(session)}")
            
            # For relationship discovery: prioritize Entity nodes (people, family, organizations)
            # with medium connectivity (not isolated, not over-connected)
            print(f"🔍 [DEBUG] Querying database for entity nodes...")
            query = session.query(Node).filter(
                Node.node_type == 'Entity',
                Node.category.in_(['person', 'family_member', 'organization', 'family_relationship'])
            ).order_by(func.random()).limit(limit)
            print(f"🔍 [DEBUG] Query created: {query}")
            
            nodes = query.all()
            print(f"🔍 [DEBUG] Query executed. Found {len(nodes) if nodes else 0} nodes")
            
            # Convert to candidate format
            print(f"🔍 [DEBUG] Converting nodes to candidate format...")
            candidates = []
            for i, node in enumerate(nodes):
                print(f"🔍 [DEBUG] Processing node {i+1}/{len(nodes)}: {node.label}")
                
                # Count actual edges for this node
                from app.assistant.kg_core.knowledge_graph_db import Edge
                edge_count = session.query(Edge).filter(
                    (Edge.source_id == node.id) | (Edge.target_id == node.id)
                ).count()
                
                candidates.append({
                    'id': str(node.id),
                    'label': node.label,
                    'semantic_label': node.semantic_label,
                    'type': node.node_type,
                    'category': node.category,
                    'description': node.description,
                    'start_date': node.start_date,
                    'end_date': node.end_date,
                    'connection_count': edge_count
                })
            
            print(f"🔍 [DEBUG] Converted {len(candidates)} nodes to candidates")
            logger.info(f"📝 Found {len(candidates)} candidate nodes for exploration")
            return candidates
            
        except Exception as e:
            print(f"❌ [DEBUG] Failed to get candidate nodes: {e}")
            print(f"❌ [DEBUG] Exception type: {type(e).__name__}")
            import traceback
            print(f"❌ [DEBUG] Traceback: {traceback.format_exc()}")
            logger.error(f"❌ Failed to get candidate nodes: {e}")
            return []
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """
        Get current status of the pipeline.
        """
        return {
            'pipeline_id': self.pipeline_id,
            'current_stage': self.state.current_stage.value if self.state.current_stage else None,
            'started_at': self.state.started_at.isoformat() if self.state.started_at else None,
            'completed_at': self.state.completed_at.isoformat() if self.state.completed_at else None,
            'error_message': self.state.error_message,
            'final_report': self.state.final_report
        }


if __name__ == '__main__':
    """
    Standalone execution of the KG Explorer Pipeline Orchestrator.
    This allows the pipeline to be run directly from the IDE or command line.
    """
    import sys
    import os
    
    # Add the project root to the path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    # Initialize the system (agents, managers, tools, services)
    import app.assistant.tests.test_setup  # This is just run for the import
    print("🔧 [DEBUG] System initialized successfully!")
    
    def main():
        manager_registry = DI.manager_registry
        manager_registry.preload_all()
        """Main function for standalone execution."""
        print("🚀 KG Explorer Pipeline Orchestrator - Standalone Mode")
        print("=" * 60)
        
        try:
            # Create orchestrator
            print("🔧 [DEBUG] Creating KGExplorerPipelineOrchestrator...")
            orchestrator = KGExplorerPipelineOrchestrator()
            print(f"🔧 [DEBUG] Orchestrator created with ID: {orchestrator.pipeline_id}")
            
            # Define exploration configuration
            exploration_config = {
                'max_depth': 3,
                'temporal_reasoning': True,
                'max_nodes': 5
            }
            
            print(f"📝 Pipeline ID: {orchestrator.pipeline_id}")
            print(f"📝 Configuration: {exploration_config}")
            print("\n⏳ Starting pipeline execution...")
            
            # Run the pipeline
            print("🔧 [DEBUG] Calling orchestrator.run_pipeline...")
            pipeline_state = orchestrator.run_pipeline(exploration_config, exploration_config['max_nodes'])
            print(f"🔧 [DEBUG] Pipeline execution completed. Final stage: {pipeline_state.current_stage}")
            
            # Display results
            print("\n" + "=" * 60)
            print("📊 Pipeline Results:")
            print("=" * 60)
            
            if pipeline_state.current_stage == "completed":
                print("✅ Pipeline completed successfully!")
                
                if pipeline_state.final_report:
                    report = pipeline_state.final_report
                    print(f"\n📊 Exploration Summary:")
                    print(f"   Nodes Explored: {report.get('total_nodes_explored', 0)}")
                    print(f"   Total Actionable Recommendations: {report.get('total_recommendations', 0)}")
                    
                    # Show all actionable recommendations
                    all_recommendations = report.get('all_actionable_recommendations', [])
                    if all_recommendations:
                        print(f"\n💡 Actionable Recommendations:")
                        for i, rec in enumerate(all_recommendations, 1):
                            print(f"\n   {i}. Node: {rec.get('node_label', 'N/A')} ({rec.get('node_id', 'N/A')})")
                            print(f"      Finding: {rec.get('finding', 'N/A')}")
                            print(f"      Recommendation: {rec.get('recommendation', 'N/A')}")
                            print(f"      Reasoning: {rec.get('reasoning', 'N/A')}")
                            print(f"      Confidence: {rec.get('confidence', 'N/A')}")
                    
                    # Show exploration summaries
                    summaries = report.get('summaries', [])
                    if summaries:
                        print(f"\n📝 Exploration Summaries:")
                        for i, summary in enumerate(summaries, 1):
                            print(f"   {i}. {summary}")
                else:
                    print("⚠️  No final report generated")
            else:
                print(f"❌ Pipeline failed with status: {pipeline_state.current_stage}")
                if pipeline_state.error_message:
                    print(f"❌ Error: {pipeline_state.error_message}")
            
            print(f"\n⏱️  Pipeline duration: {pipeline_state.completed_at - pipeline_state.started_at if pipeline_state.completed_at and pipeline_state.started_at else 'Unknown'}")
            
            return pipeline_state.current_stage == "completed"
            
        except Exception as e:
            print(f"❌ Pipeline execution failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Run the main function
    success = main()
    sys.exit(0 if success else 1)
