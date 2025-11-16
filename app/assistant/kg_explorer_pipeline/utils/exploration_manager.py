"""
Exploration Manager for KG Explorer Pipeline

This utility manages exploration tracking and provides helper functions.
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
from app.assistant.utils.logging_config import get_logger
from app.assistant.kg_explorer_pipeline.data_models.exploration_result import ExplorationResult

logger = get_logger(__name__)


class ExplorationManager:
    """
    Manages exploration tracking and provides helper functions.
    """
    
    def __init__(self):
        self.exploration_log = []
        self.exploration_counter = 0
    
    def track_exploration(self, node_id: str, result: ExplorationResult):
        """
        Track an exploration result.
        
        Args:
            node_id: ID of the explored node
            result: Exploration result
        """
        try:
            self.exploration_counter += 1
            
            log_entry = {
                'exploration_id': f"exploration_{self.exploration_counter}",
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'node_id': node_id,
                'node_label': result.node_label,
                'discoveries_count': len(result.discoveries),
                'temporal_inferences_count': len(result.temporal_inferences),
                'missing_connections_count': len(result.missing_connections),
                'confidence_score': result.confidence_score,
                'exploration_time': result.exploration_time,
                'error_message': result.error_message
            }
            
            self.exploration_log.append(log_entry)
            
            logger.info(f"📝 Tracked exploration {self.exploration_counter}: {result.node_label}")
            
        except Exception as e:
            logger.error(f"❌ Failed to track exploration: {e}")
    
    def get_exploration_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about explorations.
        
        Returns:
            Dictionary with exploration statistics
        """
        try:
            if not self.exploration_log:
                return {
                    'total_explorations': 0,
                    'successful_explorations': 0,
                    'failed_explorations': 0,
                    'success_rate': 0.0,
                    'total_discoveries': 0,
                    'total_temporal_inferences': 0,
                    'total_missing_connections': 0,
                    'average_confidence': 0.0,
                    'total_exploration_time': 0.0
                }
            
            total_explorations = len(self.exploration_log)
            successful_explorations = len([e for e in self.exploration_log if not e.get('error_message')])
            failed_explorations = total_explorations - successful_explorations
            
            success_rate = (successful_explorations / total_explorations) if total_explorations > 0 else 0
            
            total_discoveries = sum(e.get('discoveries_count', 0) for e in self.exploration_log)
            total_temporal = sum(e.get('temporal_inferences_count', 0) for e in self.exploration_log)
            total_missing = sum(e.get('missing_connections_count', 0) for e in self.exploration_log)
            
            confidence_scores = [e.get('confidence_score', 0) for e in self.exploration_log if e.get('confidence_score') is not None]
            average_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
            
            total_time = sum(e.get('exploration_time', 0) for e in self.exploration_log)
            
            return {
                'total_explorations': total_explorations,
                'successful_explorations': successful_explorations,
                'failed_explorations': failed_explorations,
                'success_rate': round(success_rate, 3),
                'total_discoveries': total_discoveries,
                'total_temporal_inferences': total_temporal,
                'total_missing_connections': total_missing,
                'average_confidence': round(average_confidence, 3),
                'total_exploration_time': round(total_time, 3)
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get exploration statistics: {e}")
            return {}
    
    def get_exploration_log(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        Get exploration log entries.
        
        Args:
            limit: Maximum number of entries to return (None for all)
            
        Returns:
            List of exploration log entries
        """
        try:
            if limit is None:
                return self.exploration_log.copy()
            else:
                return self.exploration_log[-limit:]
                
        except Exception as e:
            logger.error(f"❌ Failed to get exploration log: {e}")
            return []
    
    def clear_exploration_log(self):
        """Clear the exploration log."""
        try:
            self.exploration_log.clear()
            self.exploration_counter = 0
            logger.info("🧹 Cleared exploration log")
        except Exception as e:
            logger.error(f"❌ Failed to clear exploration log: {e}")
    
    def export_exploration_log(self, filepath: str) -> bool:
        """
        Export exploration log to a file.
        
        Args:
            filepath: Path to export the log
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import json
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.exploration_log, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📁 Exported exploration log to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to export exploration log: {e}")
            return False
