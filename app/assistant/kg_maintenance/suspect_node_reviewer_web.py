#!/usr/bin/env python3
"""
Suspect Node Reviewer Web Interface
Flask web application for reviewing, filtering, and deleting suspicious nodes.
"""
import app.assistant.tests.test_setup # This is just run for the import
import json
import os
import sys
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.kg_maintenance.node_cleanup_pipeline import run_node_cleanup_pipeline

app = Flask(__name__)
app.secret_key = 'suspect_node_reviewer_secret_key_2024'


@dataclass
class SuspectNode:
    """Data class for suspect node information"""
    node_id: str
    label: str
    type: str
    category: str
    edge_count: int
    jukka_distance: int
    suspect_reason: str
    confidence: float
    cleanup_priority: str
    suggested_action: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SuspectNodeManager:
    def __init__(self):
        self.session = get_session()
        
    def load_suspect_nodes(self, from_pipeline: bool = True) -> Dict[str, Any]:
        """Load suspect nodes by running the pipeline or from JSON file"""
        try:
            if from_pipeline:
                print("🔍 Running node cleanup pipeline to generate suspect nodes...")
                result = run_node_cleanup_pipeline()
                suspect_nodes = [SuspectNode(**node) for node in result.get('suspect_nodes', [])]
                print(f"✅ Generated {len(suspect_nodes)} suspect nodes")
                return {
                    "success": True,
                    "nodes": [node.to_dict() for node in suspect_nodes],
                    "message": f"Generated {len(suspect_nodes)} suspect nodes from pipeline"
                }
            else:
                # Load from most recent JSON file - search in multiple locations
                search_paths = [
                    Path('.'),  # Current directory
                    Path('app/assistant/kg_maintenance'),  # KG maintenance directory
                    Path('app/assistant/kg_core'),  # KG core directory
                ]
                
                json_files = []
                for search_path in search_paths:
                    if search_path.exists():
                        json_files.extend(list(search_path.glob('suspect_nodes_report_*.json')))
                
                if not json_files:
                    print("❌ No JSON report files found in any of the search paths")
                    print(f"   Searched in: {[str(p) for p in search_paths]}")
                    return {
                        "success": False,
                        "message": "No JSON report files found"
                    }
                
                # Get the most recent file
                latest_file = max(json_files, key=lambda x: x.stat().st_mtime)
                print(f"📂 Loading from {latest_file}")
                
                with open(latest_file, 'r') as f:
                    data = json.load(f)
                
                # Validate that nodes still exist in the database and haven't been excluded
                json_nodes = data.get('suspect_nodes', [])
                valid_nodes = []
                deleted_count = 0
                excluded_count = 0
                
                # Get the report timestamp to check for exclusions
                report_timestamp = data.get('timestamp')
                if report_timestamp:
                    try:
                        from datetime import datetime
                        report_time = datetime.fromisoformat(report_timestamp.replace('Z', '+00:00'))
                    except:
                        report_time = None
                else:
                    report_time = None
                
                for node_data in json_nodes:
                    try:
                        # Check if node still exists in database
                        node_uuid = uuid.UUID(node_data['node_id'])
                        current_node = self.session.query(Node).filter(Node.id == node_uuid).first()
                        
                        if current_node:
                            # Check if node was updated after the report (indicating it was excluded)
                            if report_time and current_node.updated_at and current_node.updated_at > report_time:
                                excluded_count += 1
                                print(f"⏭️ Skipping node '{current_node.label}' - was updated after report (excluded)")
                                continue
                            
                            # Node exists and hasn't been excluded - use current data but keep analysis results
                            suspect_info = {
                                'node_id': node_data['node_id'],
                                'label': current_node.label,
                                'type': current_node.node_type,
                                'category': getattr(current_node, 'category', ''),
                                'edge_count': node_data.get('edge_count', 0),
                                'jukka_distance': node_data.get('jukka_distance', -1),
                                'suspect_reason': node_data.get('suspect_reason', ''),
                                'confidence': node_data.get('confidence', 0.0),
                                'cleanup_priority': node_data.get('cleanup_priority', 'none'),
                                'suggested_action': node_data.get('suggested_action', '')
                            }
                            valid_nodes.append(suspect_info)
                        else:
                            # Node was deleted - skip it
                            deleted_count += 1
                            
                    except (ValueError, KeyError) as e:
                        # Invalid node ID or missing required fields - skip it
                        deleted_count += 1
                        continue
                
                suspect_nodes = [SuspectNode(**node) for node in valid_nodes]
                
                message = f"Loaded {len(suspect_nodes)} suspect nodes from {latest_file.name}"
                if deleted_count > 0:
                    message += f" ({deleted_count} nodes were skipped because they no longer exist)"
                if excluded_count > 0:
                    message += f" ({excluded_count} nodes were skipped because they were excluded after the report)"
                
                print(f"✅ {message}")
                return {
                    "success": True,
                    "nodes": [node.to_dict() for node in suspect_nodes],
                    "message": message
                }
            
        except Exception as e:
            print(f"❌ Error loading suspect nodes: {e}")
            return {
                "success": False,
                "message": f"Error loading suspect nodes: {str(e)}"
            }
    
    def delete_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple nodes from the database one at a time"""
        try:
            deleted_count = 0
            failed_count = 0
            total_edges_deleted = 0
            failed_nodes = []
            
            # First, clean up any corrupted edges (NULL target_id or source_id)
            self._cleanup_corrupted_edges()
            
            for node_id in node_ids:
                try:
                    # Convert string node_id to UUID
                    try:
                        node_uuid = uuid.UUID(node_id)
                    except ValueError:
                        failed_count += 1
                        failed_nodes.append(f"{node_id} (invalid format)")
                        continue
                    
                    # Get node info before deletion for reporting
                    node = self.session.query(Node).filter(Node.id == node_uuid).first()
                    if not node:
                        failed_count += 1
                        failed_nodes.append(f"{node_id} (not found)")
                        continue
                    
                    # Get edge count before deletion
                    edge_count = self.session.query(Edge).filter(
                        (Edge.source_id == node_uuid) | (Edge.target_id == node_uuid)
                    ).count()
                    
                    # Delete edges first, then the node
                    self._delete_node_safely(node_uuid, node.label)
                    
                    total_edges_deleted += edge_count
                    deleted_count += 1
                    
                    print(f"✅ Deleted node '{node.label}' ({node_id}) and {edge_count} edges")
                    
                except Exception as e:
                    failed_count += 1
                    failed_nodes.append(f"{node_id} ({str(e)})")
                    print(f"❌ Failed to delete node {node_id}: {e}")
                    # Rollback and continue with next node
                    self.session.rollback()
                    continue
            
            message = f"Successfully deleted {deleted_count} nodes and {total_edges_deleted} connected edges"
            if failed_count > 0:
                message += f". Failed to delete {failed_count} nodes: {', '.join(failed_nodes[:5])}"
                if len(failed_nodes) > 5:
                    message += f" and {len(failed_nodes) - 5} more"
            
            return {
                "success": True,
                "message": message,
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "total_edges_deleted": total_edges_deleted
            }
            
        except Exception as e:
            return {"success": False, "message": f"Error in bulk delete operation: {str(e)}"}
    
    def _cleanup_corrupted_edges(self):
        """Clean up edges with NULL source_id or target_id"""
        try:
            # Find corrupted edges
            corrupted_edges = self.session.query(Edge).filter(
                (Edge.source_id.is_(None)) | (Edge.target_id.is_(None))
            ).all()
            
            if corrupted_edges:
                print(f"🧹 Found {len(corrupted_edges)} corrupted edges with NULL source_id or target_id")
                for edge in corrupted_edges:
                    print(f"   Deleting corrupted edge {edge.id}: source_id={edge.source_id}, target_id={edge.target_id}")
                    self.session.delete(edge)
                
                self.session.commit()
                print(f"✅ Cleaned up {len(corrupted_edges)} corrupted edges")
            else:
                print("✅ No corrupted edges found")
                
        except Exception as e:
            print(f"❌ Error cleaning up corrupted edges: {e}")
            self.session.rollback()
    
    def _delete_node_safely(self, node_uuid: uuid.UUID, node_label: str):
        """Safely delete a node by first deleting its edges, then the node"""
        try:
            # Delete all edges connected to this node first
            edges_to_delete = self.session.query(Edge).filter(
                (Edge.source_id == node_uuid) | (Edge.target_id == node_uuid)
            ).all()
            
            for edge in edges_to_delete:
                self.session.delete(edge)
            
            # Delete the node
            node = self.session.query(Node).filter(Node.id == node_uuid).first()
            if node:
                self.session.delete(node)
            
            # Commit this node's deletion
            self.session.commit()
            
        except Exception as e:
            print(f"❌ Error deleting node {node_label} ({node_uuid}): {e}")
            self.session.rollback()
            raise
    
    def save_suspect_nodes(self, suspect_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save suspect nodes to a JSON file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"suspect_nodes_report_{timestamp}.json"
            
            report = {
                "timestamp": str(datetime.now()),
                "total_suspect_nodes": len(suspect_nodes),
                "suspect_nodes": suspect_nodes
            }
            
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2)
            
            return {
                "success": True,
                "message": f"Report saved to {filename}",
                "filename": filename
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error saving report: {str(e)}"
            }

    def update_node_type(self, node_id: str, new_type: str) -> Dict[str, Any]:
        """Update the type of a specific node"""
        try:
            # Convert string node_id to UUID
            try:
                node_uuid = uuid.UUID(node_id)
            except ValueError:
                return {
                    "success": False,
                    "message": f"Invalid node ID format: {node_id}"
                }
            
            # Get the node
            node = self.session.query(Node).filter(Node.id == node_uuid).first()
            if not node:
                return {
                    "success": False,
                    "message": f"Node not found: {node_id}"
                }
            
            # Store old type for reporting
            old_type = node.node_type
            
            # Update the node type
            node.node_type = new_type
            node.updated_at = datetime.now()
            
            # Commit the change
            self.session.commit()
            
            return {
                "success": True,
                "message": f"Updated node '{node.label}' type from '{old_type}' to '{new_type}'",
                "old_type": old_type,
                "new_type": new_type,
                "node_label": node.label
            }
            
        except Exception as e:
            self.session.rollback()
            return {
                "success": False,
                "message": f"Error updating node type: {str(e)}"
            }

    def mark_nodes_as_excluded(self, node_ids: List[str]) -> Dict[str, Any]:
        """Mark nodes as excluded by updating their updated_at timestamp"""
        try:
            updated_count = 0
            failed_count = 0
            failed_nodes = []
            
            for node_id in node_ids:
                try:
                    # Convert string node_id to UUID
                    try:
                        node_uuid = uuid.UUID(node_id)
                    except ValueError:
                        failed_count += 1
                        failed_nodes.append(f"{node_id} (invalid format)")
                        continue
                    
                    # Get the node
                    node = self.session.query(Node).filter(Node.id == node_uuid).first()
                    if not node:
                        failed_count += 1
                        failed_nodes.append(f"{node_id} (not found)")
                        continue
                    
                    # Update the timestamp to mark as excluded
                    node.updated_at = datetime.now()
                    updated_count += 1
                    
                    print(f"✅ Marked node '{node.label}' as excluded (updated timestamp)")
                    
                except Exception as e:
                    failed_count += 1
                    failed_nodes.append(f"{node_id} ({str(e)})")
                    print(f"❌ Failed to mark node {node_id} as excluded: {e}")
                    continue
            
            # Commit all changes
            self.session.commit()
            
            message = f"Successfully marked {updated_count} nodes as excluded"
            if failed_count > 0:
                message += f". Failed to mark {failed_count} nodes: {', '.join(failed_nodes[:5])}"
                if len(failed_nodes) > 5:
                    message += f" and {len(failed_nodes) - 5} more"
            
            return {
                "success": True,
                "message": message,
                "updated_count": updated_count,
                "failed_count": failed_count
            }
            
        except Exception as e:
            self.session.rollback()
            return {
                "success": False,
                "message": f"Error marking nodes as excluded: {str(e)}"
            }

    def export_database_to_json(self) -> Dict[str, Any]:
        """Export suspect nodes from database analysis tracking to JSON format"""
        try:
            from app.models.node_analysis_tracking import NodeAnalysisTracking
            
            # Query all suspect nodes from the tracking database
            suspect_analyses = self.session.query(NodeAnalysisTracking).filter(
                NodeAnalysisTracking.is_suspect == True
            ).all()
            
            if not suspect_analyses:
                return {
                    "success": True,
                    "nodes": [],
                    "message": "No suspect nodes found in database"
                }
            
            # Convert to SuspectNode format - only include nodes that still exist
            suspect_nodes = []
            deleted_count = 0
            
            for analysis in suspect_analyses:
                # Get current node data to ensure we have latest info
                try:
                    # analysis.node_id is already a UUID object, convert to string for query
                    node_id_str = str(analysis.node_id)
                    current_node = self.session.query(Node).filter(Node.id == analysis.node_id).first()
                    
                    if current_node:
                        # Node exists - use current data but analysis results from tracking
                        # Handle non-ASCII characters by encoding/decoding safely
                        def safe_str(value):
                            if value is None:
                                return ''
                            try:
                                return str(value)
                            except UnicodeError:
                                return str(value).encode('utf-8', errors='replace').decode('utf-8')
                        
                        suspect_info = {
                            'node_id': node_id_str,
                            'label': safe_str(current_node.label),
                            'type': safe_str(current_node.node_type),
                            'category': safe_str(getattr(current_node, 'category', '')),
                            'edge_count': analysis.edge_count_at_analysis or 0,
                            'jukka_distance': analysis.jukka_distance_at_analysis or -1,
                            'suspect_reason': safe_str(analysis.suspect_reason),
                            'confidence': analysis.confidence or 0.0,
                            'cleanup_priority': safe_str(analysis.cleanup_priority) or 'none',
                            'suggested_action': safe_str(analysis.suggested_action)
                        }
                        suspect_nodes.append(suspect_info)
                    else:
                        # Node was deleted - skip it
                        deleted_count += 1
                        
                except Exception as e:
                    # Skip this record if there's any error
                    print(f"Warning: Skipping analysis record for node {analysis.node_id} due to error: {e}")
                    continue
            
            # Sort by priority and confidence
            def get_priority_score(priority):
                """Convert priority to numeric score, handling non-English values"""
                if not priority:
                    return 0
                
                priority_lower = str(priority).lower()
                
                # English priorities
                if priority_lower in ['high', 'h']:
                    return 3
                elif priority_lower in ['medium', 'med', 'm']:
                    return 2
                elif priority_lower in ['low', 'l']:
                    return 1
                elif priority_lower in ['none', 'n']:
                    return 0
                
                # Chinese priorities (common characters)
                elif priority in ['高', '高优先级']:  # high
                    return 3
                elif priority in ['中', '中优先级', '中等']:  # medium
                    return 2
                elif priority in ['低', '低优先级']:  # low
                    return 1
                elif priority in ['无', '无优先级']:  # none
                    return 0
                
                # Default fallback - treat unknown priorities as medium
                return 2
            
            suspect_nodes.sort(key=lambda x: (
                get_priority_score(x['cleanup_priority']), 
                x['confidence']
            ), reverse=True)
            
            message = f"Exported {len(suspect_nodes)} suspect nodes from database"
            if deleted_count > 0:
                message += f" ({deleted_count} nodes were skipped because they no longer exist)"
            
            return {
                "success": True,
                "nodes": suspect_nodes,
                "message": message
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Error exporting from database: {str(e)}"
            }


# Global manager instance
node_manager = SuspectNodeManager()


@app.route('/')
def index():
    """Main page"""
    return render_template('suspect_reviewer.html')


@app.route('/api/load-nodes')
def api_load_nodes():
    """API endpoint to load suspect nodes"""
    # Check if user wants to run pipeline, load from JSON, or export from database
    from_pipeline = request.args.get('from_pipeline', 'false').lower() == 'true'
    from_database = request.args.get('from_database', 'false').lower() == 'true'
    
    if from_database:
        result = node_manager.export_database_to_json()
    else:
        result = node_manager.load_suspect_nodes(from_pipeline=from_pipeline)
    
    return jsonify(result)





@app.route('/api/delete-nodes', methods=['POST'])
def api_delete_nodes():
    """API endpoint to delete nodes from database"""
    data = request.get_json()
    node_ids = data.get('node_ids', [])
    
    if not node_ids:
        return jsonify({"success": False, "message": "No node IDs provided"})
    
    result = node_manager.delete_nodes(node_ids)
    return jsonify(result)


@app.route('/api/save-report', methods=['POST'])
def api_save_report():
    """API endpoint to save current suspect nodes to a report"""
    data = request.get_json()
    suspect_nodes = data.get('suspect_nodes', [])
    
    if not suspect_nodes:
        return jsonify({"success": False, "message": "No suspect nodes provided"})
    
    result = node_manager.save_suspect_nodes(suspect_nodes)
    return jsonify(result)


@app.route('/api/update-node-type', methods=['POST'])
def api_update_node_type():
    """API endpoint to update a node's type"""
    data = request.get_json()
    node_id = data.get('node_id')
    new_type = data.get('new_type')
    
    if not node_id or not new_type:
        return jsonify({"success": False, "message": "Both node_id and new_type are required"})
    
    result = node_manager.update_node_type(node_id, new_type)
    return jsonify(result)


@app.route('/api/mark-excluded', methods=['POST'])
def api_mark_excluded():
    """API endpoint to mark nodes as excluded by updating their timestamp"""
    data = request.get_json()
    node_ids = data.get('node_ids', [])
    
    if not node_ids:
        return jsonify({"success": False, "message": "No node IDs provided"})
    
    result = node_manager.mark_nodes_as_excluded(node_ids)
    return jsonify(result)


if __name__ == '__main__':
    print("🌐 Starting Suspect Node Reviewer Web Interface...")
    print("📱 Open your browser and go to: http://localhost:5001")
    app.run(debug=True, port=5001, host='0.0.0.0')
