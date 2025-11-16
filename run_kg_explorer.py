#!/usr/bin/env python3
"""
KG Explorer Pipeline Runner

This script runs the KG Explorer pipeline to discover relationships
and perform temporal reasoning on the knowledge graph.
"""

import sys
import os
from datetime import datetime, timezone

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_kg_explorer_pipeline():
    """Run the KG Explorer pipeline using the orchestrator."""
    print("🚀 Starting KG Explorer Pipeline")
    print("=" * 50)
    
    try:
        # Import the orchestrator
        from app.assistant.kg_explorer_pipeline.pipeline_orchestrator import KGExplorerPipelineOrchestrator
        
        # Create orchestrator instance
        orchestrator = KGExplorerPipelineOrchestrator()
        
        # Define exploration configurations
        exploration_configs = [
            {
                'max_depth': 3,
                'temporal_reasoning': True,
                'max_nodes': 3
            },
            {
                'max_depth': 2,
                'temporal_reasoning': True,
                'max_nodes': 2
            },
            {
                'max_depth': 2,
                'temporal_reasoning': False,
                'max_nodes': 2
            }
        ]
        
        print(f"📝 Found {len(exploration_configs)} exploration configurations")
        
        # Process each exploration configuration
        for i, config in enumerate(exploration_configs, 1):
            print(f"\n🔍 Running Exploration Configuration {i}/{len(exploration_configs)}")
            print(f"📝 Max depth: {config['max_depth']}")
            print(f"📝 Max nodes: {config['max_nodes']}")
            print(f"📝 Temporal reasoning: {config['temporal_reasoning']}")
            
            try:
                # Run the pipeline with this configuration
                print("⏳ Executing pipeline...")
                pipeline_state = orchestrator.run_pipeline(config, config['max_nodes'])
                
                if pipeline_state.current_stage == "completed":
                    print("✅ Pipeline completed successfully")
                    if pipeline_state.final_report:
                        print(f"📊 Discoveries: {len(pipeline_state.final_report.get('discoveries', []))}")
                        print(f"📊 Temporal inferences: {len(pipeline_state.final_report.get('temporal_inferences', []))}")
                        print(f"📊 Missing connections: {len(pipeline_state.final_report.get('missing_connections', []))}")
                else:
                    print(f"⚠️  Pipeline completed with status: {pipeline_state.current_stage}")
                    if pipeline_state.error_message:
                        print(f"❌ Error: {pipeline_state.error_message}")
                    
            except Exception as e:
                print(f"❌ Pipeline failed: {e}")
                continue
        
        print("\n🎉 KG Explorer Pipeline completed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure all dependencies are installed and paths are correct")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Main function."""
    print("🧠 KG Explorer Pipeline Runner")
    print("=" * 50)
    print("This script will run the KG Explorer pipeline to discover")
    print("relationships and perform temporal reasoning on the knowledge graph.")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists("app/assistant"):
        print("❌ Error: app/assistant directory not found")
        print("💡 Make sure you're running this from the project root")
        return False
    
    # Run the pipeline
    success = run_kg_explorer_pipeline()
    
    if success:
        print("\n🎉 KG Explorer Pipeline completed successfully!")
    else:
        print("\n❌ KG Explorer Pipeline failed. Check the output above for details.")
    
    return success

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
