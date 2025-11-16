#!/usr/bin/env python3
"""
Run the KG Repair Pipeline to generate reviews

This will analyze nodes and save findings to kg_reviews table (non-interactive mode).
"""

import app.assistant.tests.test_setup  # Initialize everything

from app.assistant.kg_repair_pipeline.pipeline_orchestrator import KGPipelineOrchestrator

print("🚀 Starting KG Repair Pipeline in review mode...")
print("   (Findings will be saved to kg_reviews table)\n")

# Create orchestrator in non-interactive mode
orchestrator = KGPipelineOrchestrator(
    enable_questioning=False,    # Don't ask user - save to DB
    enable_implementation=False  # Don't execute - save for review
)

# Run the pipeline - adjust max_nodes as needed
print("Analyzing up to 10 nodes...")
result = orchestrator.run_pipeline(max_nodes=10)

print("\n" + "="*60)
print("✅ Pipeline Complete!")
print("="*60)
print(f"📊 Results:")
print(f"   - Nodes analyzed: {result.total_nodes_identified}")
print(f"   - Problematic nodes found: {len(result.problematic_nodes)}")
print(f"   - Validated by critic: {result.nodes_validated}")
print(f"   - Saved to kg_reviews: {result.nodes_questioned}")
print(f"   - Skipped: {result.nodes_skipped}")
print(f"\n💡 Next step: Run 'python kg_review_dashboard_web.py' to review findings!")

