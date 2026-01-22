# kg_pipeline.py
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import uuid

# --- Assume these imports are correctly configured ---
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.knowledge_graph_utils import KnowledgeGraphUtils
from app.assistant.kg_core.knowledge_graph_db_sqlite import Edge, Node

from app.assistant.database.db_handler import UnifiedLog
from app.assistant.database.processed_entity_log import ProcessedEntityLog
from app.models.base import get_session
from sqlalchemy import select, func
from app.assistant.kg_core.log_preprocessing import read_unprocessed_logs_from_processed_entity_log

# --- End of imports ---

def is_html_message(message: str) -> bool:
    """
    Detect HTML messages from assistant, particularly search results.
    Looks for patterns that indicate structured HTML content like search results.
    """
    if not message or not isinstance(message, str):
        return False
    
    # Check for div tags with class attributes (common in search results)
    if '<div' in message and 'class=' in message:
        return True
    
    # Check for multiple consecutive div tags (search result pattern)
    if message.count('<div') > 2:
        return True
    
    return False


def find_conversation_boundaries(message_bounds: List[Dict], optimal_boundary_exclusive: int) -> Dict:
    """
    Find conversation boundaries in the current window.
    
    Args:
        message_bounds: List of message bounds from boundary agent
        optimal_boundary_exclusive: Optimal boundary position (exclusive)
        
    Returns:
        Dictionary with:
        - conversations: List of conversation objects with start_id, end_id, target_message_id, start_pos, end_pos
        - skipped_messages: List of message IDs that were skipped due to boundary/overlap filtering
    """
    # First deduplicate by (start_pos, end_pos) to avoid processing same span multiple times
    unique_conversations = {}
    skipped_messages = []
    
    for msg_bounds in message_bounds:
        if not msg_bounds["bounds"]["should_process"]:
            continue
        
        start_id = msg_bounds["bounds"]["start_message_id"]
        end_id = msg_bounds["bounds"]["end_message_id"]
        
        # Skip entries with empty message IDs (like analysis_summary)
        if not start_id or not end_id:
            print(f"--- Skipping entry with empty message IDs: {msg_bounds['message_id']}")
            continue
        
        # Extract positions
        start_pos = int(start_id.split('_')[1])
        end_pos = int(end_id.split('_')[1])
        
        # Use (start_pos, end_pos) as key to deduplicate
        span_key = (start_pos, end_pos)
        if span_key not in unique_conversations:
            unique_conversations[span_key] = {
                "start_id": start_id,
                "end_id": end_id,
                "target_message_id": msg_bounds["message_id"],
                "start_pos": start_pos,
                "end_pos": end_pos
            }
            print(f"--- Added unique conversation: {start_id} -> {end_id} (positions {start_pos}-{end_pos})")
        else:
            print(f"--- Skipping duplicate conversation: {start_id} -> {end_id} (positions {start_pos}-{end_pos})")
            # Track the target message as skipped
            skipped_messages.append(msg_bounds["message_id"])
    
    # Now filter by boundary and apply greedy non-overlap selection
    # Sort spans by end position, then accept only non-overlapping spans
    boundary_filtered = []
    for span_key, conversation in unique_conversations.items():
        start_pos, end_pos = span_key
        
        # Only consider conversations that end within our optimal boundary (exclusive)
        if end_pos < optimal_boundary_exclusive:
            boundary_filtered.append(conversation)
        else:
            print(f"--- Skipping conversation: {conversation['start_id']} -> {conversation['end_id']} (extends beyond boundary {optimal_boundary_exclusive})")
            # Track the target message as skipped due to boundary
            skipped_messages.append(conversation["target_message_id"])
    
    # Apply overlap merging: merge overlapping spans by taking min start to max end
    conversations_to_process = []
    
    # Sort by start position first, then end position
    sorted_conversations = sorted(boundary_filtered, key=lambda x: (x["start_pos"], x["end_pos"]))
    
    if sorted_conversations:
        # Start with the first conversation
        current_span = sorted_conversations[0].copy()
        print(f"--- Starting span: {current_span['start_id']} -> {current_span['end_id']} (positions {current_span['start_pos']}-{current_span['end_pos']})")
        
        for conversation in sorted_conversations[1:]:
            start_pos = conversation["start_pos"]
            end_pos = conversation["end_pos"]
            current_start = current_span["start_pos"]
            current_end = current_span["end_pos"]
            
            # Check if this conversation actually overlaps with the current span
            if start_pos <= current_end:  # Only merge if there's actual overlap
                # Merge: take min start to max end
                new_start = min(current_start, start_pos)
                new_end = max(current_end, end_pos)
                
                # Update current span
                current_span["start_pos"] = new_start
                current_span["end_pos"] = new_end
                current_span["start_id"] = f"msg_{new_start}"
                current_span["end_id"] = f"msg_{new_end}"
                
                print(f"--- Merged overlapping span: {conversation['start_id']} -> {conversation['end_id']} (positions {start_pos}-{end_pos}) into current span (now {new_start}-{new_end})")
            else:
                # No overlap, finalize current span and start new one
                conversations_to_process.append(current_span)
                print(f"--- Finalized span: {current_span['start_id']} -> {current_span['end_id']} (positions {current_span['start_pos']}-{current_span['end_pos']})")
                
                current_span = conversation.copy()
                print(f"--- Starting new span: {current_span['start_id']} -> {current_span['end_id']} (positions {current_span['start_pos']}-{current_span['end_pos']})")
        
        # Don't forget to add the last span
        conversations_to_process.append(current_span)
        print(f"--- Finalized final span: {current_span['start_id']} -> {current_span['end_id']} (positions {current_span['start_pos']}-{current_span['end_pos']})")
    
    # Apply fallback if no conversations were selected to prevent dropping messages
    if not conversations_to_process and optimal_boundary_exclusive > 0:
        print(f"    ⚠️ No explicit conversation spans found. Applying conservative fallback strategy.")
        
        # Instead of one massive conversation, create smaller, more reasonable fallback conversations
        # Process in chunks of max 10 messages to avoid massive context windows
        max_chunk_size = 10
        chunk_start = 0
        
        while chunk_start < optimal_boundary_exclusive:
            chunk_end = min(chunk_start + max_chunk_size - 1, optimal_boundary_exclusive - 1)
            
            conversations_to_process.append({
                "start_id": f"msg_{chunk_start}",
                "end_id": f"msg_{chunk_end}",
                "target_message_id": f"msg_{chunk_end}", # Target the last message in chunk for metadata
                "start_pos": chunk_start,
                "end_pos": chunk_end
            })
            print(f"    Created fallback conversation chunk: msg_{chunk_start} -> msg_{chunk_end} (positions {chunk_start}-{chunk_end})")
            
            chunk_start = chunk_end + 1
    
    print(f"--- Processing {len(conversations_to_process)} conversations in this window")
    return {
        "conversations": conversations_to_process,
        "skipped_messages": skipped_messages
    }


def extract_conversation_block(conversation: Dict, current_window: List[Dict]) -> Dict:
    """
    Extract conversation block and metadata from the current window.
    
    Args:
        conversation: Conversation object with start_pos, end_pos, target_message_id
        current_window: List of message entries from the log
        
    Returns:
        Dictionary with conversation_text, block_ids, data_source, original_message_timestamp_str
    """
    start_pos = conversation["start_pos"]
    end_pos = conversation["end_pos"]
    target_message_id = conversation["target_message_id"]
    
    # Get the conversation block from the current window
    conversation_block = []
    block_ids = []  # Collect all IDs in this block
    
    for idx in range(start_pos, end_pos + 1):
        if idx < len(current_window):
            entry = current_window[idx]
            message_text = entry.get("message", "").strip()
            role = entry.get("role", "unknown")
            
            # Add speaker identification to the message
            if message_text:
                formatted_message = f"{role}: {message_text}"
                conversation_block.append(formatted_message)
            
            # Collect all IDs in this block for processing
            if entry.get("id"):
                block_ids.append(entry["id"])
    
    # Join conversation block into single text with line breaks
    conversation_text = "\n".join(conversation_block)
    
    # Debug: Show what messages are in the conversation
    print(f"🔍 DEBUG: Conversation block contains {len(conversation_block)} messages:")
    user_count = sum(1 for msg in conversation_block if msg.startswith("user:"))
    assistant_count = sum(1 for msg in conversation_block if msg.startswith("assistant:"))
    print(f"   📊 Role distribution: {user_count} user messages, {assistant_count} assistant messages")
    for i, msg in enumerate(conversation_block[:5]):  # Show first 5 messages
        print(f"   {i+1}: {msg[:100]}...")
    if len(conversation_block) > 5:
        print(f"   ... and {len(conversation_block) - 5} more messages")
            
    # Get metadata from the target message
    target_idx = int(target_message_id.split('_')[1])
    data_source = "unknown"  # Default value
    original_message_timestamp_str = None
            
    if target_idx < len(current_window):
        entry = current_window[target_idx]
        data_source = entry.get("source", "unknown")
        original_message_timestamp = entry.get("timestamp", None)
        if original_message_timestamp:
            if isinstance(original_message_timestamp, str):
                original_message_timestamp_str = original_message_timestamp
            else:
                try:
                    original_message_timestamp_str = original_message_timestamp.isoformat()
                except Exception:
                    original_message_timestamp_str = str(original_message_timestamp)
                
    return {
        "conversation_text": conversation_text,
        "block_ids": block_ids,
        "data_source": data_source,
        "original_message_timestamp_str": original_message_timestamp_str
    }


def parse_conversation_sentences(
        conversation_text: str,
        parser_agent,
        original_message_timestamp_str: str = None
) -> Optional[Dict]:
    """
    Parse a single conversation block into atomic sentences.
    Returns None if nothing was parsed.
    """
    from typing import Optional, Dict, List

    parser_input = {"text": conversation_text}
    if original_message_timestamp_str:
        parser_input["original_message_timestamp"] = original_message_timestamp_str

    parser_result = parser_agent.action_handler(Message(agent_input=parser_input)).data or {}
    parsed_items = parser_result.get("parsed_sentences", [])

    print(f"--- Parser result keys: {list(parser_result.keys())}")
    print(f"--- Parsed sentences count: {len(parsed_items)}")

    if not parsed_items:
        print("--- No sentences parsed from conversation block")
        return None

    # Extract raw text for the current block only
    all_atomic_sentences: List[str] = []
    for item in parsed_items:
        if isinstance(item, dict):
            sentence_text = item.get("sentence", "")
        else:
            # Pydantic object case
            sentence_text = getattr(item, "sentence", "")
        if sentence_text:
            all_atomic_sentences.append(sentence_text)

    sentence_window_text = " ".join(all_atomic_sentences)
    return {
        "atomic_sentences": all_atomic_sentences,
        "sentence_window_text": sentence_window_text,
    }


def extract_facts_from_sentences(
        atomic_sentences: List[str],
        fact_extractor_agent,
        conversation_text: str,
        original_message_timestamp_str: str,
        fact_extractor_call_count: int
) -> Dict:
    """
    Extract facts for this chunk only.
    """
    print(f"--- 🎯 FACT EXTRACTOR CALL #{fact_extractor_call_count} - Processing {len(atomic_sentences)} sentences")

    fact_extractor_input = {"text": atomic_sentences}
    if original_message_timestamp_str:
        fact_extractor_input["original_message_timestamp"] = original_message_timestamp_str

    fact_extraction_result = fact_extractor_agent.action_handler(
        Message(agent_input=fact_extractor_input)
    ).data or {}

    nodes = fact_extraction_result.get("nodes", [])
    edges = fact_extraction_result.get("edges", [])
    
    # Map fact_extractor's 'core' field to 'category' for downstream compatibility
    for node in nodes:
        if "core" in node:
            node["category"] = node["core"]
    
    print(f"--- 📊 EXTRACTION: {len(nodes)} nodes and {len(edges)} edges")
    print(f"DEBUG: Fact extractor returned {len(nodes)} nodes and {len(edges)} edges")

    return {"original_nodes": nodes, "original_edges": edges}


