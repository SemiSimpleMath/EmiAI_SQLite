#!/usr/bin/env python3
"""
Analyze Delete Candidates
Extract nodes marked for deletion and analyze their context windows with the parser
"""

import os
import sys
import json
from datetime import datetime
from typing import List, Dict, Any

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node
from app.models.node_analysis_tracking import NodeAnalysisTracking
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message


def get_delete_candidates() -> List[Dict[str, Any]]:
    """Get all nodes marked for deletion with their context windows"""
    session = get_session()
    
    try:
        # Query nodes marked for deletion
        delete_analyses = session.query(NodeAnalysisTracking).filter(
            NodeAnalysisTracking.is_suspect == True,
            NodeAnalysisTracking.suggested_action == 'delete'
        ).all()
        
        print(f"🔍 Found {len(delete_analyses)} nodes marked for deletion")
        
        delete_candidates = []
        for analysis in delete_analyses:
            try:
                # Check if node still exists
                current_node = session.query(Node).filter(Node.id == analysis.node_id).first()
                
                if current_node:
                    # Get context window from the node (updated for new schema)
                    context_window = ""
                    if current_node.attributes:
                        context_window = current_node.attributes.get('context_window', '')
                        if not context_window:
                            context_window = current_node.attributes.get('context', '')
                    
                    # If no context from attributes, try to get from connected edges
                    if not context_window:
                        sample_edge = session.query(Edge).filter(
                            (Edge.source_id == current_node.id) | (Edge.target_id == current_node.id)
                        ).filter(Edge.sentence.isnot(None)).first()
                        if sample_edge and sample_edge.sentence:
                            context_window = sample_edge.sentence
                    
                    candidate = {
                        'node_id': str(analysis.node_id),
                        'label': current_node.label,
                        'type': current_node.node_type,
                        'context_window': context_window,
                        'sentence': '',  # sentence field removed from Node schema
                        'suspect_reason': analysis.suspect_reason or '',
                        'confidence': analysis.confidence or 0.0,
                        'cleanup_priority': analysis.cleanup_priority or 'none'
                    }
                    delete_candidates.append(candidate)
                else:
                    print(f"⚠️ Node {analysis.node_id} was deleted, skipping")
                    
            except Exception as e:
                print(f"⚠️ Error processing node {analysis.node_id}: {e}")
                continue
        
        print(f"✅ Extracted {len(delete_candidates)} delete candidates with context windows")
        return delete_candidates
        
    finally:
        session.close()


def test_parser_with_context(context_window: str, node_info: Dict[str, Any]) -> Dict[str, Any]:
    """Test the parser agent with a context window"""
    try:
        # Create parser agent
        parser_agent = DI.agent_factory.create_agent("knowledge_graph_add::parser")
        
        # Run parser
        parser_input = {"text": context_window}
        result = parser_agent.action_handler(Message(agent_input=parser_input))
        
        if result and result.data:
            parsed_sentences = result.data.get("parsed_sentences", [])
            reasoning = result.data.get("reasoning", "")
            
            return {
                "success": True,
                "parsed_sentences": parsed_sentences,
                "reasoning": reasoning,
                "sentence_count": len(parsed_sentences)
            }
        else:
            return {
                "success": False,
                "error": "Parser failed to return results"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Parser error: {str(e)}"
        }


