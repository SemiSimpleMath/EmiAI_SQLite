"""
Master script to create and seed ALL knowledge graph tables.

Runs in correct dependency order:
1. Core KG tables (nodes, edges, ENUM)
2. Taxonomy tables
3. Standardization tables (label_canon, edge_canon)
4. Seed core data

Usage:
    python app/assistant/kg_core/kg_setup/setup_all_kg_tables.py
    
    OR from kg_setup directory:
    cd app/assistant/kg_core/kg_setup
    python setup_all_kg_tables.py
"""

import sys
import subprocess
from pathlib import Path

def run_script(script_name, description):
    """Run a Python script and handle errors."""
    print(f"\n{'='*80}")
    print(f"🔧 {description}")
    print(f"   Script: {script_name}")
    print(f"{'='*80}")
    
    script_path = Path(script_name)
    if not script_path.exists():
        print(f"⚠️  SKIPPED: {script_name} not found")
        return True
    
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=False,
            text=True,
            check=True
        )
        print(f"✅ SUCCESS: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FAILED: {description}")
        print(f"   Error: {e}")
        return False
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        return False

def main():
    print("\n" + "="*80)
    print("🚀 KNOWLEDGE GRAPH SETUP - FULL INITIALIZATION")
    print("="*80)
    print("\nThis will create and seed all KG tables in the correct order.")
    print("Using official taxonomy ontology (~1500 types) - comprehensive, curated")
    print("Estimated time: 30-60 seconds\n")
    
    # Track failures
    failed_steps = []
    
    # ========================================
    # PHASE 1: Create Core KG Tables
    # ========================================
    print("\n" + "█"*80)
    print("█  PHASE 1: CORE KG TABLES")
    print("█"*80)
    
    # Import and call directly (more reliable than subprocess)
    try:
        from app.assistant.kg_core.knowledge_graph_db_sqlite import initialize_knowledge_graph_db
        initialize_knowledge_graph_db()
        print("✅ SUCCESS: Core tables (nodes, edges, ENUM)")
    except Exception as e:
        print(f"❌ CRITICAL FAILURE: Core tables - {e}")
        failed_steps.append("Core tables creation")
        return 1
    
    # ========================================
    # PHASE 2: Create Taxonomy Tables
    # ========================================
    print("\n" + "█"*80)
    print("█  PHASE 2: TAXONOMY TABLES")
    print("█"*80)
    
    # Import and call functions directly (more reliable than subprocess)
    try:
        from create_taxonomy_tables import create_taxonomy_tables
        create_taxonomy_tables()
        print("✅ SUCCESS: Taxonomy tables")
    except Exception as e:
        print(f"❌ FAILED: Taxonomy tables - {e}")
        failed_steps.append("Taxonomy tables")
    
    try:
        from create_taxonomy_suggestions_table import create_taxonomy_suggestions_table
        create_taxonomy_suggestions_table()
        print("✅ SUCCESS: Taxonomy suggestions table")
    except Exception as e:
        print(f"❌ FAILED: Taxonomy suggestions table - {e}")
        failed_steps.append("Taxonomy suggestions table")
    
    try:
        from create_taxonomy_review_tables import create_taxonomy_review_tables
        create_taxonomy_review_tables()
        print("✅ SUCCESS: Taxonomy review queue tables")
    except Exception as e:
        print(f"❌ FAILED: Taxonomy review queue tables - {e}")
        failed_steps.append("Taxonomy review queue tables")
    
    if not run_script("add_count_and_last_seen_to_taxonomy_links.py", "Add count and last_seen to node_taxonomy_links"):
        # This may fail if columns already exist - not critical
        print("⚠️  Note: Count/last_seen columns may already exist")
    
    # ========================================
    # PHASE 3: Create Standardization Tables
    # ========================================
    print("\n" + "█"*80)
    print("█  PHASE 3: STANDARDIZATION TABLES")
    print("█"*80)
    
    if not run_script("setup_standardization_tables.py", "Create label_canon, label_alias, edge_canon, edge_alias tables"):
        # May need to use individual scripts
        print("⚠️  Trying individual table creation scripts...")
        if not run_script("create_edge_tables.py", "Create edge_canon and edge_alias tables"):
            failed_steps.append("Edge standardization tables")
    
    # ========================================
    # PHASE 4: Seed Data
    # ========================================
    print("\n" + "█"*80)
    print("█  PHASE 4: SEED DATA")
    print("█"*80)
    
    if not run_script("seed_core_nodes.py", "Seed Jukka and Emi nodes"):
        failed_steps.append("Core nodes seeding")
    
    if not run_script("seed_taxonomy_from_ontology.py", "Seed taxonomy from official ontology (~1500 types)"):
        failed_steps.append("Taxonomy seeding")
    
    if not run_script("seed_edge_types.py", "Seed edge type registry (~240 types + aliases)"):
        failed_steps.append("Edge types seeding")
    
    # ========================================
    # SUMMARY
    # ========================================
    print("\n" + "="*80)
    print("🏁 SETUP COMPLETE!")
    print("="*80)
    
    if failed_steps:
        print("\n⚠️  Some steps failed:")
        for step in failed_steps:
            print(f"   ❌ {step}")
        print("\nYou may need to run these scripts manually.")
        return 1
    else:
        print("\n✅ All tables created and seeded successfully!")
        print("\n📊 Ready to process knowledge graph data!")
        print("\nNext steps:")
        print("  1. Run: python -c \"from app.assistant.kg_core.kg_pipeline import main; main(limit=10)\"")
        print("  2. Check graph visualizer at: http://localhost:5000/graph-visualizer")
        return 0

if __name__ == "__main__":
    sys.exit(main())