def standardize_enriched_nodes(
        enriched_nodes: List[Dict],
        enriched_edges: List[Dict],
        standardizer_agent,
        edge_standardizer_agent,
        orchestrator
) -> Dict:
    """
    Standardize nodes and edges (after metadata enrichment) using standardizer agent.
    Generates semantic_label only - taxonomy classification handles type canonicalization.
    Each node and edge has its own 'sentence' field for context.
    """
    print(f"--- 🎨 STANDARDIZING {len(enriched_nodes)} nodes and {len(enriched_edges)} edges")
    
    # COMMENTED OUT: Standardizer agent removed - just set semantic_label = label
    standardized_nodes = []
    for i, node in enumerate(enriched_nodes):
        print(f"--- Standardizing node {i+1}/{len(enriched_nodes)}: {node.get('label', 'Unknown')}")
        # Set semantic_label equal to label to avoid breaking anything
        standardized_node = node.copy()
        standardized_node["semantic_label"] = node.get("label", "")
        standardized_nodes.append(standardized_node)
    
    # COMMENTED OUT: Edge standardizer agent removed - just pass edges through
    standardized_edges = []
    for i, edge in enumerate(enriched_edges):
        print(f"--- Processing edge {i+1}/{len(enriched_edges)}: {edge.get('label', 'unknown')}")
        # Just pass edges through without standardization
        standardized_edges.append(edge)
    
    print(f"--- ✅ STANDARDIZATION COMPLETE: {len(standardized_nodes)} nodes, {len(standardized_edges)} edges")
    
    return {"standardized_nodes": standardized_nodes, "standardized_edges": standardized_edges}


def add_metadata_to_nodes(
    original_nodes: List[Dict], 
    original_edges: List[Dict],
    meta_data_agent, 
    conversation_text: str, 
    original_message_timestamp_str: str
) -> Dict:
    """
    Enrich nodes with metadata using the metadata agent.
    Processes nodes one at a time for better focus and efficiency.
    
    Args:
        original_nodes: List of nodes from fact extractor
        original_edges: List of edges from fact extractor (not used, kept for compatibility)
        meta_data_agent: The metadata agent instance
        conversation_text: The original conversation text (sentence window for context)
        original_message_timestamp_str: The original message timestamp
        
    Returns:
        Dictionary with enriched_metadata
    """
    print(f"--- Enriching {len(original_nodes)} nodes with metadata (one at a time)...")
    print(f"--- DEBUG: conversation_text length: {len(conversation_text) if conversation_text else 0}")
    print(f"--- DEBUG: conversation_text preview: {conversation_text[:200] if conversation_text else 'EMPTY'}...")
    print(f"--- INFO: Each node will use its own specific sentence from fact extractor output")

    # Create a mapping of temp_id to enriched metadata
    enriched_metadata = {}
    
    for i, node in enumerate(original_nodes):
        temp_id = node.get("temp_id")
        if not temp_id:
            print(f"--- Skipping node {i+1}: no temp_id")
            continue
            
        print(f"--- Processing node {i+1}/{len(original_nodes)}: {node.get('label', 'Unknown')} (temp_id: {temp_id})")
        
        # Get the specific sentence that created this node
        node_sentence = node.get("sentence", "")
        if not node_sentence:
            print(f"--- ⚠️  Warning: No sentence found for node {node.get('label', 'Unknown')}")
            node_sentence = conversation_text  # Fallback to full conversation
        
        # Call metadata agent for this single node
        meta_data_input = {
            "nodes": json.dumps([node]),  # Single node in a list
            "resolved_sentence": node_sentence,  # Use the specific sentence that created this node
            "message_timestamp": original_message_timestamp_str  # CRITICAL: Pass message date for start/end date decisions
        }
        
        print(f"--- DEBUG: Using node-specific sentence: {node_sentence[:100]}...")
        print(f"--- DEBUG: resolved_sentence length: {len(node_sentence) if node_sentence else 0}")
        
        try:
            meta_data_msg = Message(agent_input=meta_data_input)
            meta_data_result = meta_data_agent.action_handler(meta_data_msg)
            
            if meta_data_result and hasattr(meta_data_result, 'data') and meta_data_result.data:
                enriched_nodes = meta_data_result.data.get("Nodes", [])
                if enriched_nodes and len(enriched_nodes) > 0:
                    enriched_node = enriched_nodes[0]  # Should be only one node
                    if enriched_node.get("temp_id") == temp_id:
                        enriched_metadata[temp_id] = enriched_node
                        print(f"--- ✅ Enriched metadata for node: {node.get('label', 'Unknown')}")
                    else:
                        print(f"--- ⚠️  Warning: temp_id mismatch in metadata result")
                else:
                    print(f"--- ⚠️  No enriched nodes returned for: {node.get('label', 'Unknown')}")
            else:
                print(f"--- ⚠️  No metadata result for: {node.get('label', 'Unknown')}")
                
        except Exception as e:
            print(f"--- ❌ Error enriching node {node.get('label', 'Unknown')}: {e}")
            # Continue with other nodes even if one fails
    
    print(f"--- Enriched metadata for {len(enriched_metadata)}/{len(original_nodes)} nodes")
    
    return {
        "enriched_metadata": enriched_metadata
    }


def process_nodes(
        original_nodes: List[Dict],
        enriched_metadata: Dict,
        original_edges: List[Dict],
        conversation_text: str,
        sentence_window_text: str,
        data_source: str,
        original_message_timestamp_str: str,
        kg_utils: KnowledgeGraphUtils,
        merge_agent,
        node_data_merger,
        # New parameters for message tracking
        block_ids: List[str] = None,
        sentence_id: str = None
) -> Dict:
    """
    Process nodes with selective metadata enrichment, smart merge logic, and creation.
    Returns a dict with a temp_id -> Node map and a passthrough edges list.
    """
    import json
    import uuid
    import logging
    from datetime import datetime

    logger = logging.getLogger(__name__)

    # ---------- helpers ----------
    def _normalize_iso(dt_val):
        """Accept None, empty, 'unknown', 'null', 'none', or ISO strings. Return datetime or None."""
        if dt_val is None:
            return None
        if isinstance(dt_val, datetime):
            return dt_val
        if isinstance(dt_val, str):
            s = dt_val.strip().lower()
            if s in {"", "unknown", "null", "none"}:
                return None
            try:
                # Handle trailing 'Z'
                if s.endswith("z"):
                    s = s[:-1] + "+00:00"
                return datetime.fromisoformat(s)
            except Exception:
                return None
        return None


    def _ensure_type(nt: str):
        """Validate node type against valid types."""
        # Valid node types: Entity, Event, State, Goal, Concept, Property
        valid_types = {'Entity', 'Event', 'State', 'Goal', 'Concept', 'Property'}
        if nt not in valid_types:
            logger.warning(f"Invalid node type '{nt}', will be rejected by database. Valid types: {valid_types}")
            # Let the database ENUM constraint handle the validation


    # ---------- step 1: selective metadata enrichment ----------
    nodes: List[Dict] = []
    for node in original_nodes:
        temp_id = node.get("temp_id")
        node_type = node.get("node_type") or ""
        
        # Attach source to node data - this flows through the pipeline without being sent to agents
        node["source"] = data_source

        if temp_id in enriched_metadata:
            enriched = enriched_metadata[temp_id]
            # Event-like: start, end, valid window
            if node_type in {"Event", "State", "Goal"}:
                if enriched.get("start_date"):
                    node["start_date"] = enriched["start_date"]
                if enriched.get("end_date"):
                    node["end_date"] = enriched["end_date"]
                if enriched.get("valid_during"):
                    node["valid_during"] = enriched["valid_during"]
                if enriched.get("start_date_confidence"):
                    node["start_date_confidence"] = enriched["start_date_confidence"]
                if enriched.get("end_date_confidence"):
                    node["end_date_confidence"] = enriched["end_date_confidence"]
            # State or property: semantic type
            if node_type in {"State", "Property"}:
                if enriched.get("semantic_label"):
                    node["semantic_label"] = enriched["semantic_label"]
            # Goal: goal status
            if node_type == "Goal":
                if enriched.get("goal_status"):
                    node["goal_status"] = enriched["goal_status"]
            
            # Always apply confidence and importance from metadata agent
            if enriched.get("confidence") is not None:
                node["confidence"] = enriched["confidence"]
            if enriched.get("importance") is not None:
                node["importance"] = enriched["importance"]
            
            # Apply aliases and hash_tags from metadata agent
            # Note: category comes from fact_extractor only, not metadata agent
            if enriched.get("aliases"):
                node["aliases"] = enriched["aliases"]
            if enriched.get("hash_tags"):
                node["hash_tags"] = enriched["hash_tags"]

        nodes.append(node)

    # ---------- step 2: passthrough edges ----------
    edges = list(original_edges)
    logger.debug("Edges passthrough count: %d", len(edges))

    # ---------- step 3: merge or create ----------
    node_map: Dict[str, object] = {}
    well_known_entities = {
        "jukka",
        "juka",  # keep common misspelling
        "emi",
        "emi_ai",
        "emi ai",
        "emi ai assistant",
        "emi_ai_assistant",
    }

    for node in nodes:
        temp_id = node.get("temp_id")
        label = node.get("label") or ""
        node_type = node.get("node_type") or ""
        category = node.get("category")

        # Prepare node data
        normalized_node_type = node_type.title() if node_type else "Unknown"
        _ensure_type(normalized_node_type)

        # Attributes to store on the node (only custom metadata, not promoted fields)
        base_attributes = {}
        # Note: start_date, end_date, valid_during, semantic_label, goal_status are now top-level columns
        # Only store custom metadata in attributes

        start_date = _normalize_iso(node.get("start_date"))
        end_date = _normalize_iso(node.get("end_date"))

        # Log node data before processing
        print(f"\n{'='*80}")
        print(f"🔄 PROCESSING NODE (checking for duplicates...)")
        print(f"{'='*80}")
        print(f"🏷️  LABEL: {label}")
        print(f"🔖 NODE_TYPE: {normalized_node_type}")
        print(f"📝 DESCRIPTION: {''}")
        print(f"🏷️  ALIASES: {node.get('aliases', [])}")
        print(f"📂 CATEGORY: {category}")
        print(f"📋 ATTRIBUTES: {base_attributes}")
        print(f"📅 START_DATE: {start_date}")
        print(f"📅 END_DATE: {end_date}")
        print(f"📊 START_DATE_CONFIDENCE: {node.get('start_date_confidence')}")
        print(f"📊 END_DATE_CONFIDENCE: {node.get('end_date_confidence')}")
        print(f"⏰ VALID_DURING: {node.get('valid_during')}")
        print(f"🏷️  HASH_TAGS: {node.get('hash_tags')}")
        print(f"🔍 SEMANTIC_LABEL: {node.get('semantic_label')}")
        print(f"🎯 GOAL_STATUS: {node.get('goal_status')}")
        print(f"📊 CONFIDENCE: {node.get('confidence')}")
        print(f"⭐ IMPORTANCE: {node.get('importance')}")
        print(f"📂 SOURCE: {node.get('source')}")
        print(f"{'='*80}")

        try:
            # Use add_node which checks for duplicates BEFORE creating the node
            new_node, status = kg_utils.add_node(
                node_type=normalized_node_type,
                label=label,
                aliases=node.get("aliases", []),
                description="",
                category=category,
                attributes=base_attributes,
                valid_during=node.get("valid_during"),
                hash_tags=node.get("hash_tags"),
                start_date=start_date,
                end_date=end_date,
                start_date_confidence=node.get("start_date_confidence"),
                end_date_confidence=node.get("end_date_confidence"),
                semantic_label=node.get("semantic_label"),
                goal_status=node.get("goal_status"),
                confidence=node.get("confidence"),
                importance=node.get("importance"),
                source=node.get("source"),
                # New schema fields (provenance - immutable)
                original_message_id=block_ids[0] if block_ids else None,  # Use first message ID as original
                original_sentence=node.get("sentence"),  # Sentence that created this node (immutable provenance)
                sentence_id=sentence_id,  # Pass the sentence ID from context
                # Merge agents
                merge_agent=merge_agent,
                node_data_merger=node_data_merger
            )
            node_map[temp_id] = new_node
            
            # Log what actually happened
            if status == "created":
                print(f"✅ NODE CREATED: '{label}' saved as new node (ID: {new_node.id})")
            elif status == "merged":
                print(f"🔀 NODE MERGED: '{label}' merged into existing node (ID: {new_node.id})")
            else:
                print(f"✅ NODE {status.upper()}: '{label}' (ID: {new_node.id})")
                    
        except Exception:
            logger.exception("Failed to create node: %s", label)
            raise

    # Ensure DB IDs are populated and release lock
    try:
        kg_utils.session.commit()  # Commit instead of flush - SQLite single-writer
    except Exception:
        logger.exception("Session commit failed")
        raise

    return {"node_map": node_map, "edges": edges}

