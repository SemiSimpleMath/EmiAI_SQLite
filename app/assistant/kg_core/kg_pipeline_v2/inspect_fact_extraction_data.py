#!/usr/bin/env python3
"""
Inspect Fact Extraction Data

This script inspects the actual data stored in fact extraction results
to understand the data structure and debug the metadata stage.
"""

import sys
import os

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

# Import test setup to initialize services
import app.assistant.tests.test_setup

from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.database_schema import StageResult
import json

def inspect_fact_extraction_data():
    """Inspect fact extraction results in the database"""
    print("🔍 Inspecting Fact Extraction Data")
    print("=" * 50)
    
    session = get_session()
    
    try:
        # Get all fact extraction results
        fact_results = session.query(StageResult).filter(
            StageResult.stage_name == 'fact_extraction'
        ).all()
        
        print(f"📊 Found {len(fact_results)} fact extraction results")
        
        for i, result in enumerate(fact_results):
            print(f"\n📋 Fact Extraction Result {i+1}:")
            print(f"   Node ID: {result.node_id}")
            print(f"   Created: {result.created_at}")
            
            # Get the result data
            result_data = result.result_data
            print(f"   Data keys: {list(result_data.keys())}")
            
            # Check if extracted_facts exists
            if 'extracted_facts' in result_data:
                extracted_facts = result_data['extracted_facts']
                print(f"   Extracted facts type: {type(extracted_facts)}")
                print(f"   Extracted facts length: {len(extracted_facts) if isinstance(extracted_facts, list) else 'N/A'}")
                
                if isinstance(extracted_facts, list) and len(extracted_facts) > 0:
                    print(f"   First fact keys: {list(extracted_facts[0].keys()) if isinstance(extracted_facts[0], dict) else 'N/A'}")
                    print(f"   First fact atomic_sentence: {extracted_facts[0].get('atomic_sentence', 'N/A')[:100]}...")
                else:
                    print("   ⚠️ No extracted facts found or empty list")
            else:
                print("   ❌ No 'extracted_facts' key found in result data")
            
            # Show a sample of the data structure
            print(f"   Sample data structure:")
            print(f"   {json.dumps(result_data, indent=2, default=str)[:500]}...")
        
    except Exception as e:
        print(f"❌ Error inspecting fact extraction data: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    inspect_fact_extraction_data()
