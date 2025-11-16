"""
KG Reporter Stage

This stage generates comprehensive reports from exploration results.
"""

from typing import List, Dict, Any
from app.assistant.utils.logging_config import get_logger
from app.assistant.kg_explorer_pipeline.data_models.exploration_result import ExplorationResult

logger = get_logger(__name__)


class KGReporter:
    """
    Generates comprehensive reports from exploration results.
    """
    
    def __init__(self):
        self.report_templates = {
            'summary': "Exploration Summary",
            'discoveries': "Relationship Discoveries",
            'temporal': "Temporal Inferences",
            'missing': "Missing Connections",
            'recommendations': "Next Steps"
        }
    
    def generate_report(self, exploration_results: List[ExplorationResult]) -> Dict[str, Any]:
        """
        Generate a comprehensive report from exploration results.
        
        Args:
            exploration_results: List of exploration results
            
        Returns:
            Comprehensive report dictionary
        """
        logger.info(f"📊 Generating report for {len(exploration_results)} exploration results")
        
        try:
            # Aggregate all discoveries
            all_discoveries = []
            all_temporal_inferences = []
            all_missing_connections = []
            
            for result in exploration_results:
                all_discoveries.extend(result.discoveries)
                all_temporal_inferences.extend(result.temporal_inferences)
                all_missing_connections.extend(result.missing_connections)
            
            # Generate report sections
            report = {
                'summary': self._generate_summary(exploration_results),
                'discoveries': self._format_discoveries(all_discoveries),
                'temporal_inferences': self._format_temporal_inferences(all_temporal_inferences),
                'missing_connections': self._format_missing_connections(all_missing_connections),
                'recommendations': self._generate_recommendations(exploration_results),
                'statistics': self._generate_statistics(exploration_results),
                'next_steps': self._generate_next_steps(exploration_results)
            }
            
            logger.info(f"✅ Generated comprehensive report: {len(all_discoveries)} discoveries, {len(all_temporal_inferences)} temporal inferences, {len(all_missing_connections)} missing connections")
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Failed to generate report: {e}")
            return {
                'error': str(e),
                'summary': 'Report generation failed',
                'discoveries': [],
                'temporal_inferences': [],
                'missing_connections': [],
                'recommendations': []
            }
    
    def _generate_summary(self, exploration_results: List[ExplorationResult]) -> str:
        """Generate summary of exploration results."""
        total_nodes = len(exploration_results)
        successful_explorations = len([r for r in exploration_results if not r.error_message])
        total_discoveries = sum(len(r.discoveries) for r in exploration_results)
        total_temporal = sum(len(r.temporal_inferences) for r in exploration_results)
        total_missing = sum(len(r.missing_connections) for r in exploration_results)
        
        return f"""
KG Explorer Pipeline Summary:
- Explored {total_nodes} nodes ({successful_explorations} successful)
- Discovered {total_discoveries} relationships
- Made {total_temporal} temporal inferences
- Found {total_missing} missing connections
- Average confidence: {sum(r.confidence_score for r in exploration_results) / total_nodes:.2f}
        """.strip()
    
    def _format_discoveries(self, discoveries: List) -> List[Dict[str, Any]]:
        """Format discoveries for the report."""
        formatted = []
        for discovery in discoveries:
            formatted.append({
                'type': discovery.type,
                'description': discovery.description,
                'confidence': discovery.confidence,
                'evidence': discovery.evidence,
                'suggested_action': discovery.suggested_action
            })
        return formatted
    
    def _format_temporal_inferences(self, inferences: List) -> List[Dict[str, Any]]:
        """Format temporal inferences for the report."""
        formatted = []
        for inference in inferences:
            formatted.append({
                'description': inference.description,
                'confidence': inference.confidence,
                'evidence': inference.evidence,
                'suggested_dates': inference.suggested_dates
            })
        return formatted
    
    def _format_missing_connections(self, connections: List) -> List[Dict[str, Any]]:
        """Format missing connections for the report."""
        formatted = []
        for connection in connections:
            formatted.append({
                'description': connection.description,
                'confidence': connection.confidence,
                'evidence': connection.evidence,
                'suggested_connection': connection.suggested_connection
            })
        return formatted
    
    def _generate_recommendations(self, exploration_results: List[ExplorationResult]) -> List[str]:
        """Generate recommendations based on exploration results."""
        recommendations = []
        
        # High confidence discoveries
        high_confidence_discoveries = [
            r for r in exploration_results 
            if r.confidence_score > 0.7 and len(r.discoveries) > 0
        ]
        
        if high_confidence_discoveries:
            recommendations.append("Review high-confidence discoveries for potential KG updates")
        
        # Temporal inferences
        temporal_results = [r for r in exploration_results if len(r.temporal_inferences) > 0]
        if temporal_results:
            recommendations.append("Investigate temporal inferences for date refinement")
        
        # Missing connections
        missing_results = [r for r in exploration_results if len(r.missing_connections) > 0]
        if missing_results:
            recommendations.append("Consider creating missing connections identified")
        
        # Low confidence results
        low_confidence_results = [r for r in exploration_results if r.confidence_score < 0.3]
        if low_confidence_results:
            recommendations.append("Review low-confidence results for potential data quality issues")
        
        return recommendations
    
    def _generate_statistics(self, exploration_results: List[ExplorationResult]) -> Dict[str, Any]:
        """Generate statistics for the report."""
        total_nodes = len(exploration_results)
        successful_nodes = len([r for r in exploration_results if not r.error_message])
        
        return {
            'total_nodes_explored': total_nodes,
            'successful_explorations': successful_nodes,
            'success_rate': successful_nodes / total_nodes if total_nodes > 0 else 0,
            'total_discoveries': sum(len(r.discoveries) for r in exploration_results),
            'total_temporal_inferences': sum(len(r.temporal_inferences) for r in exploration_results),
            'total_missing_connections': sum(len(r.missing_connections) for r in exploration_results),
            'average_confidence': sum(r.confidence_score for r in exploration_results) / total_nodes if total_nodes > 0 else 0,
            'total_exploration_time': sum(r.exploration_time for r in exploration_results)
        }
    
    def _generate_next_steps(self, exploration_results: List[ExplorationResult]) -> List[str]:
        """Generate next steps based on exploration results."""
        next_steps = []
        
        # If we found many discoveries, suggest deeper exploration
        total_discoveries = sum(len(r.discoveries) for r in exploration_results)
        if total_discoveries > 5:
            next_steps.append("Consider deeper exploration of high-discovery nodes")
        
        # If we found temporal inferences, suggest date refinement
        temporal_count = sum(len(r.temporal_inferences) for r in exploration_results)
        if temporal_count > 0:
            next_steps.append("Review and implement temporal inferences")
        
        # If we found missing connections, suggest connection creation
        missing_count = sum(len(r.missing_connections) for r in exploration_results)
        if missing_count > 0:
            next_steps.append("Create missing connections identified")
        
        # If we have low confidence results, suggest data quality review
        low_confidence_count = len([r for r in exploration_results if r.confidence_score < 0.3])
        if low_confidence_count > 0:
            next_steps.append("Review data quality for low-confidence results")
        
        return next_steps
