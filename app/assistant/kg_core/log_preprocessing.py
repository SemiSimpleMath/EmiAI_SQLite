"""
Log preprocessing utilities for entity resolution

This file contains utilities for preprocessing raw log data
before it enters the main knowledge graph pipeline.

The main function is to read chunks of text from unified_log,
use entity_resolver to get resolved sentences, and save them
as new message types in processed_entity_log.
"""
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.database.db_handler import UnifiedLog
from app.assistant.database.processed_entity_log import ProcessedEntityLog
from app.models.base import get_session

def read_unprocessed_logs_from_processed_entity_log(batch_size: int = 100, source_filter: Optional[str] = None, role_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Read unprocessed logs from the processed_entity_log table.
    
    Args:
        batch_size: Number of logs to fetch
        source_filter: Optional source filter (not used for processed_entity_log)
        role_filter: Optional list of roles to filter by (e.g., ['user', 'assistant'])
    
    Returns:
        List of log entries in the format expected by process_text_to_kg
    """
    session = get_session()
    try:
        query = session.query(ProcessedEntityLog).filter(ProcessedEntityLog.processed == False)
        
        if role_filter:
            query = query.filter(ProcessedEntityLog.role.in_(role_filter))
        
        # Order by timestamp to process oldest first
        query = query.order_by(ProcessedEntityLog.original_message_timestamp.asc()).limit(batch_size)
        
        results = session.execute(query).scalars().all()
        
        log_entries = []
        html_messages_filtered = 0
        html_filtered_ids = []
        
        for log in results:
            # Filter out HTML messages at the source
            if is_html_message(log.resolved_sentence):
                print(f"📖 Filtering out HTML message: \"{log.resolved_sentence[:50]}...\"")
                html_messages_filtered += 1
                html_filtered_ids.append(log.id)
                continue

            entry = {
                "id": log.id,
                "message": log.resolved_sentence,  # Use resolved_sentence instead of message
                "context_window": [],  # Not needed for processed_entity_log
                "source": "processed_entity_log",  # Fixed source
                "timestamp": log.original_message_timestamp,  # Use original_message_timestamp
                "role": log.role,
                "original_message_id": log.original_message_id,  # Keep track of original message
                "original_sentence": log.original_sentence,  # Keep original sentence for reference
                "reasoning": log.reasoning  # Keep reasoning for reference
            }
            log_entries.append(entry)
        
        print(f"📖 Read {len(log_entries)} unprocessed logs from processed_entity_log")
        if html_messages_filtered > 0:
            print(f"🚫 Filtered out {html_messages_filtered} HTML messages at source")
            # Mark HTML-filtered messages as processed to avoid reprocessing them
            for log_id in html_filtered_ids:
                log_obj = session.query(ProcessedEntityLog).filter(ProcessedEntityLog.id == log_id).first()
                if log_obj:
                    log_obj.processed = True
            session.commit()
            print(f"✅ Marked {len(html_filtered_ids)} HTML-filtered messages as processed")
        
        return log_entries
        
    finally:
        session.close()

def mark_processed_entity_logs_as_processed(log_ids: List[str]):
    """Mark processed_entity_log entries as processed"""
    session = get_session()
    try:
        for log_id in log_ids:
            log_obj = session.query(ProcessedEntityLog).filter(ProcessedEntityLog.id == log_id).first()
            if log_obj:
                log_obj.processed = True
        session.commit()
    finally:
        session.close()

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
    if '<ul>' in message or '<li>'  in message:
        return True
    
    # Check for multiple consecutive div tags (search result pattern)
    if message.count('<div') > 2:
        return True
    
    return False


def read_text_chunks_from_unified_log(
    chunk_size: int = 10, 
    overlap_size: int = 3,
    source_filter: Optional[str] = None,
    role_filter: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Read overlapping chunks of text from unified_log to ensure no entity relationships are missed
    
    Args:
        chunk_size: Number of messages per chunk
        overlap_size: Number of messages to overlap between chunks
        source_filter: Filter by source (e.g., 'chat', 'email')
        role_filter: Filter by role (e.g., ['user', 'assistant'])
    
    Returns:
        List of overlapping chunks, each containing message data and combined text
    """
    session = get_session()
    
    try:
        # Build query
        query = session.query(UnifiedLog).filter(UnifiedLog.processed == False)
        
        if source_filter:
            query = query.filter(UnifiedLog.source == source_filter)
        
        if role_filter:
            query = query.filter(UnifiedLog.role.in_(role_filter))
        
        # Order by timestamp
        query = query.order_by(UnifiedLog.timestamp)
        
        # Debug: Check what we're actually querying
        print(f"🔍 Debug: Querying for processed=False")
        print(f"🔍 Debug: Source filter: {source_filter}")
        print(f"🔍 Debug: Role filter: {role_filter}")
        
        # Get all unprocessed messages
        all_messages = query.all()
        
        print(f"🔍 Debug: Found {len(all_messages)} unprocessed messages")
        
        if not all_messages:
            # Let's check what's actually in the database
            total_count = session.query(UnifiedLog).count()
            processed_count = session.query(UnifiedLog).filter(UnifiedLog.processed == True).count()
            unprocessed_count = session.query(UnifiedLog).filter(UnifiedLog.processed == False).count()
            
            print(f"🔍 Debug: Total messages: {total_count}")
            print(f"🔍 Debug: Processed: {processed_count}")
            print(f"🔍 Debug: Unprocessed: {unprocessed_count}")
            
            # Check a few sample records
            sample_records = session.query(UnifiedLog).limit(3).all()
            for i, record in enumerate(sample_records):
                print(f"🔍 Debug: Sample {i+1}: id={record.id}, processed={record.processed}, source={record.source}, role={record.role}")
            
            return []
        
        # Create overlapping chunks
        chunks = []
        start_idx = 0
        
        while start_idx < len(all_messages):
            # Calculate end index for this chunk
            end_idx = min(start_idx + chunk_size, len(all_messages))
            
            # Get messages for this chunk
            chunk_messages = all_messages[start_idx:end_idx]
            
            # Filter out HTML messages before processing
            filtered_messages = []
            html_filtered_count = 0
            
            for msg in chunk_messages:
                if is_html_message(msg.message):
                    print(f"📖 Filtering out HTML message: \"{msg.message[:50]}...\"")
                    html_filtered_count += 1
                    # Mark HTML messages as processed to avoid reprocessing
                    msg.processed = True
                    continue
                filtered_messages.append(msg)
            
            if html_filtered_count > 0:
                print(f"🚫 Filtered out {html_filtered_count} HTML messages from chunk")
                # Commit the HTML-filtered messages as processed
                session.commit()
            
            # Skip this chunk if all messages were filtered out
            if not filtered_messages:
                print(f"⚠️ All messages in chunk were HTML - skipping chunk")
                start_idx = end_idx - overlap_size
                if start_idx <= 0:
                    start_idx = end_idx
                continue
            
            # Use filtered messages for processing
            chunk_messages = filtered_messages
            
            # Combine text from all messages in the chunk
            combined_text = ""
            message_data = []
            
            for msg in chunk_messages:
                message_data.append({
                    'id': msg.id,
                    'timestamp': msg.timestamp,
                    'role': msg.role,
                    'message': msg.message,
                    'source': msg.source
                })
                
                # Add to combined text
                if msg.role:
                    combined_text += f"{msg.role}: {msg.message}\n"
                else:
                    combined_text += f"{msg.message}\n"
            
            chunks.append({
                'messages': message_data,
                'combined_text': combined_text.strip(),
                'chunk_size': len(chunk_messages),
                'start_idx': start_idx,
                'end_idx': end_idx,
                'overlap_with_previous': start_idx > 0,
                'overlap_size': overlap_size if start_idx > 0 else 0
            })
            
            # Move to next chunk with overlap
            if end_idx >= len(all_messages):
                break
                
            # Start next chunk with overlap (unless we're at the end)
            start_idx = end_idx - overlap_size
            
            # Ensure we don't go backwards
            if start_idx <= 0:
                start_idx = end_idx
        
        return chunks
        
    finally:
        session.close()


def process_text_chunk_with_entity_resolver(
    chunk_data: Dict[str, Any],
    agent_version: str = "1.0",
    overlap_context: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Process a text chunk with entity_resolver agent, focusing on non-overlapping content
    
    Args:
        chunk_data: Chunk data from read_text_chunks_from_unified_log
        agent_version: Version of entity_resolver agent
    
    Returns:
        List of resolved sentences with metadata
    """
    # Create entity_resolver agent
    agent = DI.agent_factory.create_agent("knowledge_graph_add::entity_resolver")
    
    # Determine what text to process and what context to provide
    if chunk_data.get('overlap_with_previous', False) and overlap_context:
        # For overlapping chunks, use resolved sentences as context
        overlap_size = chunk_data.get('overlap_size', 0)
        messages = chunk_data['messages']
        
        if overlap_size > 0 and len(messages) > overlap_size:
            # Get new messages to process
            new_messages = messages[overlap_size:]
            
            # Build text from only the new messages
            new_text = ""
            for msg in new_messages:
                if msg['role']:
                    new_text += f"{msg['role']}: {msg['message']}\n"
                else:
                    new_text += f"{msg['message']}\n"
            
            text_to_process = new_text.strip()
            
            # Build previous context from resolved sentences
            previous_context_text = ""
            for resolved_sentence in overlap_context:
                previous_context_text += f"{resolved_sentence['resolved_sentence']}\n"
            previous_context_text = previous_context_text.strip()
            
            print(f"   📝 Processing only new content ({len(new_messages)} messages, skipping {overlap_size} overlapping)")
            print(f"   📚 Providing {len(overlap_context)} resolved sentences as previous context")
        else:
            # Fallback to full text if overlap logic fails
            text_to_process = chunk_data['combined_text']
            previous_context_text = ""
            print(f"   📝 Processing full content (overlap logic fallback)")
    else:
        # For non-overlapping chunks, process everything with no previous context
        text_to_process = chunk_data['combined_text']
        previous_context_text = ""
        print(f"   📝 Processing full content (no overlap)")
    
    # Prepare input with both previous context and new messages
    msg_text = {
        "text": text_to_process,
        "previous_context": previous_context_text,
        "original_message_timestamp": chunk_data['messages'][0]['timestamp'].isoformat()
    }
    
    # Debug: Print what we're sending to the agent
    print(f"🔍 DEBUG: Sending to agent:")
    print(f"  Text to process: {text_to_process[:200]}...")
    print(f"  Previous context: {previous_context_text[:200]}...")
    print(f"  Messages in chunk: {[msg['message'][:50] + '...' for msg in chunk_data['messages']]}")
    
    # Process with agent
    msg = Message(agent_input=msg_text)
    result = agent.action_handler(msg)
    
    # Extract resolved sentences
    resolved_sentences = []
    if result and hasattr(result, 'data') and result.data:
        for sentence_data in result.data.get('resolved_sentences', []):
            resolved_sentences.append({
                'original_sentence': sentence_data.get('original_sentence', ''),
                'resolved_sentence': sentence_data.get('resolved_sentence', ''),
                'reasoning': sentence_data.get('reasoning', ''),
                'agent_version': agent_version
            })
    
    # Debug: Print what the agent returned
    print(f"🔍 DEBUG: Agent returned {len(resolved_sentences)} sentences:")
    for i, sentence in enumerate(resolved_sentences[:3]):  # Show first 3
        print(f"  {i+1}. Original: {sentence['original_sentence'][:500]}...")
        print(f"     Resolved: {sentence['resolved_sentence'][:500]}...")
    
    return resolved_sentences


def save_resolved_sentences_to_processed_entity_log(
    resolved_sentences: List[Dict[str, Any]],
    original_messages: List[Dict[str, Any]],
    session: Session
) -> List[str]:
    """
    Save resolved sentences to processed_entity_log table
    
    Args:
        resolved_sentences: List of resolved sentences from entity_resolver
        original_messages: Original messages from unified_log
        session: Database session
    
    Returns:
        List of created record IDs
    """
    created_ids = []
    
    for sentence_data in resolved_sentences:
        # Strip role prefix from original sentence for matching
        original_sentence = sentence_data['original_sentence']
        if original_sentence.startswith('user: '):
            sentence_to_match = original_sentence[6:]  # Remove 'user: '
        elif original_sentence.startswith('assistant: '):
            sentence_to_match = original_sentence[11:]  # Remove 'assistant: '
        else:
            sentence_to_match = original_sentence
        
        # Find the original message that contains this sentence
        original_message = None
        for msg in original_messages:
            if sentence_to_match in msg['message']:
                original_message = msg
                break
        
        if not original_message:
            print(f"⚠️  Skipping sentence that couldn't be matched: {original_sentence[:100]}...")
            continue
        
        # Create new record
        record_id = str(uuid.uuid4())
        
        processed_entity = ProcessedEntityLog(
            id=record_id,
            original_message_id=original_message['id'],
            original_message_timestamp=original_message['timestamp'],
            role=original_message['role'],  # Save role from original message
            original_sentence=sentence_data['original_sentence'],
            resolved_sentence=sentence_data['resolved_sentence'],
            reasoning=sentence_data['reasoning'],
            agent_version=sentence_data['agent_version'],
            processed=False
        )
        
        session.add(processed_entity)
        created_ids.append(record_id)
    
    return created_ids


def process_unified_log_chunks_with_entity_resolution(
    chunk_size: int = 8,
    overlap_size: int = 3,
    source_filter: Optional[str] = None,
    role_filter: Optional[List[str]] = None,
    agent_version: str = "1.0"
) -> Dict[str, Any]:
    """
    Main function to process unified log chunks with entity resolution using overlapping windows
    
    Args:
        chunk_size: Number of messages per chunk
        overlap_size: Number of messages to overlap between chunks
        source_filter: Filter by source
        role_filter: Filter by role
        agent_version: Version of entity_resolver agent
    
    Returns:
        Processing summary
    """
    session = get_session()
    
    try:
        # Read overlapping chunks
        chunks = read_text_chunks_from_unified_log(chunk_size, overlap_size, source_filter, role_filter)
        
        if not chunks:
            return {
                'chunks_processed': 0,
                'sentences_resolved': 0,
                'records_created': 0,
                'message': 'No unprocessed chunks found'
            }
        
        total_sentences = 0
        total_records = 0
        processed_sentences = set()  # Track processed sentences to avoid duplicates
        overlap_buffer = []  # Keep last k resolved sentences for overlap context
        
        for i, chunk in enumerate(chunks):
            overlap_info = f" (overlap: {chunk['overlap_with_previous']})" if chunk['overlap_with_previous'] else ""
            print(f"🔄 Processing chunk {i+1}/{len(chunks)} with {chunk['chunk_size']} messages{overlap_info}...")
            
            # Process with entity_resolver (will focus on non-overlapping content)
            resolved_sentences = process_text_chunk_with_entity_resolver(chunk, agent_version, overlap_buffer)
            
            if resolved_sentences:
                # Filter out sentences we've already processed (deduplication for overlapping chunks)
                new_sentences = []
                for sentence_data in resolved_sentences:
                    sentence_key = f"{sentence_data['original_sentence']}|{sentence_data['resolved_sentence']}"
                    if sentence_key not in processed_sentences:
                        new_sentences.append(sentence_data)
                        processed_sentences.add(sentence_key)
                
                if new_sentences:
                    # Save to database
                    created_ids = save_resolved_sentences_to_processed_entity_log(
                        new_sentences, 
                        chunk['messages'], 
                        session
                    )
                    
                    # Mark messages as processed if we successfully saved at least some sentences
                    if created_ids:
                        # Some or all sentences were successfully saved
                        for msg in chunk['messages']:
                            msg_obj = session.query(UnifiedLog).filter(UnifiedLog.id == msg['id']).first()
                            if msg_obj:
                                msg_obj.processed = True
                        
                        if len(created_ids) == len(new_sentences):
                            print(f"✅ Resolved {len(new_sentences)} new sentences, created {len(created_ids)} records")
                        else:
                            print(f"⚠️ Resolved {len(new_sentences)} new sentences, created {len(created_ids)} records")
                            print(f"⚠️ Skipped {len(new_sentences) - len(created_ids)} sentences that couldn't be matched to original messages")
                        print(f"📝 Marked {len(chunk['messages'])} messages as processed")
                    else:
                        print(f"⚠️ No sentences could be matched to original messages in this chunk")
                        print(f"⚠️ Skipping this chunk but continuing processing")
                        # Still mark messages as processed to avoid infinite loops
                        for msg in chunk['messages']:
                            msg_obj = session.query(UnifiedLog).filter(UnifiedLog.id == msg['id']).first()
                            if msg_obj:
                                msg_obj.processed = True
                    
                    # Commit after each chunk to see progress
                    session.commit()
                    
                    total_sentences += len(new_sentences)
                    total_records += len(created_ids)
                    if len(resolved_sentences) > len(new_sentences):
                        print(f"   (Filtered out {len(resolved_sentences) - len(new_sentences)} duplicate sentences)")
                    
                    # Update overlap buffer with new resolved sentences
                    overlap_buffer.extend(new_sentences)
                    # Keep only the last k sentences for overlap
                    if len(overlap_buffer) > overlap_size:
                        overlap_buffer = overlap_buffer[-overlap_size:]
                else:
                    print(f"⚠️  All {len(resolved_sentences)} sentences were duplicates from overlap")
            else:
                print("⚠️  No sentences resolved for this chunk")
        
        # Commit all changes
        print(f"💾 Committing {total_records} records to database...")
        session.commit()
        print(f"✅ Successfully committed {total_records} records")
        
        # Verify records were saved
        from app.assistant.database.processed_entity_log import ProcessedEntityLog
        saved_count = session.query(ProcessedEntityLog).count()
        print(f"🔍 Database now contains {saved_count} records")
        
        return {
            'chunks_processed': len(chunks),
            'sentences_resolved': total_sentences,
            'records_created': total_records,
            'message': f'Successfully processed {len(chunks)} chunks'
        }
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error processing chunks: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    # Example usage
    import app.assistant.tests.test_setup # This is just run for the import
    result = process_unified_log_chunks_with_entity_resolution(
        chunk_size=10,
        overlap_size=3,
        source_filter=None,  # Process all sources
        role_filter=['user', 'assistant']
    )
    print(f"Processing result: {result}")