def process_edges(
        edges: List[Dict],
        node_map: Dict,
        conversation_text: str,
        all_atomic_sentences: List[str],
        data_source: str,
        original_message_timestamp_str: str,
        kg_utils: KnowledgeGraphUtils,
        edge_merge_agent,
        conv_idx: int,
        # New parameters for message tracking
        block_ids: List[str] = None,
        sentence_id: str = None
) -> Dict:
    """
    Process edges with merge logic and creation. Returns processing statistics.
    """
    import json
    import logging
    from datetime import datetime

    logger = logging.getLogger(__name__)

    # ---------- helpers ----------
    def _normalize_edge_label(label: Optional[str]) -> str:
        return label.title() if label else "Unknown"

    def _build_edge_attributes() -> Dict[str, str]:
        # Only store custom metadata in attributes, not data that has dedicated columns
        return {
            # Note: data_source, original_message_timestamp, provenance_timestamp are now top-level columns
            # Only store custom metadata here
        }

    def _collect_candidate_contexts(similar_edges_list: List) -> List[Dict]:
        out = []
        for idx, cand in enumerate(similar_edges_list):
            try:
                ctx = kg_utils.get_edge_merge_context(cand)
            except Exception:
                logger.exception("get_edge_merge_context failed for candidate index %d", idx)
                ctx = {}
            ctx["candidate_id"] = idx + 1  # human-friendly 1-based id
            out.append(ctx)
        return out

    def _ask_merge_agent(source_label: str, target_label: str, rel_type: str, sentence: str, candidates_ctx: List[Dict]) -> Dict:
        try:
            merger_input = {
                "new_edge_data": json.dumps(
                    {
                        "relationship_type": rel_type,
                        "source_node_label": source_label,
                        "target_node_label": target_label,
                        "sentence": sentence or "No sentence provided.",
                    }
                ),
                "existing_edge_candidates": json.dumps(candidates_ctx),
            }
            resp = edge_merge_agent.action_handler(Message(agent_input=merger_input))
            return resp.data or {} if resp else {}
        except Exception:
            logger.exception("Edge merge agent failed")
            return {}

    # ---------- counters ----------
    edges_in = len(edges)
    edges_created = 0
    edges_merged = 0
    edges_skipped_missing_nodes = 0

    logger.debug("Process edges: count=%d, conv_idx=%d", edges_in, conv_idx)
    logger.debug("Node map keys: %s", list(node_map.keys())[:25])  # avoid huge logs

    sentence_window_text = " ".join(all_atomic_sentences) if all_atomic_sentences else ""

    # ---------- main loop ----------
    for edge_idx, edge_data in enumerate(edges):
        source_temp_id = edge_data.get("source")
        target_temp_id = edge_data.get("target")
        edge_label = edge_data.get("label")
        sentence = edge_data.get("sentence", "")

        logger.debug(
            "Edge %d/%d: %s -> %s -> %s",
            edge_idx + 1, edges_in, source_temp_id, edge_label, target_temp_id
        )

        source_node = node_map.get(source_temp_id)
        target_node = node_map.get(target_temp_id)

        if not source_node or not target_node:
            edges_skipped_missing_nodes += 1
            logger.warning(
                "Skipping edge due to missing nodes. source_exists=%s target_exists=%s source_temp_id=%s target_temp_id=%s",
                bool(source_node), bool(target_node), source_temp_id, target_temp_id
            )
            continue

        normalized_edge_label = _normalize_edge_label(edge_label)

        # Look for similar edges to possibly merge with
        try:
            similar_edges = kg_utils.find_similar_edges(
                source_id=source_node.id,
                target_id=target_node.id,
                relationship_type=normalized_edge_label,
                k=5,
            )
        except Exception:
            logger.exception("find_similar_edges failed")
            similar_edges = []

        if similar_edges:
            candidate_contexts = _collect_candidate_contexts(similar_edges)
            decision = _ask_merge_agent(
                source_node.label, target_node.label, normalized_edge_label, sentence, candidate_contexts
            )

            merged_id_str = decision.get("merged_edge_id")
            if decision.get("merge_edges") and merged_id_str is not None:
                try:
                    idx_0_based = int(merged_id_str) - 1
                    if 0 <= idx_0_based < len(similar_edges):
                        existing_edge = similar_edges[idx_0_based]
                        logger.info(
                            "Merged with existing edge: %s -> %s -> %s (edge_id=%s)",
                            getattr(existing_edge.source_node, "label", "?"),
                            getattr(existing_edge, "relationship_type", normalized_edge_label),
                            getattr(existing_edge.target_node, "label", "?"),
                            getattr(existing_edge, "id", None),
                        )
                        edges_merged += 1  # count reuse as a merge
                        continue
                    else:
                        logger.warning(
                            "Invalid merged_edge_id=%s (valid 1..%d). Will create new edge.",
                            merged_id_str, len(similar_edges)
                        )
                except (ValueError, TypeError):
                    logger.warning("Invalid merged_edge_id format: %s. Will create new edge.", merged_id_str)

        # No merge, create a new or idempotent edge
        edge_attributes = _build_edge_attributes()
        
        # Log all edge data before saving
        print(f"\n{'='*80}")
        print(f"🔗 SAVING NEW EDGE TO DATABASE")
        print(f"{'='*80}")
        print(f"📤 SOURCE_ID: {source_node.id}")
        print(f"📥 TARGET_ID: {target_node.id}")
        print(f"🏷️  RELATIONSHIP_TYPE: {normalized_edge_label}")
        print(f"📋 ATTRIBUTES: {edge_attributes}")
        print(f"📝 SENTENCE: {sentence}")
        print(f"📅 ORIGINAL_MESSAGE_TIMESTAMP: {original_message_timestamp_str}")
        print(f"📊 CONFIDENCE: {None} (will be set by metadata agent later)")
        print(f"⭐ IMPORTANCE: {None} (will be set by metadata agent later)")
        print(f"📂 SOURCE: {data_source}")
        print(f"{'='*80}")
        
        # Convert original_message_timestamp string to datetime object
        original_message_timestamp_dt = None
        if original_message_timestamp_str:
            try:
                original_message_timestamp_dt = datetime.fromisoformat(original_message_timestamp_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                original_message_timestamp_dt = None

        try:
            edge_obj, status = kg_utils.safe_add_relationship_by_id(
                source_id=source_node.id,
                target_id=target_node.id,
                relationship_type=normalized_edge_label,
                attributes=edge_attributes,
                sentence=sentence,
                original_message_timestamp=original_message_timestamp_dt,
                confidence=None,   # set later by metadata agent
                importance=None,   # set later by metadata agent
                source=data_source,
                # New schema fields
                original_message_id=block_ids[0] if block_ids else None,  # Use first message ID as original
                sentence_id=sentence_id,  # Pass the sentence ID from context
                relationship_descriptor=edge_data.get("relationship_descriptor"),  # Extract from edge data
            )
            if status == "created":
                edges_created += 1
            elif status == "merged":
                edges_merged += 1

            logger.info(
                "Edge %s -> %s -> %s %s (edge_id=%s)",
                source_node.label,
                normalized_edge_label,
                target_node.label,
                status.upper(),
                getattr(edge_obj, "id", None),
            )
        except Exception:
            logger.exception(
                "Failed to create edge: %s -> %s -> %s",
                getattr(source_node, "label", "?"),
                normalized_edge_label,
                getattr(target_node, "label", "?"),
            )
            raise

    # ---------- summary ----------
    logger.debug(
        "Edges summary: in=%d created=%d merged=%d skipped_missing_nodes=%d",
        edges_in, edges_created, edges_merged, edges_skipped_missing_nodes
    )

    # ---------- connectivity check ----------
    orphaned_nodes: List[Tuple[str, object]] = []
    for temp_id, node in node_map.items():
        has_edges = any(e.get("source") == temp_id or e.get("target") == temp_id for e in edges)
        if not has_edges:
            orphaned_nodes.append((temp_id, node))

    if orphaned_nodes:
        for temp_id, node in orphaned_nodes:
            logger.error("Orphaned node: %s (id=%s, temp_id=%s)", getattr(node, "label", "?"), getattr(node, "id", None), temp_id)
        raise RuntimeError(
            f"Data integrity violation: {len(orphaned_nodes)} nodes have no edges connecting them."
        )

    logger.info("Graph connectivity check passed. Nodes=%d", len(node_map))

    return {
        "edges_in": edges_in,
        "edges_created": edges_created,
        "edges_merged": edges_merged,
        "edges_skipped_missing_nodes": edges_skipped_missing_nodes,
    }


def commit_conversation_changes(kg_utils: KnowledgeGraphUtils, nodes_count: int, edges_count: int) -> None:
    """
    Commit conversation changes to the database.
    
    Args:
        kg_utils: KnowledgeGraphUtils instance
        nodes_count: Number of nodes processed
        edges_count: Number of edges processed
    """
    print(f"DEBUG: Before commit - Session is active: {kg_utils.session.is_active}")
    print(f"DEBUG: Before commit - Session is dirty: {kg_utils.session.dirty}")
    print(f"DEBUG: Before commit - Session is new: {kg_utils.session.new}")
    print(f"DEBUG: Before commit - Session has {len(kg_utils.session.new)} new objects")
    print(f"DEBUG: Before commit - Session has {len(kg_utils.session.dirty)} dirty objects")
    
    try:
        kg_utils.session.commit()
        print(f"--- Successfully processed {nodes_count} nodes and {edges_count} edges")
        print(f"SUCCESS: Database transaction committed - {nodes_count} nodes and {edges_count} edges saved to database")
    except Exception as e:
        print(f"ERROR: Database transaction failed: {e}")
        print(f"ERROR: Rolling back transaction...")
        kg_utils.session.rollback()
        import traceback
        traceback.print_exc()
        raise


# Configuration for adaptive window approach
# This implements an elegant sliding window logic:
# - Always assume message 1 is start of new conversation
# - Look for breaks between positions 15-20 first (future breaks)
# - If no future break, look for last break between positions 1-15 (past fallback)
# - If no break anywhere, use full 20-message window
# - Move window forward by processed size, repeat
# - Apply greedy non-overlap selection to prevent processing overlapping spans
# - Sort by (end_pos, start_pos) for deterministic selection
# - Fallback: if no conversations found, process the full boundary to prevent data loss
WINDOW_SIZE = 20  # Total window size for processing
THRESHOLD_POSITION = 15  # Look for breaks past this position first (future)
                          # If no future break, fallback to past breaks

def get_last_processed_timestamp(source_filter: Optional[str] = None, role_filter: Optional[List[str]] = None) -> Optional[datetime]:
    """
    Get the timestamp of the last processed log to avoid reprocessing.
    
    Args:
        source_filter: Optional source filter
        role_filter: Optional role filter
    
    Returns:
        Timestamp of last processed log, or None if no processed logs exist
    """
    session = get_session()
    try:
        query = select(UnifiedLog.timestamp).where(UnifiedLog.processed == True)
        
        if source_filter:
            query = query.where(UnifiedLog.source == source_filter)
        
        if role_filter:
            query = query.where(UnifiedLog.role.in_(role_filter))
        
        query = query.order_by(UnifiedLog.timestamp.desc()).limit(1)
        
        result = session.execute(query).scalar()
        return result
        
    except Exception as e:
        print(f"WARNING: Could not get last processed timestamp: {e}")
        return None
    finally:
        session.close()


def read_unprocessed_logs_from_unified_db(batch_size: int = 100, source_filter: Optional[str] = None, role_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Read unprocessed logs from the unified log database.
    
    Args:
        batch_size: Number of logs to fetch
        source_filter: Optional source filter (e.g., 'chat', 'slack', 'email')
        role_filter: Optional list of roles to filter by (e.g., ['user', 'assistant'])
    
    Returns:
        List of log entries in the format expected by process_text_to_kg
    """
    session = get_session()
    try:
        query = select(UnifiedLog).where(UnifiedLog.processed == False)
        
        if source_filter:
            query = query.where(UnifiedLog.source == source_filter)
        
        if role_filter:
            query = query.where(UnifiedLog.role.in_(role_filter))
        
        # Note: We rely on processed == False to avoid reprocessing
        # Using timestamp filter can starve old unprocessed rows
        # Safer approach: ORDER BY timestamp ASC to process oldest first
        query = query.order_by(UnifiedLog.timestamp.asc()).limit(batch_size)
        
        results = session.execute(query).scalars().all()
        
        # Get all unprocessed messages (without role filter) to check for role-filtered messages
        all_unprocessed_query = select(UnifiedLog).where(UnifiedLog.processed == False)
        if source_filter:
            all_unprocessed_query = all_unprocessed_query.where(UnifiedLog.source == source_filter)
        all_unprocessed_query = all_unprocessed_query.order_by(UnifiedLog.timestamp.asc()).limit(batch_size)
        all_unprocessed_results = session.execute(all_unprocessed_query).scalars().all()
        
        # Find messages that were filtered out by role filter
        selected_ids = {log.id for log in results}
        role_filtered_ids = [log.id for log in all_unprocessed_results if log.id not in selected_ids]
        
        log_entries = []
        html_messages_filtered = 0
        html_filtered_ids = []
        
        for log in results:
            # Filter out HTML messages at the source
            if is_html_message(log.message):
                print(f"📖 Filtering out HTML message: \"{log.message[:50]}...\"")
                html_messages_filtered += 1
                html_filtered_ids.append(log.id)
                continue

            entry = {
                "id": log.id,
                "message": log.message,
                "context_window": [],  # Unified log doesn't have context_window, so we'll use empty list
                "source": log.source,
                "timestamp": log.timestamp,
                "role": log.role
            }
            log_entries.append(entry)
        
        print(f"📖 Read {len(log_entries)} unprocessed logs from unified database")
        if html_messages_filtered > 0:
            print(f"🚫 Filtered out {html_messages_filtered} HTML messages at source")
            # Mark HTML-filtered messages as processed to avoid reprocessing them
            mark_logs_as_processed(html_filtered_ids)
            print(f"✅ Marked {len(html_filtered_ids)} HTML-filtered messages as processed")
        
        if role_filtered_ids:
            print(f"🚫 Filtered out {len(role_filtered_ids)} messages due to role filter")
            # Mark role-filtered messages as processed to avoid reprocessing them
            mark_logs_as_processed(role_filtered_ids)
            print(f"✅ Marked {len(role_filtered_ids)} role-filtered messages as processed")
        
        # No context needed - we'll use the adaptive window approach
        # Each window is self-contained and assumes message 1 is conversation start
        
        return log_entries
        
    except Exception as e:
        print(f"ERROR: Error reading from unified log: {e}")
        return []
    finally:
        session.close()

def find_optimal_window_boundary(message_bounds: List[Dict[str, Any]], window_size: int = WINDOW_SIZE, threshold: int = THRESHOLD_POSITION) -> int:
    """
    Find the optimal window boundary using your adaptive window approach.
    
    Logic:
    1. Look for breaks between threshold and window_size (future first)
    2. If no future break, look for last break between 1 and threshold (past fallback)
    3. If no break anywhere, use full window_size
    
    Args:
        message_bounds: List of conversation boundaries from the agent
        window_size: Total window size (default 20)
        threshold: Position to look for breaks first (default 15)
    
    Returns:
        Position to end the current window (exclusive)
    """
    if not message_bounds:
        return window_size  # No breaks found, use full window
    
    # Convert message bounds to positions
    boundaries = []
    for bound in message_bounds:
        if bound["bounds"]["should_process"]:
            start_id = bound["bounds"]["start_message_id"]
            end_id = bound["bounds"]["end_message_id"]
            
            # Skip entries with empty message IDs (like analysis_summary)
            if not start_id or not end_id:
                continue
            
            # Extract position from IDs like "msg_5" -> 5
            start_pos = int(start_id.split('_')[1])
            end_pos = int(end_id.split('_')[1])
            
            boundaries.append((start_pos, end_pos))
    
    if not boundaries:
        return window_size  # No valid boundaries, use full window
    
    # Sort boundaries by start position
    boundaries.sort(key=lambda x: x[0])
    
    # Strategy 1: Look for breaks between threshold and window_size (future first)
    future_breaks = [end_pos for start_pos, end_pos in boundaries if end_pos >= threshold]
    if future_breaks:
        # Found a break in the future - use the first one
        optimal_boundary_exclusive = min(future_breaks) + 1  # Make exclusive
        print(f"    🎯 Found future break at position {min(future_breaks)} (past threshold {threshold})")
        return optimal_boundary_exclusive
    
    # Strategy 2: No future breaks, look for last break between 1 and threshold
    past_breaks = [end_pos for start_pos, end_pos in boundaries if end_pos < threshold]
    if past_breaks:
        # Use the last break in the past
        optimal_boundary_exclusive = max(past_breaks) + 1  # Make exclusive
        print(f"    DEBUG: No future breaks, using past break at position {max(past_breaks)}")
        return optimal_boundary_exclusive
    
    # Strategy 3: No breaks anywhere, check if we have a single conversation spanning the window
    if boundaries:
        # We have boundaries but no breaks - this means one conversation spans the entire window
        # Find the actual end position of the conversation
        max_end_pos = max(end_pos for start_pos, end_pos in boundaries)
        optimal_boundary_exclusive = max_end_pos + 1  # Make exclusive
        print(f"    📏 Single conversation spans entire window, ending at position {max_end_pos}")
        return optimal_boundary_exclusive
    
    # Strategy 4: No boundaries at all, use full window
    print(f"    📏 No boundaries found, using full window size {window_size}")
    return window_size


# Context functions removed - no longer needed with adaptive window approach


def mark_logs_as_processed(log_ids: List[str]):
    """
    Mark logs as processed in the processed entity log database.
    
    Args:
        log_ids: List of log IDs to mark as processed
    """
    if not log_ids:
        return
        
    session = get_session()
    try:
        # Update the processed flag for the given log IDs in processed_entity_log
        session.query(ProcessedEntityLog).filter(ProcessedEntityLog.id.in_(log_ids)).update(
            {ProcessedEntityLog.processed: True}, 
            synchronize_session=False
        )
        session.commit()
        print(f"SUCCESS: Marked {len(log_ids)} processed entity logs as processed")
    except Exception as e:
        session.rollback()
        print(f"ERROR: Error marking logs as processed: {e}")
    finally:
        session.close()

# A more robust date parsing function
def parse_iso_or_none(date_str: Optional[str]) -> Optional[datetime]:
    """
    Robustly parses a string into a datetime object, handling common formats and None values.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None


def merge_node_aliases(existing_node: Node, new_node_label: str) -> List[str]:
    """
    Merge aliases from existing node and new node label.
    
    Args:
        existing_node: The existing node from the database
        new_node_label: The label of the new node being merged
        
    Returns:
        List of merged aliases (excluding the node's own label)
    """
    # Start with existing aliases (or empty list if None)
    existing_aliases = existing_node.aliases or []
    
    # Add the new node label if it's different from existing label and not already in aliases
    if new_node_label != existing_node.label and new_node_label not in existing_aliases:
        existing_aliases.append(new_node_label)
    
    # Remove the node's own label from aliases (aliases should only contain alternative names)
    if existing_node.label in existing_aliases:
        existing_aliases.remove(existing_node.label)
    
    # Remove duplicates and return
    return list(dict.fromkeys(existing_aliases))  # Preserves order while removing duplicates


def merge_node_information_with_agent(existing_node: Node, new_node_data: Dict, node_data_merger) -> None:
    """
    Merge node information using the node_data_merger agent for intelligent data combination.
    
    Args:
        existing_node: The existing node to update
        new_node_data: Dictionary containing new node information
        node_data_merger: The node data merger agent instance
    """
    from datetime import datetime
    
    # Prepare existing node data for the agent
    existing_node_data = {
        "label": existing_node.label,
        "aliases": existing_node.aliases or [],
        "hash_tags": existing_node.hash_tags or [],
        "semantic_label": existing_node.semantic_label,
        "goal_status": existing_node.goal_status,
        "valid_during": existing_node.valid_during,
        "category": existing_node.category,
        "start_date": existing_node.start_date.isoformat() if existing_node.start_date and hasattr(existing_node.start_date, 'isoformat') else existing_node.start_date,
        "end_date": existing_node.end_date.isoformat() if existing_node.end_date and hasattr(existing_node.end_date, 'isoformat') else existing_node.end_date,
        "start_date_confidence": existing_node.start_date_confidence,
        "end_date_confidence": existing_node.end_date_confidence,
        "confidence": existing_node.confidence,
        "importance": existing_node.importance,
        # Source is not sent to merge agent - it's just a tracking field
        # Nodes no longer have sentence fields - sentence context is on edges
    }
    
    # Prepare new node data for the agent
    agent_new_node_data = {
        "label": new_node_data.get("label", ""),
        "aliases": new_node_data.get("aliases", []),
        "hash_tags": new_node_data.get("hash_tags", []),
        "semantic_label": new_node_data.get("semantic_label"),
        "goal_status": new_node_data.get("goal_status"),
        "valid_during": new_node_data.get("valid_during"),
        "category": new_node_data.get("category"),
        "start_date": new_node_data.get("start_date"),
        "end_date": new_node_data.get("end_date"),
        "start_date_confidence": new_node_data.get("start_date_confidence"),
        "end_date_confidence": new_node_data.get("end_date_confidence"),
        "confidence": new_node_data.get("confidence"),
        "importance": new_node_data.get("importance"),
        # Source is not sent to merge agent - it's just a tracking field
        # Sentence context is now stored on edges, not nodes
    }
    
    # Call the node data merger agent
    merger_input = {
        "existing_node_data": json.dumps(existing_node_data),
        "new_node_data": json.dumps(agent_new_node_data)
    }
    
    merger_response = node_data_merger.action_handler(Message(agent_input=merger_input))
    merger_result = merger_response.data or {}
    
    # Enhanced logging for evaluation
    print(f"\n{'='*80}")
    print(f"🧠 NODE DATA MERGER AGENT OUTPUT")
    print(f"{'='*80}")
    print(f"📊 Merging nodes: '{existing_node.label}' + '{new_node_data.get('label', 'Unknown')}'")
    print(f"🎯 Agent Reasoning: {merger_result.get('reasoning', 'No reasoning provided')}")
    print(f"📈 Confidence Score: {merger_result.get('merge_confidence', 0.0):.2f}")
    print(f"{'='*80}")
    
    # Show before/after comparison for each field
    changes_made = []
    
    # Aliases comparison
    old_aliases = existing_node.aliases or []
    new_aliases = merger_result.get("merged_aliases")
    if new_aliases and new_aliases != old_aliases:
        existing_node.aliases = new_aliases
        changes_made.append("aliases")
        print(f"📝 ALIASES:")
        print(f"   Before: {old_aliases}")
        print(f"   After:  {new_aliases}")
        print(f"   Change: {'Added' if len(new_aliases) > len(old_aliases) else 'Modified'}")
    
    # Hash tags comparison
    old_tags = existing_node.hash_tags or []
    new_tags = merger_result.get("merged_hash_tags")
    if new_tags and new_tags != old_tags:
        existing_node.hash_tags = new_tags
        changes_made.append("hash_tags")
        print(f"🏷️  HASH TAGS:")
        print(f"   Before: {old_tags}")
        print(f"   After:  {new_tags}")
        print(f"   Change: {'Added' if len(new_tags) > len(old_tags) else 'Modified'}")
    
    # Semantic type comparison
    old_semantic_label = existing_node.semantic_label
    new_semantic_label = merger_result.get("unified_semantic_label")
    if new_semantic_label and new_semantic_label != old_semantic_label:
        existing_node.semantic_label = new_semantic_label
        changes_made.append("semantic_label")
        print(f"🔍 SEMANTIC TYPE:")
        print(f"   Before: {old_semantic_label}")
        print(f"   After:  {new_semantic_label}")
        print(f"   Change: {'More specific' if len(new_semantic_label) > len(old_semantic_label or '') else 'Updated'}")
    
    # Goal status comparison
    old_goal_status = existing_node.goal_status
    new_goal_status = merger_result.get("unified_goal_status")
    if new_goal_status and new_goal_status != old_goal_status:
        existing_node.goal_status = new_goal_status
        changes_made.append("goal_status")
        print(f"🎯 GOAL STATUS:")
        print(f"   Before: {old_goal_status}")
        print(f"   After:  {new_goal_status}")
        print(f"   Change: {'Added' if not old_goal_status else 'Updated'}")
    
    # Valid during comparison
    old_valid_during = existing_node.valid_during
    new_valid_during = merger_result.get("unified_valid_during")
    
    # CRITICAL: Entity nodes should not have valid_during - reset to blank
    if existing_node.node_type == 'Entity':
        if existing_node.valid_during:
            existing_node.valid_during = None
            changes_made.append("valid_during")
            print(f"⏰ VALID DURING:")
            print(f"   Before: {old_valid_during}")
            print(f"   After:  None (entity nodes don't have valid_during)")
            print(f"   Change: Reset to blank for entity node")
    elif new_valid_during and new_valid_during != old_valid_during:
        # Valid_during should be a simple temporal qualifier, not biographical text
        if len(new_valid_during) > 100:
            print(f"⚠️  WARNING: valid_during too long ({len(new_valid_during)} chars), should be simple temporal qualifier")
            print(f"⚠️  WARNING: Truncating to first 100 chars: {new_valid_during[:100]}...")
            new_valid_during = new_valid_during[:100] + "..."
        
        existing_node.valid_during = new_valid_during
        changes_made.append("valid_during")
        print(f"⏰ VALID DURING:")
        print(f"   Before: {old_valid_during}")
        print(f"   After:  {new_valid_during}")
        print(f"   Change: {'Added' if not old_valid_during else 'Updated'}")
    
    # Category comparison
    old_category = existing_node.category
    new_category = merger_result.get("unified_category")
    if new_category and new_category != old_category:
        existing_node.category = new_category
        changes_made.append("category")
        print(f"📂 CATEGORY:")
        print(f"   Before: {old_category}")
        print(f"   After:  {new_category}")
        print(f"   Change: {'More specific' if len(new_category) > len(old_category or '') else 'Updated'}")
    
    # Start date comparison
    old_start_date = existing_node.start_date
    new_start_date_str = merger_result.get("unified_start_date")
    # Filter out invalid date strings like "unknown", "null", etc.
    if new_start_date_str and new_start_date_str.lower() in ['unknown', 'null', 'none', '']:
        print(f"⚠️  WARNING: Agent returned invalid date string '{new_start_date_str}' - ignoring")
        new_start_date_str = None
    
    if new_start_date_str:
        try:
            new_start_date = datetime.fromisoformat(new_start_date_str)
            if new_start_date != old_start_date:
                existing_node.start_date = new_start_date
                # Also update confidence if provided
                new_start_confidence = merger_result.get("unified_start_date_confidence")
                if new_start_confidence:
                    existing_node.start_date_confidence = new_start_confidence
                changes_made.append("start_date")
                print(f"📅 START DATE:")
                print(f"   Before: {old_start_date}")
                print(f"   After:  {new_start_date}")
                print(f"   Confidence: {new_start_confidence or 'unchanged'}")
                print(f"   Change: {'Added' if not old_start_date else 'Updated (chose more accurate date)'}")
        except (ValueError, TypeError):
            print(f"⚠️  WARNING: Invalid start_date format: {new_start_date_str}")
    
    # End date comparison
    old_end_date = existing_node.end_date
    new_end_date_str = merger_result.get("unified_end_date")
    # Filter out invalid date strings like "unknown", "null", etc.
    if new_end_date_str and new_end_date_str.lower() in ['unknown', 'null', 'none', '']:
        print(f"⚠️  WARNING: Agent returned invalid date string '{new_end_date_str}' - ignoring")
        new_end_date_str = None
    
    if new_end_date_str:
        try:
            new_end_date = datetime.fromisoformat(new_end_date_str)
            if new_end_date != old_end_date:
                existing_node.end_date = new_end_date
                # Also update confidence if provided
                new_end_confidence = merger_result.get("unified_end_date_confidence")
                if new_end_confidence:
                    existing_node.end_date_confidence = new_end_confidence
                changes_made.append("end_date")
                print(f"📅 END DATE:")
                print(f"   Before: {old_end_date}")
                print(f"   After:  {new_end_date}")
                print(f"   Confidence: {new_end_confidence or 'unchanged'}")
                print(f"   Change: {'Added' if not old_end_date else 'Updated (chose more accurate date)'}")
        except (ValueError, TypeError):
            print(f"⚠️  WARNING: Invalid end_date format: {new_end_date_str}")
    
    # Algorithmically merge confidence and importance (take the higher value)
    new_confidence = new_node_data.get("confidence")
    new_importance = new_node_data.get("importance")
    
    if new_confidence is not None:
        old_confidence = existing_node.confidence
        if old_confidence is None or new_confidence > old_confidence:
            existing_node.confidence = new_confidence
            changes_made.append("confidence")
            print(f"📊 CONFIDENCE:")
            print(f"   Before: {old_confidence}")
            print(f"   After:  {new_confidence}")
            print(f"   Change: {'Added' if old_confidence is None else 'Increased (took higher value)'}")
    
    if new_importance is not None:
        old_importance = existing_node.importance
        if old_importance is None or new_importance > old_importance:
            existing_node.importance = new_importance
            changes_made.append("importance")
            print(f"⭐ IMPORTANCE:")
            print(f"   Before: {old_importance}")
            print(f"   After:  {new_importance}")
            print(f"   Change: {'Added' if old_importance is None else 'Increased (took higher value)'}")

    # Update timestamp
    existing_node.updated_at = datetime.utcnow()
    
    # Note: source field is intentionally NOT updated - it preserves the original source
    # (the first time this node was seen) for provenance tracking
    
    # Summary
    print(f"{'='*80}")
    if changes_made:
        print(f"✅ MERGE COMPLETED: Updated {len(changes_made)} field(s): {', '.join(changes_made)}")
    else:
        print(f"ℹ️  NO CHANGES: Agent determined no updates were needed")
    print(f"🕒 Timestamp updated: {existing_node.updated_at}")
    print(f"📂 Source preserved: {existing_node.source} (original source)")
    print(f"{'='*80}\n")


def merge_node_information(existing_node: Node, new_node_data: Dict, merge_decision: Dict) -> None:
    """
    Merge information from new node into existing node.
    
    Args:
        existing_node: The existing node to update
        new_node_data: Dictionary containing new node information
        merge_decision: The merge decision from the merge agent
    """
    from datetime import datetime
    
    # 1. Merge aliases
    new_label = new_node_data.get("label", "")
    if new_label:
        merged_aliases = merge_node_aliases(existing_node, new_label)
        if merged_aliases != existing_node.aliases:
            existing_node.aliases = merged_aliases
            print(f"--- Updated aliases for {existing_node.label}: {merged_aliases}")
    
    # 2. Update node type if merge agent provided unified_type
    unified_type = merge_decision.get("unified_type")
    if unified_type and unified_type != existing_node.node_type:
        existing_node.node_type = unified_type
        print(f"--- Updated node type for {existing_node.label}: {existing_node.node_type} -> {unified_type}")
    
    # 3. Update temporal information if new node has better data
    new_start_date = new_node_data.get("start_date")
    new_end_date = new_node_data.get("end_date")
    
    if new_start_date and (not existing_node.start_date or new_start_date < existing_node.start_date):
        existing_node.start_date = new_start_date
        print(f"--- Updated start_date for {existing_node.label}: {existing_node.start_date} -> {new_start_date}")
    
    if new_end_date and (not existing_node.end_date or new_end_date > existing_node.end_date):
        existing_node.end_date = new_end_date
        print(f"--- Updated end_date for {existing_node.label}: {existing_node.end_date} -> {new_end_date}")
    
    # 4. Merge hash_tags arrays
    new_hash_tags = new_node_data.get("hash_tags", [])
    if new_hash_tags:
        existing_tags = set(existing_node.hash_tags or [])
        new_tags = set(new_hash_tags)
        merged_tags = list(existing_tags.union(new_tags))
        if merged_tags != (existing_node.hash_tags or []):
            existing_node.hash_tags = merged_tags
            print(f"--- Updated hash_tags for {existing_node.label}: {merged_tags}")
    
    # 5. Update semantic_label if new node has more specific type
    new_semantic_label = new_node_data.get("semantic_label")
    if new_semantic_label and (not existing_node.semantic_label or len(new_semantic_label) > len(existing_node.semantic_label)):
        existing_node.semantic_label = new_semantic_label
        print(f"--- Updated semantic_label for {existing_node.label}: {existing_node.semantic_label} -> {new_semantic_label}")
    
    # 6. Update goal_status if new node has status info
    new_goal_status = new_node_data.get("goal_status")
    if new_goal_status and not existing_node.goal_status:
        existing_node.goal_status = new_goal_status
        print(f"--- Updated goal_status for {existing_node.label}: {new_goal_status}")
    
    # 7. Update valid_during if new node has temporal info
    new_valid_during = new_node_data.get("valid_during")
    if new_valid_during and not existing_node.valid_during:
        existing_node.valid_during = new_valid_during
        print(f"--- Updated valid_during for {existing_node.label}: {new_valid_during}")
    
    # 8. Update category if new node has better category
    new_category = new_node_data.get("category")
    if new_category and (not existing_node.category or len(new_category) > len(existing_node.category)):
        existing_node.category = new_category
        print(f"--- Updated category for {existing_node.label}: {existing_node.category} -> {new_category}")
    
    # 9. Update timestamp
    existing_node.updated_at = datetime.utcnow()
    print(f"--- Updated timestamp for {existing_node.label}")


def model_to_dict(instance: Any) -> Dict[str, Any]:
    """
    Robustly converts a SQLAlchemy model instance to a dictionary,
    excluding the 'embedding' field.
    """
    if not instance:
        return {}
    columns = [c.key for c in instance.__class__.__mapper__.columns]
    d = {c: getattr(instance, c) for c in columns if c != 'embedding'}
    return d

# Valid node types: Entity, Event, State, Goal, Concept, Property
# Node types are validated at the application level


def process_text_to_kg(log_context_items: List[Dict[str, Any]], kg_utils: Optional[KnowledgeGraphUtils] = None):
    """
    The main pipeline function to process text entries and add them to the knowledge graph.

    Uses adaptive sliding windows to prevent false conversation starts at batch boundaries.
    This ensures that messages at the beginning of a batch have proper context from
    the previous conversation, improving the quality of boundary detection and fact extraction.

    The solution handles the conversation boundary problem using an adaptive window approach:
     1. Always assume message 1 is start of new conversation
     2. Look for breaks between positions 15-20 first (future breaks)
     3. If no future break, look for last break between positions 1-15 (past fallback)
     4. If no break anywhere, use full 20-message window
     5. Process determined conversations and slide window forward
     6. Apply greedy non-overlap selection to prevent processing overlapping spans
     7. Fallback: if no conversations found, process the full boundary to prevent data loss
     8. Progress preservation: commit processed messages after each window to enable resume capability
    """
    print("\n" + "-" * 40 + " [KG PIPELINE START] " + "-" * 40)

    # Initialize utilities and agents
    kg_utils = kg_utils or KnowledgeGraphUtils()
    
    # Debug: Print which database we're using
    import os
    print(f"🔍 KG Pipeline Database Debug:")
    print(f"   USE_TEST_DB: {os.environ.get('USE_TEST_DB')}")
    print(f"   TEST_DB_NAME: {os.environ.get('TEST_DB_NAME')}")
    print(f"   Session engine URL: {kg_utils.session.bind.url}")
    print(f"   Database name: {kg_utils.session.bind.url.database}")
    
    parser_agent = DI.agent_factory.create_agent("knowledge_graph_add::parser")
    fact_extractor_agent = DI.agent_factory.create_agent("knowledge_graph_add::fact_extractor")
    # standardizer_agent = DI.agent_factory.create_agent("knowledge_graph_add::standardizer")
    # edge_standardizer_agent = DI.agent_factory.create_agent("knowledge_graph_add::edge_standardizer")
    meta_data_agent = DI.agent_factory.create_agent("knowledge_graph_add::meta_data_add")
    merge_agent = DI.agent_factory.create_agent("knowledge_graph_add::node_merger")
    node_data_merger = DI.agent_factory.create_agent("knowledge_graph_add::node_data_merger")
    edge_merge_agent = DI.agent_factory.create_agent("knowledge_graph_add::edge_merger")

    boundary_agent = DI.agent_factory.create_agent("knowledge_graph_add::conversation_boundary")
    
    # Initialize standardization orchestrator
    from app.assistant.kg_core.standardization_orchestrator import StandardizationOrchestrator
    orchestrator = StandardizationOrchestrator()

    # Track processed log IDs for unified log
    processed_log_ids = []
    
    # Track fact extractor calls to ensure one per block
    fact_extractor_call_count = 0

    # Process messages using adaptive window approach
    # Each window is self-contained and assumes message 1 is conversation start
    print(f"🔍 Processing with adaptive window approach")
    print(f"📊 Window size: {WINDOW_SIZE}, Threshold: {THRESHOLD_POSITION}")
    print(f"📊 Total messages available: {len(log_context_items)}")

    # Process messages in sliding windows of WINDOW_SIZE
    current_position = 0
    windows_processed = 0

    while current_position < len(log_context_items):
        # Get current window (up to WINDOW_SIZE messages)
        window_end = min(current_position + WINDOW_SIZE, len(log_context_items))
        current_window = log_context_items[current_position:window_end]

        print(f"\n--- Processing Window #{windows_processed + 1}")
        print(f"--- Window range: {current_position} to {window_end - 1} (inclusive)")
        print(f"--- Messages in window: {len(current_window)}")
        
        # Convert to format expected by boundary agent
        boundary_messages = []
        for j, entry in enumerate(current_window):
            boundary_messages.append({
                "id": f"msg_{j}",
                "role": entry.get("role", "unknown"),
                "message": entry.get("message", "").strip(),
                "timestamp": entry.get("timestamp")
            })
        
        # 1. Get conversation boundaries for this window
        boundary_input = {
            "messages": boundary_messages,
            "analysis_window_size": len(boundary_messages)
        }
        boundary_result = boundary_agent.action_handler(Message(agent_input=boundary_input)).data or {}
        message_bounds = boundary_result.get("message_bounds", [])
        
        print(f"--- Found {len(message_bounds)} message bounds")
        
        # 2. Find optimal window boundary using your adaptive logic
        optimal_boundary_exclusive = find_optimal_window_boundary(
            message_bounds, len(current_window), THRESHOLD_POSITION
        )

        # 3. Determine which conversations to process in this window
        conv_sel_result = find_conversation_boundaries(message_bounds, optimal_boundary_exclusive)
        conversations_to_process = conv_sel_result["conversations"]
        skipped_messages = conv_sel_result["skipped_messages"]

        # 3.5. Mark filtered messages as processed (messages with should_process: F)
        filtered_message_ids = []
        for msg_bounds in message_bounds:
            if not msg_bounds["bounds"]["should_process"]:
                # Extract the actual log ID from the message
                msg_id = msg_bounds["message_id"]
                # Convert msg_X back to actual log ID
                msg_index = int(msg_id.split('_')[1])
                if msg_index < len(current_window):
                    actual_log_id = current_window[msg_index].get("id")
                    if actual_log_id:
                        filtered_message_ids.append(actual_log_id)
                        print(f"--- Marking filtered message as processed: {msg_id} (log_id: {actual_log_id})")

        if filtered_message_ids:
            processed_log_ids.extend(filtered_message_ids)
            print(f"--- Marked {len(filtered_message_ids)} filtered messages as processed")

        # 3.6. Mark skipped messages as processed (messages skipped due to boundary/overlap filtering)
        skipped_message_ids = []
        for msg_id in skipped_messages:
            # Convert msg_X back to actual log ID
            msg_index = int(msg_id.split('_')[1])
            if msg_index < len(current_window):
                actual_log_id = current_window[msg_index].get("id")
                if actual_log_id:
                    skipped_message_ids.append(actual_log_id)
                    print(f"--- Marking skipped message as processed: {msg_id} (log_id: {actual_log_id})")

        if skipped_message_ids:
            processed_log_ids.extend(skipped_message_ids)
            print(f"--- Marked {len(skipped_message_ids)} skipped messages as processed")

        # 4. Process each conversation in the current window
        if not conversations_to_process:
            # This block would now only be reached if optimal_boundary_exclusive was 0
            print(f"--- No conversations to process in this window, advancing by boundary")
            # Mark all messages in this window as processed since none were selected for processing
            window_message_ids = [entry.get("id") for entry in current_window if entry.get("id")]
            if window_message_ids:
                processed_log_ids.extend(window_message_ids)
                print(f"--- Marked {len(window_message_ids)} window messages as processed (no conversations selected)")
        else:
            for conv_idx, conversation in enumerate(conversations_to_process):
                start_id = conversation["start_id"]
                end_id = conversation["end_id"]
                target_message_id = conversation["target_message_id"]
                start_pos = conversation["start_pos"]
                end_pos = conversation["end_pos"]

                # Extract conversation block and metadata
                conversation_data = extract_conversation_block(conversation, current_window)
                conversation_text = conversation_data["conversation_text"]
                block_ids = conversation_data["block_ids"]
                data_source = conversation_data["data_source"]
                original_message_timestamp_str = conversation_data["original_message_timestamp_str"]

                print(f"\n--- Processing Conversation #{fact_extractor_call_count + 1} (Window #{windows_processed + 1}, Conv {conv_idx + 1})")
                print(f"--- Conversation bounds: {start_id} -> {end_id} (positions {start_pos}-{end_pos})")
                print(f"--- Target message: {target_message_id}")
                print(f"--- Data source: {data_source}")
                print(f"--- Conversation block: \"{conversation_text[:100]}...\"")
            
                # Parse conversation block into atomic sentences
                parse_result = parse_conversation_sentences(conversation_text, parser_agent, original_message_timestamp_str)
                if not parse_result:
                    # No sentences parsed, mark as processed and continue
                    processed_log_ids.extend(block_ids)
                    continue
            
                all_atomic_sentences = parse_result["atomic_sentences"]
                sentence_window_text = parse_result["sentence_window_text"]

                # Handle chunking: if more than 5 sentences, process in chunks
                if len(all_atomic_sentences) > 5:
                    print(f"--- 📦 PROCESSING {len(all_atomic_sentences)} sentences in chunks of 5 or less")
                    sentence_chunks = [all_atomic_sentences[i:i + 5] for i in range(0, len(all_atomic_sentences), 5)]
                    print(f"--- 📦 Created {len(sentence_chunks)} chunks: {[len(chunk) for chunk in sentence_chunks]}")

                    # Process each chunk completely before moving to the next
                    for chunk_idx, sentence_chunk in enumerate(sentence_chunks):
                        print(f"--- 🔄 PROCESSING CHUNK {chunk_idx + 1}/{len(sentence_chunks)} with {len(sentence_chunk)} sentences")

                        # Extract facts from this chunk
                        fact_extractor_call_count += 1
                        fact_result = extract_facts_from_sentences(
                            sentence_chunk,
                            fact_extractor_agent,
                            conversation_text,
                            original_message_timestamp_str,
                            fact_extractor_call_count
                        )

                        original_nodes = fact_result["original_nodes"]
                        original_edges = fact_result["original_edges"]

                        # Add metadata to the extracted facts
                        metadata_result = add_metadata_to_nodes(
                            original_nodes,
                            original_edges,
                            meta_data_agent,
                            conversation_text,
                            original_message_timestamp_str
                        )

                        enriched_metadata = metadata_result["enriched_metadata"]
                        
                        # Merge enriched metadata back into nodes
                        enriched_nodes = []
                        for node in original_nodes:
                            temp_id = node.get("temp_id")
                            if temp_id in enriched_metadata:
                                # Merge enriched fields into node
                                enriched_node = {**node, **enriched_metadata[temp_id]}
                                enriched_nodes.append(enriched_node)
                            else:
                                enriched_nodes.append(node)
                        
                        # Standardize the enriched facts (after metadata has added semantic_label and hash_tags; category comes from fact_extractor)
                        standardization_result = standardize_enriched_nodes(
                            enriched_nodes,
                            original_edges,
                            None,  # standardizer_agent commented out
                            None,  # edge_standardizer_agent commented out
                            orchestrator
                        )
                        
                        standardized_nodes = standardization_result["standardized_nodes"]
                        standardized_edges = standardization_result["standardized_edges"]

                        # Process nodes and prepare edges for this chunk
                        # Note: standardized_nodes already have enriched_metadata merged in, so pass empty dict
                        node_result = process_nodes(
                            standardized_nodes,
                            {},  # Empty - standardized_nodes already have all metadata
                            standardized_edges,
                            conversation_text,
                            sentence_window_text,
                            data_source,
                            original_message_timestamp_str,
                            kg_utils,
                            merge_agent,
                            node_data_merger,
                            block_ids,
                            f"sentence_{chunk_idx}_{conv_idx}"  # Generate unique sentence ID
                        )

                        node_map = node_result["node_map"]
                        edges = node_result["edges"]

                        # Process edges and commit changes for this chunk
                        edge_result = process_edges(
                            edges,
                            node_map,
                            conversation_text,
                            sentence_chunk,  # Use chunk sentences, not all sentences
                            data_source,
                            original_message_timestamp_str,
                            kg_utils,
                            edge_merge_agent,
                            conv_idx,
                            block_ids,
                            f"sentence_{chunk_idx}_{conv_idx}"  # Generate unique sentence ID
                        )

                        # Log detailed summary before commit
                        print(f"\n{'=' * 80}")
                        print(f"📊 CONVERSATION PROCESSING SUMMARY")
                        print(f"{'=' * 80}")
                        print(f"🏷️  NODES CREATED/MERGED: {len(node_map)}")
                        for temp_id, node in node_map.items():
                            print(f"   • {node.label} (ID: {node.id}, Type: {node.node_type})")
                        print(f"🔗 EDGES CREATED/MERGED: {len(edges)}")
                        for edge_idx, edge_data in enumerate(edges):
                            source_temp = edge_data.get('source')
                            target_temp = edge_data.get('target')
                            edge_label = edge_data.get('label')
                            source_node = node_map.get(source_temp)
                            target_node = node_map.get(target_temp)
                            if source_node and target_node:
                                print(f"   • {source_node.label} -> {edge_label} -> {target_node.label}")
                        print(f"{'=' * 80}")

                        # Commit this chunk's changes
                        commit_conversation_changes(
                            kg_utils,
                            len(node_map),
                            len(edges)
                        )

                        print(f"--- ✅ CHUNK {chunk_idx + 1} COMPLETED: {len(node_map)} nodes, {len(edges)} edges")

                    print(f"--- ✅ ALL CHUNKS COMPLETED for conversation {conv_idx + 1}")

                else:
                    # No chunking needed - process all sentences at once
                    print(f"--- 🎯 PROCESSING {len(all_atomic_sentences)} sentences (no chunking needed)")

                    # Extract facts from sentences and enrich with metadata
                    fact_extractor_call_count += 1
                    fact_result = extract_facts_from_sentences(
                        all_atomic_sentences,
                        fact_extractor_agent,
                        conversation_text,
                        original_message_timestamp_str,
                        fact_extractor_call_count
                    )

                    original_nodes = fact_result["original_nodes"]
                    original_edges = fact_result["original_edges"]

                    # Add metadata to the extracted facts
                    metadata_result = add_metadata_to_nodes(
                        original_nodes,
                        original_edges,
                        meta_data_agent,
                        conversation_text,
                        original_message_timestamp_str
                    )

                    enriched_metadata = metadata_result["enriched_metadata"]
                    
                    # Merge enriched metadata back into nodes
                    enriched_nodes = []
                    for node in original_nodes:
                        temp_id = node.get("temp_id")
                        if temp_id in enriched_metadata:
                            # Merge enriched fields into node
                            enriched_node = {**node, **enriched_metadata[temp_id]}
                            enriched_nodes.append(enriched_node)
                        else:
                            enriched_nodes.append(node)
                    
                    # Standardize the enriched facts (after metadata has added semantic_label, category, hash_tags)
                    standardization_result = standardize_enriched_nodes(
                        enriched_nodes,
                        original_edges,
                        None,  # standardizer_agent commented out
                        None,  # edge_standardizer_agent commented out
                        orchestrator
                    )
                    
                    standardized_nodes = standardization_result["standardized_nodes"]
                    standardized_edges = standardization_result["standardized_edges"]

                    # Process nodes and prepare edges
                    # Note: standardized_nodes already have enriched_metadata merged in, so pass empty dict
                    node_result = process_nodes(
                        standardized_nodes,
                        {},  # Empty - standardized_nodes already have all metadata
                        standardized_edges,
                        conversation_text,
                        sentence_window_text,
                        data_source,
                        original_message_timestamp_str,
                        kg_utils,
                        merge_agent,
                        node_data_merger,
                        block_ids,
                        f"sentence_0_{conv_idx}"  # Generate unique sentence ID for non-chunked processing
                    )

                    node_map = node_result["node_map"]
                    edges = node_result["edges"]

                    # Process edges and commit changes (INSIDE the conversation loop)
                    edge_result = process_edges(
                        edges,
                        node_map,
                        conversation_text,
                        all_atomic_sentences,
                        data_source,
                        original_message_timestamp_str,
                        kg_utils,
                        edge_merge_agent,
                        conv_idx,
                        block_ids,
                        f"sentence_0_{conv_idx}"  # Generate unique sentence ID for non-chunked processing
                    )

                    # Log detailed summary before commit
                    print(f"\n{'=' * 80}")
                    print(f"📊 CONVERSATION PROCESSING SUMMARY")
                    print(f"{'=' * 80}")
                    print(f"🏷️  NODES CREATED/MERGED: {len(node_map)}")
                    for temp_id, node in node_map.items():
                        print(f"   • {node.label} (ID: {node.id}, Type: {node.node_type})")
                    print(f"🔗 EDGES CREATED/MERGED: {len(edges)}")
                    for edge_idx, edge_data in enumerate(edges):
                        source_temp = edge_data.get('source')
                        target_temp = edge_data.get('target')
                        edge_label = edge_data.get('label')
                        source_node = node_map.get(source_temp)
                        target_node = node_map.get(target_temp)
                        if source_node and target_node:
                            print(f"   • {source_node.label} -> {edge_label} -> {target_node.label}")
                    print(f"{'=' * 80}")

                    # Commit this conversation's changes (INSIDE the conversation loop)
                    commit_conversation_changes(
                        kg_utils,
                        len(node_map),
                        len(edges)
                    )

                # Mark all messages in this conversation block as processed
                processed_log_ids.extend(block_ids)

        # 5. Advance window position for next iteration
        # Track the actual maximum position processed to avoid gaps
        max_processed_position = 0
        if conversations_to_process:
            # Find the maximum end position actually processed
            for conversation in conversations_to_process:
                end_pos = conversation["end_pos"]
                max_processed_position = max(max_processed_position, end_pos)
            # Advance by max_processed_position + 1 to avoid reprocessing
            advance_by = max_processed_position + 1
        else:
            # No conversations processed, advance by optimal boundary or full window
            advance_by = max(optimal_boundary_exclusive, len(current_window))
            print(f"--- Safety: No conversations processed, advancing by {advance_by}")

        current_position += advance_by
        windows_processed += 1

        print(f"--- Window #{windows_processed} completed, processed up to position {max_processed_position}, advancing to position {current_position}")

        # NEW: Commit processed messages after each window to preserve progress
        if processed_log_ids:
            unique_processed_ids = list(set(processed_log_ids))
            print(f"🔍 Committing {len(unique_processed_ids)} processed messages after window #{windows_processed}")
            mark_logs_as_processed(unique_processed_ids)
            processed_log_ids = []  # Reset for next window
            print(f"✅ Progress saved: {len(unique_processed_ids)} messages marked as processed")

        # If we've processed all messages, break
        if current_position >= len(log_context_items):
            print(f"--- All messages processed, ending pipeline")
            break

    print("\n" + "-" * 40 + " [KG PIPELINE END] " + "-" * 40)
    print(f"🎯 TOTAL FACT EXTRACTOR CALLS: {fact_extractor_call_count}")
    print(f"📊 TOTAL WINDOWS PROCESSED: {windows_processed}")
    
    # Note: Messages are now committed after each window to preserve progress
    # No need for final commit since all messages were already processed
    
    # Debug: Check session state before closing
    print(f"🔍 DEBUG: Before close - Session is active: {kg_utils.session.is_active}")
    print(f"🔍 DEBUG: Before close - Session is dirty: {kg_utils.session.dirty}")
    print(f"🔍 DEBUG: Before close - Session is new: {kg_utils.session.new}")
    
    # Final commit to ensure all changes are persisted
    try:
        kg_utils.session.commit()
        print("🔍 DEBUG: Final commit successful")
    except Exception as e:
        print(f"🔍 DEBUG: Final commit failed: {e}")
        import traceback
        traceback.print_exc()
    
    kg_utils.close()
    orchestrator.close()
    
    # Debug: Check session state after closing
    try:
        print(f"🔍 DEBUG: After close - Session is active: {kg_utils.session.is_active}")
    except:
        print("🔍 DEBUG: Session is fully closed")



def process_unified_log_to_kg(batch_size: int = 100, source_filter: Optional[str] = None, role_filter: Optional[List[str]] = None, kg_utils: Optional[KnowledgeGraphUtils] = None):
    """
    Process unprocessed logs from the unified log database and add them to the knowledge graph.
    
    Args:
        batch_size: Number of logs to process in one batch
        source_filter: Optional source filter (e.g., 'chat', 'slack', 'email')
        role_filter: Optional list of roles to filter by (e.g., ['user', 'assistant'])
        kg_utils: Optional KnowledgeGraphUtils instance
    """
    print(f"\n🚀 Starting unified log processing...")
    print(f"   Batch size: {batch_size}")
    print(f"   Source filter: {source_filter or 'all sources'}")
    print(f"   Role filter: {role_filter or 'all roles'}")
    
    # Get comprehensive database statistics
    session = get_session()
    try:
        print(f"\n{'='*60}")
        print(f"🔍 DATABASE STATE ANALYSIS")
        print(f"{'='*60}")
        
        # Total records in database
        total_records = session.execute(select(func.count(UnifiedLog.id))).scalar()
        print(f"📊 Total records in database: {total_records}")
        
        # Count by processed status
        processed_count = session.execute(select(func.count(UnifiedLog.id)).where(UnifiedLog.processed == True)).scalar()
        unprocessed_count = session.execute(select(func.count(UnifiedLog.id)).where(UnifiedLog.processed == False)).scalar()
        null_processed_count = session.execute(select(func.count(UnifiedLog.id)).where(UnifiedLog.processed.is_(None))).scalar()
        
        print(f"✅ Processed records: {processed_count}")
        print(f"❌ Unprocessed records: {unprocessed_count}")
        print(f"❓ NULL processed records: {null_processed_count}")
        
        # Verify the math
        calculated_total = processed_count + unprocessed_count + null_processed_count
        print(f"🧮 Calculated total: {calculated_total} (should match {total_records})")
        
        # Show sample of processed values
        sample_processed = session.execute(select(UnifiedLog.processed).limit(5)).scalars().all()
        print(f"🔍 Sample processed values: {sample_processed}")
        
        # Apply filters and show filtered counts
        if source_filter or role_filter:
            print(f"\n📋 APPLYING FILTERS:")
            print(f"   Source filter: {source_filter or 'none'}")
            print(f"   Role filter: {role_filter or 'none'}")
            
            filtered_query = select(UnifiedLog)
            if source_filter:
                filtered_query = filtered_query.where(UnifiedLog.source == source_filter)
            if role_filter:
                filtered_query = filtered_query.where(UnifiedLog.role.in_(role_filter))
            
            filtered_total = session.execute(select(func.count()).select_from(filtered_query.subquery())).scalar()
            filtered_unprocessed = session.execute(select(func.count()).select_from(filtered_query.where(UnifiedLog.processed == False).subquery())).scalar()
            
            print(f"📊 Filtered total records: {filtered_total}")
            print(f"📊 Filtered unprocessed records: {filtered_unprocessed}")
        
        print(f"{'='*60}\n")
        
        # Use the filtered unprocessed count for the pipeline
        total_query = select(UnifiedLog).where(UnifiedLog.processed == False)
        if source_filter:
            total_query = total_query.where(UnifiedLog.source == source_filter)
        if role_filter:
            total_query = total_query.where(UnifiedLog.role.in_(role_filter))
        
        total_unprocessed = session.execute(select(func.count()).select_from(total_query.subquery())).scalar()
        print(f"📊 Total unprocessed logs for processing: {total_unprocessed}")
        
    except Exception as e:
        print(f"⚠️  Could not get database statistics: {e}")
        import traceback
        traceback.print_exc()
        total_unprocessed = "unknown"
    finally:
        session.close()
    
    # Note: We rely on processed == False to avoid reprocessing
    # Using timestamp filters can starve old unprocessed rows
    
    # Read unprocessed logs from processed entity log (entity-resolved sentences)
    log_entries = read_unprocessed_logs_from_processed_entity_log(batch_size, source_filter, role_filter)
    
    if not log_entries:
        print("📭 No unprocessed logs found in processed entity log")
        return
    
    print(f"📖 Processing batch of {len(log_entries)} logs")
    if total_unprocessed != "unknown":
        remaining = total_unprocessed - len(log_entries)
        print(f"📊 Remaining logs to process: {remaining}")
    
    # Process the logs using the existing pipeline
    process_text_to_kg(log_entries, kg_utils)
    
    print(f"✅ Unified log processing completed")
    
    # Show final status
    if total_unprocessed != "unknown":
        if remaining > 0:
            print(f"📊 Still have {remaining} logs remaining to process")
        else:
            print(f"🎉 All logs have been processed!")


def process_all_processed_entity_logs_to_kg(batch_size: int = 100, source_filter: Optional[str] = None, role_filter: Optional[List[str]] = None, max_batches: int = 20):
    """
    Process ALL unprocessed logs from the processed_entity_log database in batches, with progress tracking.
    This processes entity-resolved sentences through the knowledge graph pipeline.
    
    Args:
        batch_size: Number of logs to process in one batch
        source_filter: Optional source filter (not used for processed_entity_log)
        role_filter: Optional list of roles to filter by (e.g., ['user', 'assistant'])
        max_batches: Maximum number of batches to process (prevents infinite loops)
    """
    print(f"\n🚀 Starting BATCHED processed entity log processing...")
    print(f"   Batch size: {batch_size}")
    print(f"   Max batches: {max_batches}")
    print(f"   Source filter: {source_filter or 'all sources'} (not used for processed_entity_log)")
    print(f"   Role filter: {role_filter or 'all roles'}")
    print("=" * 80)
    
    # Get comprehensive database statistics
    session = get_session()
    try:
        print(f"\n{'='*60}")
        print(f"🔍 DATABASE STATE ANALYSIS")
        print(f"{'='*60}")
        
        # Total records in database
        total_records = session.execute(select(func.count(ProcessedEntityLog.id))).scalar()
        print(f"📊 Total records in processed_entity_log: {total_records}")
        
        # Count by processed status
        processed_count = session.execute(select(func.count(ProcessedEntityLog.id)).where(ProcessedEntityLog.processed == True)).scalar()
        unprocessed_count = session.execute(select(func.count(ProcessedEntityLog.id)).where(ProcessedEntityLog.processed == False)).scalar()
        
        print(f"✅ Processed records: {processed_count}")
        print(f"⏳ Unprocessed records: {unprocessed_count}")
        
        if unprocessed_count == 0:
            print("🎉 All records are already processed!")
            return
        
        print(f"\n📈 Processing {unprocessed_count} unprocessed records in batches of {batch_size}")
        
    except Exception as e:
        print(f"❌ Error getting database statistics: {e}")
        return
    finally:
        session.close()
    
    # Process in batches
    batch_count = 0
    total_processed = 0
    
    while batch_count < max_batches:
        batch_count += 1
        print(f"\n{'='*60}")
        print(f"🔄 PROCESSING BATCH #{batch_count}")
        print(f"{'='*60}")
        
        # Note: We rely on processed == False to avoid reprocessing
        # Using timestamp filters can starve old unprocessed rows
        
        # Read unprocessed logs for this batch (entity-resolved sentences)
        log_entries = read_unprocessed_logs_from_processed_entity_log(batch_size, source_filter, role_filter)
        
        if not log_entries:
            print("📭 No more unprocessed logs found")
            break
        
        print(f"📖 Processing batch of {len(log_entries)} logs")
        
        try:
            # Process this batch through the knowledge graph pipeline
            process_text_to_kg(log_entries)
            total_processed += len(log_entries)
            print(f"✅ Batch #{batch_count} completed successfully!")
            print(f"📊 Total processed so far: {total_processed}")
            
        except Exception as e:
            print(f"❌ Batch #{batch_count} failed: {e}")
            import traceback
            traceback.print_exc()
            break
    
    print(f"\n{'='*60}")
    print(f"🏁 BATCHED PROCESSING COMPLETED")
    print(f"{'='*60}")
    print(f"📊 Total batches processed: {batch_count}")
    print(f"📊 Total records processed: {total_processed}")
    print(f"✅ Processing completed successfully!")


def process_all_unified_logs_to_kg(batch_size: int = 100, source_filter: Optional[str] = None, role_filter: Optional[List[str]] = None, max_batches: int = 20):
    """
    Process ALL unprocessed logs from the unified log database in batches, with progress tracking.
    Similar to the legacy knowledge_graph_processor but using the modern pipeline.
    
    Args:
        batch_size: Number of logs to process in one batch
        source_filter: Optional source filter (e.g., 'chat', 'slack', 'email')
        role_filter: Optional list of roles to filter by (e.g., ['user', 'assistant'])
        max_batches: Maximum number of batches to process (prevents infinite loops)
    """
    print(f"\n🚀 Starting BATCHED unified log processing...")
    print(f"   Batch size: {batch_size}")
    print(f"   Max batches: {max_batches}")
    print(f"   Source filter: {source_filter or 'all sources'}")
    print(f"   Role filter: {role_filter or 'all roles'}")
    print("=" * 80)
    
    # Get comprehensive database statistics
    session = get_session()
    try:
        print(f"\n{'='*60}")
        print(f"🔍 DATABASE STATE ANALYSIS")
        print(f"{'='*60}")
        
        # Total records in database
        total_records = session.execute(select(func.count(UnifiedLog.id))).scalar()
        print(f"📊 Total records in database: {total_records}")
        
        # Count by processed status
        processed_count = session.execute(select(func.count(UnifiedLog.id)).where(UnifiedLog.processed == True)).scalar()
        unprocessed_count = session.execute(select(func.count(UnifiedLog.id)).where(UnifiedLog.processed == False)).scalar()
        null_processed_count = session.execute(select(func.count(UnifiedLog.id)).where(UnifiedLog.processed.is_(None))).scalar()
        
        print(f"✅ Processed records: {processed_count}")
        print(f"❌ Unprocessed records: {unprocessed_count}")
        print(f"❓ NULL processed records: {null_processed_count}")
        
        # Verify the math
        calculated_total = processed_count + unprocessed_count + null_processed_count
        print(f"🧮 Calculated total: {calculated_total} (should match {total_records})")
        
        # Show sample of processed values
        sample_processed = session.execute(select(UnifiedLog.processed).limit(5)).scalars().all()
        print(f"🔍 Sample processed values: {sample_processed}")
        
        # Apply filters and show filtered counts
        if source_filter or role_filter:
            print(f"\n📋 APPLYING FILTERS:")
            print(f"   Source filter: {source_filter or 'none'}")
            print(f"   Role filter: {role_filter or 'none'}")
            
            filtered_query = select(UnifiedLog)
            if source_filter:
                filtered_query = filtered_query.where(UnifiedLog.source == source_filter)
            if role_filter:
                filtered_query = filtered_query.where(UnifiedLog.role.in_(role_filter))
            
            filtered_total = session.execute(select(func.count()).select_from(filtered_query.subquery())).scalar()
            filtered_unprocessed = session.execute(select(func.count()).select_from(filtered_query.where(UnifiedLog.processed == False).subquery())).scalar()
            
            print(f"📊 Filtered total records: {filtered_total}")
            print(f"📊 Filtered unprocessed records: {filtered_unprocessed}")
        
        print(f"{'='*60}\n")
        
        # Use the filtered unprocessed count for the pipeline
        total_query = select(UnifiedLog).where(UnifiedLog.processed == False)
        if source_filter:
            total_query = total_query.where(UnifiedLog.source == source_filter)
        if role_filter:
            total_query = total_query.where(UnifiedLog.role.in_(role_filter))
        
        total_unprocessed = session.execute(select(func.count()).select_from(total_query.subquery())).scalar()
        print(f"📊 Total unprocessed logs for processing: {total_unprocessed}")
        
    except Exception as e:
        print(f"⚠️  Could not get database statistics: {e}")
        import traceback
        traceback.print_exc()
        total_unprocessed = "unknown"
    finally:
        session.close()
    
    if total_unprocessed == 0:
        print("📭 No unprocessed logs found in database")
        return
    
    # Process in batches
    batches_processed = 0
    total_processed = 0
    
    while batches_processed < max_batches:
        print(f"\n" + "+" * 80)
        print(f"+++ Processing Batch #{batches_processed + 1} (Max: {max_batches})")
        print(f"+++ Total processed so far: {total_processed}")
        if total_unprocessed != "unknown":
            remaining = total_unprocessed - total_processed
            print(f"+++ Remaining logs: {remaining}")
        print("+" * 80)
        
        # Note: We rely on processed == False to avoid reprocessing
        # Using timestamp filters can starve old unprocessed rows
        
        # Read unprocessed logs for this batch (entity-resolved sentences)
        log_entries = read_unprocessed_logs_from_processed_entity_log(batch_size, source_filter, role_filter)
        
        if not log_entries:
            print("📭 No more unprocessed logs found")
            break
        
        print(f"📖 Processing batch of {len(log_entries)} logs")
        
        # Process this batch
        try:
            process_text_to_kg(log_entries)
            total_processed += len(log_entries)
            batches_processed += 1
            print(f"✅ Batch #{batches_processed} completed successfully")
        except Exception as e:
            print(f"❌ Batch #{batches_processed + 1} failed: {e}")
            print("🔄 Stopping batch processing due to error")
            break
    
    print(f"\n" + "=" * 80)
    print(f"🏁 BATCHED PROCESSING COMPLETED")
    print(f"   Batches processed: {batches_processed}")
    print(f"   Total logs processed: {total_processed}")
    if total_unprocessed != "unknown":
        remaining = total_unprocessed - total_processed
        if remaining > 0:
            print(f"   Logs remaining: {remaining}")
        else:
            print(f"   🎉 All logs have been processed!")
    print("=" * 80)


if __name__ == "__main__":
    print("🚀 Starting Knowledge Graph Pipeline in standalone mode...")
    print("=" * 60)
    
    try:
        # Try to import the test setup to initialize the system
        try:
            import app.assistant.tests.test_setup
            print("✅ System initialized successfully")
        except ImportError as e:
            print(f"⚠️  Could not import test setup: {e}")
            print("   This might be okay if running from the main app context")
        
        # Check if we have unprocessed logs to process
        print("\n📖 Checking for unprocessed logs...")

        try:
            print("\n🚀 Processing ALL remaining entity-resolved logs...")

            # Process everything with reasonable batch size from processed_entity_log
            process_all_processed_entity_logs_to_kg(batch_size=200, max_batches=100, role_filter=["user", "assistant"])
            print("✅ All entity-resolved logs processing completed successfully!")
            
        except Exception as e:
            print(f"❌ Full processing failed: {e}")

    except Exception as e:
        print(f"❌ Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🏁 Knowledge Graph Pipeline execution finished")