def analyze_with_fact_extractor(max_candidates: int = 10) -> Dict[str, Any]:
    """Analyze context windows using fact_extractor to create nodes"""
    
    print("🔍 Analyzing Context Windows with Fact Extractor")
    print("=" * 60)
    
    # Get delete candidates
    candidates = get_delete_candidates()
    
    if not candidates:
        print("❌ No delete candidates found")
        return {"success": False, "message": "No delete candidates found"}
    
    # Deduplicate by context window to avoid processing same context multiple times
    seen_contexts = set()
    unique_candidates = []
    duplicate_count = 0
    
    for candidate in candidates:
        context = candidate['context_window']
        if context and context.strip() and context not in seen_contexts:
            seen_contexts.add(context)
            unique_candidates.append(candidate)
        else:
            duplicate_count += 1
    
    print(f"📊 Found {len(candidates)} total candidates")
    print(f"📊 {len(unique_candidates)} unique contexts (skipped {duplicate_count} duplicates)")
    
    # Limit analysis to avoid overwhelming output
    if len(unique_candidates) > max_candidates:
        print(f"📊 Limiting analysis to first {max_candidates} unique contexts")
        unique_candidates = unique_candidates[:max_candidates]
    
    # Create fact extractor agent
    try:
        fact_extractor_agent = DI.agent_factory.create_agent("knowledge_graph_add::fact_extractor")
        print("✅ Fact extractor agent created successfully")
    except Exception as e:
        print(f"❌ Failed to create fact extractor agent: {e}")
        return {"success": False, "error": f"Failed to create fact extractor agent: {e}"}
    
    analysis_results = []
    
    for i, candidate in enumerate(unique_candidates, 1):
        print(f"\n🔍 Analyzing Context {i}/{len(unique_candidates)} with Fact Extractor")
        print(f"Node: {candidate['label']} ({candidate['type']})")
        print(f"Priority: {candidate['cleanup_priority']}")
        print(f"Confidence: {candidate['confidence']}")
        print(f"Reason: {candidate['suspect_reason'][:100]}...")
        print(f"Context Window Length: {len(candidate['context_window'])} characters")
        
        if not candidate['context_window']:
            print("⚠️ No context window available")
            analysis_results.append({
                "candidate": candidate,
                "fact_extractor_result": {"success": False, "error": "No context window available"}
            })
            continue
        
        try:
            # Step 1: Parse the context window (mimicking kg_pipeline)
            print("📤 Step 1: Parsing context window...")
            parser_agent = DI.agent_factory.create_agent("knowledge_graph_add::parser")
            parser_input = {
                "text": candidate['context_window']
            }
            parser_result = parser_agent.action_handler(Message(agent_input=parser_input)).data or {}
            
            parsed_sentences = parser_result.get("parsed_sentences", [])
            
            if not parsed_sentences:
                print("❌ Parser failed: No sentences extracted")
                analysis_results.append({
                    "candidate": candidate,
                    "fact_extractor_result": {"success": False, "error": "Parser failed - no sentences"}
                })
                continue
            
            print(f"✅ Parser extracted {len(parsed_sentences)} sentences")
            
            # Extract sentence texts (mimicking kg_pipeline)
            all_atomic_sentences = []
            for parsed_sentence in parsed_sentences:
                if isinstance(parsed_sentence, dict):
                    sentence_text = parsed_sentence.get('sentence', '')
                else:
                    # Handle Pydantic ParsedSentence objects
                    sentence_text = parsed_sentence.sentence
                all_atomic_sentences.append(sentence_text)
            
            print(f"📝 Atomic sentences: {all_atomic_sentences}")
            
            # Step 2: Use parsed sentences with fact extractor (mimicking kg_pipeline)
            print("📤 Step 2: Sending parsed sentences to fact extractor...")
            fact_extractor_input = {
                "text": all_atomic_sentences  # Use parsed sentences, NOT raw context
            }
            
            # Call fact extractor
            result = fact_extractor_agent.action_handler(Message(agent_input=fact_extractor_input))
            
            if result and result.data:
                extractions = result.data.get('extractions', [])
                reasoning = result.data.get('reasoning', '')
                
                print(f"✅ Fact extractor successful!")
                print(f"📊 Extracted {len(extractions)} extractions")
                print(f"🧠 Reasoning: {reasoning[:200]}...")
                
                # Count nodes and edges
                total_nodes = 0
                total_edges = 0
                node_types = {}
                edge_types = {}
                
                for extraction in extractions:
                    nodes = extraction.get('nodes', [])
                    edges = extraction.get('edges', [])
                    
                    total_nodes += len(nodes)
                    total_edges += len(edges)
                    
                    # Count node types
                    for node in nodes:
                        node_type = node.get('node_type', 'Unknown')
                        node_types[node_type] = node_types.get(node_type, 0) + 1
                    
                    # Count edge types
                    for edge in edges:
                        edge_type = edge.get('label', 'Unknown')
                        edge_types[edge_type] = edge_types.get(edge_type, 0) + 1
                
                print(f"📊 Total nodes: {total_nodes}")
                print(f"📊 Total edges: {total_edges}")
                print(f"📊 Node types: {node_types}")
                print(f"📊 Edge types: {edge_types}")
                
                analysis_results.append({
                    "candidate": candidate,
                    "parser_result": parser_result,
                    "fact_extractor_result": {
                        "success": True,
                        "extractions": extractions,
                        "reasoning": reasoning,
                        "total_nodes": total_nodes,
                        "total_edges": total_edges,
                        "node_types": node_types,
                        "edge_types": edge_types,
                        "parsed_sentences_used": all_atomic_sentences
                    }
                })
            else:
                print("❌ Fact extractor returned no results")
                analysis_results.append({
                    "candidate": candidate,
                    "parser_result": parser_result,
                    "fact_extractor_result": {
                        "success": False,
                        "error": "No results returned from fact extractor",
                        "parsed_sentences_used": all_atomic_sentences
                    }
                })
                
        except Exception as e:
            print(f"❌ Error: {e}")
            analysis_results.append({
                "candidate": candidate,
                "parser_result": {"success": False, "error": f"Error: {str(e)}"},
                "fact_extractor_result": {
                    "success": False,
                    "error": f"Error: {str(e)}"
                }
            })
    
    # Save results to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"delete_candidates_fact_extractor_analysis_{timestamp}.json"
    
    report = {
        "timestamp": str(datetime.now()),
        "total_candidates_found": len(candidates),
        "unique_contexts_found": len(unique_candidates),
        "duplicate_contexts_skipped": duplicate_count,
        "contexts_analyzed": len(analysis_results),
        "analysis_results": analysis_results
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Fact extractor analysis report saved to: {output_file}")
    
    # Summary statistics
    successful_extractions = sum(1 for r in analysis_results if r['fact_extractor_result']['success'])
    total_nodes_extracted = sum(r['fact_extractor_result'].get('total_nodes', 0) for r in analysis_results if r['fact_extractor_result']['success'])
    total_edges_extracted = sum(r['fact_extractor_result'].get('total_edges', 0) for r in analysis_results if r['fact_extractor_result']['success'])
    
    print(f"\n📊 FACT EXTRACTOR SUMMARY:")
    print(f"  Total delete candidates found: {len(candidates)}")
    print(f"  Unique contexts found: {len(unique_candidates)}")
    print(f"  Duplicate contexts skipped: {duplicate_count}")
    print(f"  Contexts analyzed: {len(analysis_results)}")
    print(f"  Successful fact extractions: {successful_extractions}")
    print(f"  Total nodes extracted: {total_nodes_extracted}")
    print(f"  Total edges extracted: {total_edges_extracted}")
    print(f"  Average nodes per context: {total_nodes_extracted/max(1, successful_extractions):.1f}")
    print(f"  Average edges per context: {total_edges_extracted/max(1, successful_extractions):.1f}")
    
    return {
        "success": True,
        "total_candidates_found": len(candidates),
        "unique_contexts_found": len(unique_candidates),
        "duplicate_contexts_skipped": duplicate_count,
        "contexts_analyzed": len(analysis_results),
        "successful_extractions": successful_extractions,
        "total_nodes_extracted": total_nodes_extracted,
        "total_edges_extracted": total_edges_extracted,
        "output_file": output_file
    }


def analyze_delete_candidates(max_candidates: int = 10) -> Dict[str, Any]:
    """Analyze delete candidates by feeding their context windows to the parser"""
    
    print("🔍 Analyzing Delete Candidates with Parser")
    print("=" * 60)
    
    # Get delete candidates
    candidates = get_delete_candidates()
    
    if not candidates:
        print("❌ No delete candidates found")
        return {"success": False, "message": "No delete candidates found"}
    
    # Deduplicate by context window to avoid processing same context multiple times
    seen_contexts = set()
    unique_candidates = []
    duplicate_count = 0
    
    for candidate in candidates:
        context = candidate['context_window']
        if context and context.strip() and context not in seen_contexts:
            seen_contexts.add(context)
            unique_candidates.append(candidate)
        else:
            duplicate_count += 1
    
    print(f"📊 Found {len(candidates)} total candidates")
    print(f"📊 {len(unique_candidates)} unique contexts (skipped {duplicate_count} duplicates)")
    
    # Limit analysis to avoid overwhelming output
    if len(unique_candidates) > max_candidates:
        print(f"📊 Limiting analysis to first {max_candidates} unique contexts")
        unique_candidates = unique_candidates[:max_candidates]
    
    analysis_results = []
    
    for i, candidate in enumerate(unique_candidates, 1):
        print(f"\n🔍 Analyzing Unique Context {i}/{len(unique_candidates)}")
        print(f"Node: {candidate['label']} ({candidate['type']})")
        print(f"Priority: {candidate['cleanup_priority']}")
        print(f"Confidence: {candidate['confidence']}")
        print(f"Reason: {candidate['suspect_reason'][:100]}...")
        print(f"Context Window Length: {len(candidate['context_window'])} characters")
        
        if not candidate['context_window']:
            print("⚠️ No context window available")
            analysis_results.append({
                "candidate": candidate,
                "parser_result": {"success": False, "error": "No context window"}
            })
            continue
        
        # Test parser with context window
        parser_result = test_parser_with_context(candidate['context_window'], candidate)
        
        if parser_result['success']:
            print(f"✅ Parser extracted {parser_result['sentence_count']} sentences")
            print(f"Reasoning: {parser_result['reasoning'][:200]}...")
            
            # Show first few parsed sentences
            for j, sentence in enumerate(parser_result['parsed_sentences'][:3], 1):
                if isinstance(sentence, dict):
                    print(f"  {j}. {sentence.get('sentence', '')[:100]}...")
                else:
                    print(f"  {j}. {sentence.sentence[:100]}...")
            
            if len(parser_result['parsed_sentences']) > 3:
                print(f"  ... and {len(parser_result['parsed_sentences']) - 3} more sentences")
        else:
            print(f"❌ Parser failed: {parser_result['error']}")
        
        analysis_results.append({
            "candidate": candidate,
            "parser_result": parser_result
        })
    
    # Save results to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"delete_candidates_analysis_{timestamp}.json"
    
    report = {
        "timestamp": str(datetime.now()),
        "total_candidates_found": len(candidates),
        "unique_contexts_found": len(unique_candidates),
        "duplicate_contexts_skipped": duplicate_count,
        "contexts_analyzed": len(analysis_results),
        "analysis_results": analysis_results
    }
    
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Analysis report saved to: {output_file}")
    
    # Summary statistics
    successful_parses = sum(1 for r in analysis_results if r['parser_result']['success'])
    total_sentences = sum(r['parser_result'].get('sentence_count', 0) for r in analysis_results if r['parser_result']['success'])
    
    print(f"\n📊 SUMMARY:")
    print(f"  Total delete candidates found: {len(candidates)}")
    print(f"  Unique contexts found: {len(unique_candidates)}")
    print(f"  Duplicate contexts skipped: {duplicate_count}")
    print(f"  Contexts analyzed: {len(analysis_results)}")
    print(f"  Successful parses: {successful_parses}")
    print(f"  Total sentences extracted: {total_sentences}")
    print(f"  Average sentences per context: {total_sentences/max(1, successful_parses):.1f}")
    
    return {
        "success": True,
        "total_candidates_found": len(candidates),
        "unique_contexts_found": len(unique_candidates),
        "duplicate_contexts_skipped": duplicate_count,
        "contexts_analyzed": len(analysis_results),
        "successful_parses": successful_parses,
        "total_sentences": total_sentences,
        "output_file": output_file
    }


if __name__ == "__main__":
    import app.assistant.tests.test_setup  # This is just run for the import
    import sys
    
    # Set test database
    os.environ['USE_TEST_DB'] = 'true'
    os.environ['TEST_DB_NAME'] = 'test_emidb'
    
    print("🧪 Delete Candidates Analysis Tool")
    print("=" * 60)
    print("This tool analyzes nodes marked for deletion by replaying their context through")
    print("the parser and/or fact extractor to understand why they were created.")
    print()
    
    # Parse command line arguments
    max_candidates = 2
    method = 'both'
    
    if len(sys.argv) > 1:
        try:
            max_candidates = int(sys.argv[1])
            print(f"📊 Analyzing up to {max_candidates} candidates")
        except ValueError:
            print("⚠️ Invalid number, using default of 10 candidates")
    
    if len(sys.argv) > 2:
        method = sys.argv[2].lower()
        if method not in ['parser', 'fact_extractor', 'both']:
            print("⚠️ Invalid method, using 'both'")
            method = 'both'
        print(f"🔧 Analysis method: {method}")
    
    # Run parser analysis
    if method in ['parser', 'both']:
        print("\n📊 PART 1: Parser Analysis")
        print("=" * 30)
        result1 = analyze_delete_candidates(max_candidates=max_candidates)
        
        if result1['success']:
            print(f"\n✅ Parser analysis completed successfully!")
            print(f"📄 Parser report saved to: {result1['output_file']}")
        else:
            print(f"\n❌ Parser analysis failed: {result1.get('message', 'Unknown error')}")
    
    # Run fact extractor analysis
    if method in ['fact_extractor', 'both']:
        print("\n📊 PART 2: Fact Extractor Analysis")
        print("=" * 30)
        result2 = analyze_with_fact_extractor(max_candidates=max_candidates)
        
        if result2['success']:
            print(f"\n✅ Fact extractor analysis completed successfully!")
            print(f"📄 Fact extractor report saved to: {result2['output_file']}")
        else:
            print(f"\n❌ Fact extractor analysis failed: {result2.get('error', 'Unknown error')}")
    
    print("\n" + "=" * 60)
    print("🏁 Delete candidates analysis finished")
    print("🎯 Use the generated reports to understand why bad nodes were created.")
