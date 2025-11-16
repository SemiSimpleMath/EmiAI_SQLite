#!/usr/bin/env python3
"""
Export Database Analysis Results to JSON
Standalone script to export suspect nodes from database analysis tracking to JSON format
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node
from app.models.node_analysis_tracking import NodeAnalysisTracking
import uuid


def export_database_to_json(output_file: str = None) -> str:
    """
    Export suspect nodes from database analysis tracking to JSON format
    
    Args:
        output_file: Optional output filename. If None, generates timestamped filename
        
    Returns:
        Path to the created JSON file
    """
    session = get_session()
    
    try:
        # Query all suspect nodes from the tracking database
        suspect_analyses = session.query(NodeAnalysisTracking).filter(
            NodeAnalysisTracking.is_suspect == True
        ).all()
        
        if not suspect_analyses:
            print("❌ No suspect nodes found in database")
            return None
        
        print(f"📊 Found {len(suspect_analyses)} suspect nodes in database")
        
        # Convert to suspect node format
        suspect_nodes = []
        for analysis in suspect_analyses:
            # Get current node data to ensure we have latest info
            try:
                # analysis.node_id is already a UUID object, convert to string for output
                node_id_str = str(analysis.node_id)
                current_node = session.query(Node).filter(Node.id == analysis.node_id).first()
                
                if current_node:
                    # Use current node data, but analysis results from tracking
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
                        'node_classification': safe_str(getattr(current_node, 'node_classification', 'entity_node')),
                        'category': safe_str(getattr(current_node, 'category', '')),
                        'sentence': safe_str(current_node.sentence),
                        'edge_count': analysis.edge_count_at_analysis or 0,
                        'jukka_distance': analysis.jukka_distance_at_analysis or -1,
                        'suspect_reason': safe_str(analysis.suspect_reason),
                        'confidence': analysis.confidence or 0.0,
                        'cleanup_priority': safe_str(analysis.cleanup_priority) or 'none',
                        'suggested_action': safe_str(analysis.suggested_action)
                    }
                    suspect_nodes.append(suspect_info)
                else:
                    # Node was deleted, but we still have the analysis record
                    def safe_str(value):
                        if value is None:
                            return ''
                        try:
                            return str(value)
                        except UnicodeError:
                            return str(value).encode('utf-8', errors='replace').decode('utf-8')
                    
                    suspect_info = {
                        'node_id': node_id_str,
                        'label': safe_str(analysis.node_label),
                        'type': safe_str(analysis.node_type_at_analysis) or 'Unknown',
                        'node_classification': safe_str(analysis.node_classification_at_analysis) or 'entity_node',
                        'category': '',
                        'sentence': '',
                        'edge_count': analysis.edge_count_at_analysis or 0,
                        'jukka_distance': analysis.jukka_distance_at_analysis or -1,
                        'suspect_reason': safe_str(analysis.suspect_reason),
                        'confidence': analysis.confidence or 0.0,
                        'cleanup_priority': safe_str(analysis.cleanup_priority) or 'none',
                        'suggested_action': safe_str(analysis.suggested_action)
                    }
                    suspect_nodes.append(suspect_info)
                    
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
            print(f"Warning: Unknown priority '{priority}', treating as medium")
            return 2
        
        suspect_nodes.sort(key=lambda x: (
            get_priority_score(x['cleanup_priority']), 
            x['confidence']
        ), reverse=True)
        
        # Generate output filename if not provided
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"suspect_nodes_from_database_{timestamp}.json"
        
        # Create report structure
        report = {
            "timestamp": str(datetime.now()),
            "source": "database_analysis_tracking",
            "total_suspect_nodes": len(suspect_nodes),
            "suspect_nodes": suspect_nodes
        }
        
        # Write to file
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✅ Exported {len(suspect_nodes)} suspect nodes to {output_file}")
        
        # Print summary
        print(f"\n📊 EXPORT SUMMARY:")
        print(f"  Total suspect nodes: {len(suspect_nodes)}")
        
        # Group by priority
        by_priority = {}
        for node in suspect_nodes:
            priority = node['cleanup_priority']
            if priority not in by_priority:
                by_priority[priority] = 0
            by_priority[priority] += 1
        
        for priority in ['high', 'medium', 'low', 'none']:
            if priority in by_priority:
                print(f"  {priority.upper()} priority: {by_priority[priority]} nodes")
        
        return output_file
        
    except Exception as e:
        print(f"❌ Error exporting from database: {e}")
        return None
        
    finally:
        session.close()


if __name__ == "__main__":
    import app.assistant.tests.test_setup  # This is just run for the import
    
    print("🗄️ Exporting Database Analysis Results to JSON...")
    print("=" * 60)
    
    # Check if output file was specified as command line argument
    output_file = None
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
        print(f"📁 Output file specified: {output_file}")
    
    # Export the data
    result_file = export_database_to_json(output_file)
    
    if result_file:
        print(f"\n✅ Export completed successfully!")
        print(f"📄 JSON file created: {result_file}")
        print(f"🌐 You can now use this file with the web interface or load it directly")
    else:
        print(f"\n❌ Export failed!")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("🏁 Database export finished")
