"""
SwitchboardRunner: Processes overlapping message windows to extract user preferences and feedback.

Design:
- Overlapping sliding windows to catch preferences that span multiple messages
- TIME-BASED SPLITTING: If gap > 2 hours between messages, starts fresh (no overlap)
- Tracks last_processed_message_id to resume from where we left off
- Uses window_end_id in extracted_facts to prevent duplicate window processing
- Deduplicates facts by checking if same message IDs already extracted
"""

import uuid
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func

from app.models.base import get_session
from app.assistant.database.db_handler import UnifiedLog, ExtractedFact, SwitchboardState
from app.assistant.utils.logging_config import get_logger
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message

logger = get_logger(__name__)


class SwitchboardRunner:
    """
    Processes overlapping sliding windows of messages to extract user preferences and feedback.
    
    Strategy:
    1. Get last processed message ID from SwitchboardState
    2. Check time gap - if > TIME_GAP_THRESHOLD, start fresh (no overlap)
    3. Fetch next window_size messages after that point (with overlap if same conversation)
    4. Check if this window has already been processed (via window_end_id)
    5. If not, run switchboard agent on the window
    6. Filter out facts that reference message IDs we've already extracted
    7. Save new extracted facts to extracted_facts table
    8. Update last_processed_message_id (advance by window_size - overlap_size)
    """
    
    # If gap between messages > this threshold, treat as separate conversations (no overlap)
    TIME_GAP_THRESHOLD = timedelta(hours=2)
    
    def __init__(self, window_size: int = 10, overlap_size: int = 3):
        """
        Args:
            window_size: Number of messages per window (default 10)
            overlap_size: Number of messages to overlap between windows (default 3)
        """
        self.window_size = window_size
        self.overlap_size = overlap_size
    
    def _get_last_processed_message_id(self) -> Optional[str]:
        """Get the last processed message ID from SwitchboardState."""
        session = get_session()
        try:
            state = session.query(SwitchboardState).filter(SwitchboardState.id == 1).first()
            if state and state.last_processed_message_id:
                return state.last_processed_message_id
            return None
        finally:
            session.close()
    
    def _update_last_processed_message_id(self, message_id: str):
        """Update the last processed message ID in SwitchboardState."""
        session = get_session()
        try:
            state = session.query(SwitchboardState).filter(SwitchboardState.id == 1).first()
            if not state:
                state = SwitchboardState(id=1, last_processed_message_id=message_id)
                session.add(state)
            else:
                state.last_processed_message_id = message_id
                state.last_run_at = datetime.now(timezone.utc)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating last processed message ID: {e}")
        finally:
            session.close()
    
    def _get_messages_for_window(self, start_after_message_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Get window_size messages from unified_log, with overlap if resuming.
        
        Strategy:
        - If start_after_message_id is None: Get first window_size messages
        - If start_after_message_id is set:
          - Check time gap to next message
          - If gap > TIME_GAP_THRESHOLD: Start fresh (no overlap) - different conversation
          - Otherwise: Get overlap_size messages before it + window_size new messages after it
        
        Args:
            start_after_message_id: Message ID to start after (for overlap, we go back overlap_size before this)
        
        Returns:
            Tuple of (messages list, is_new_conversation bool)
            - messages: List of message dicts with id, timestamp, role, message, source
            - is_new_conversation: True if time gap detected (no overlap used)
        """
        session = get_session()
        try:
            # Only select the columns we need (avoids deprecated 'category' column)
            columns = [UnifiedLog.id, UnifiedLog.timestamp, UnifiedLog.role, UnifiedLog.message, UnifiedLog.source]
            
            if start_after_message_id is None:
                # First window: just get window_size messages
                query = session.query(*columns).filter(
                    UnifiedLog.role.in_(['user', 'assistant'])
                ).order_by(UnifiedLog.timestamp.asc()).limit(self.window_size)
                
                messages = query.all()
                return [
                    {
                        'id': msg.id,
                        'timestamp': msg.timestamp,
                        'role': msg.role,
                        'message': msg.message,
                        'source': msg.source
                    }
                    for msg in messages
                ], False  # Not a new conversation (first run)
            
            # Resuming: check time gap first
            last_msg_timestamp = session.query(UnifiedLog.timestamp).filter(
                UnifiedLog.id == start_after_message_id
            ).scalar()
            if not last_msg_timestamp:
                return [], False
            
            # Get the FIRST message after last_processed to check time gap
            next_msg = session.query(UnifiedLog.timestamp).filter(
                UnifiedLog.role.in_(['user', 'assistant']),
                UnifiedLog.timestamp > last_msg_timestamp
            ).order_by(UnifiedLog.timestamp.asc()).first()
            
            if not next_msg:
                return [], False  # No new messages
            
            # Check time gap
            time_gap = next_msg.timestamp - last_msg_timestamp
            is_new_conversation = time_gap > self.TIME_GAP_THRESHOLD
            
            if is_new_conversation:
                # Large time gap - start fresh, no overlap
                logger.info(f"🔀 SWITCHBOARD:   ⏰ Time gap of {time_gap} detected (>{self.TIME_GAP_THRESHOLD}) - starting new conversation window")
                overlap_msgs = []
            else:
                # Same conversation - get overlap messages
                overlap_query = session.query(*columns).filter(
                    UnifiedLog.role.in_(['user', 'assistant']),
                    UnifiedLog.timestamp <= last_msg_timestamp
                ).order_by(UnifiedLog.timestamp.desc()).limit(self.overlap_size)
                
                overlap_msgs = list(reversed(overlap_query.all()))  # Reverse to chronological
            
            # Get window_size new messages after last_msg
            new_query = session.query(*columns).filter(
                UnifiedLog.role.in_(['user', 'assistant']),
                UnifiedLog.timestamp > last_msg_timestamp
            ).order_by(UnifiedLog.timestamp.asc()).limit(self.window_size)
            
            new_msgs = new_query.all()
            
            # Combine overlap + new
            all_messages = list(overlap_msgs) + list(new_msgs)
            
            return [
                {
                    'id': msg.id,
                    'timestamp': msg.timestamp,
                    'role': msg.role,
                    'message': msg.message,
                    'source': msg.source
                }
                for msg in all_messages
            ], is_new_conversation
        finally:
            session.close()
    
    def _check_window_already_processed(self, window_end_id: str) -> bool:
        """
        Check if a window ending at window_end_id has already been processed.
        
        Args:
            window_end_id: The ID of the last message in the window
        
        Returns:
            True if this window has already been processed
        """
        session = get_session()
        try:
            # Check if any extracted_fact has this window_end_id
            existing = session.query(ExtractedFact).filter(
                ExtractedFact.window_end_id == window_end_id
            ).first()
            return existing is not None
        finally:
            session.close()
    
    def _get_already_extracted_message_ids(self) -> Set[str]:
        """
        Get set of all message IDs that have already been extracted.
        Used to filter out facts that reference messages we've already processed.
        
        Returns:
            Set of message IDs that appear in source_message_ids of existing facts
        """
        session = get_session()
        try:
            facts = session.query(ExtractedFact).all()
            extracted_ids = set()
            for fact in facts:
                if fact.source_message_ids:
                    extracted_ids.update(fact.source_message_ids)
            return extracted_ids
        finally:
            session.close()
    
    def _classify_messages_in_window(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run switchboard agent on a window of messages.
        
        Args:
            messages: List of message dicts
        
        Returns:
            List of tagged chunks from switchboard agent
        """
        try:
            switchboard = DI.agent_factory.create_agent('switchboard')
            if not switchboard:
                logger.error("🔀 SWITCHBOARD: ❌ Switchboard agent not found")
                return []
            
            # Format messages for switchboard agent
            agent_input = {
                "messages": messages
            }
            
            logger.debug(f"🔀 SWITCHBOARD:   Calling switchboard agent with {len(messages)} messages")
            response = switchboard.action_handler(Message(agent_input=agent_input))
            result = response.data or {}
            
            tagged_chunks = result.get('tagged_chunks', [])
            logger.debug(f"🔀 SWITCHBOARD:   Agent returned {len(tagged_chunks)} tagged chunks")
            
            # Log reasoning if provided
            reasoning = result.get('reasoning')
            if reasoning:
                logger.info(f"🔀 SWITCHBOARD:   💭 Reasoning: {reasoning}")
            
            return tagged_chunks
            
        except Exception as e:
            logger.error(f"🔀 SWITCHBOARD: ❌ Error running switchboard agent: {e}", exc_info=True)
            return []
    
    def _save_extracted_facts(self, tagged_chunks: List[Dict[str, Any]], window_end_id: str, 
                              source_message_ids: List[str], already_extracted_ids: Set[str]):
        """
        Save extracted facts to extracted_facts table, filtering out duplicates.
        
        Args:
            tagged_chunks: List of tagged chunks from switchboard
            window_end_id: ID of last message in the window (high water mark)
            source_message_ids: List of message IDs in this window
            already_extracted_ids: Set of message IDs already extracted (for deduplication)
        """
        if not tagged_chunks:
            logger.info(f"🔀 SWITCHBOARD:   No chunks to save")
            return
        
        session = get_session()
        try:
            facts_to_save = []
            skipped_no_category = 0
            skipped_duplicate = 0
            
            for chunk in tagged_chunks:
                category = chunk.get('category')
                if not category:  # Skip chunks with no category
                    skipped_no_category += 1
                    continue
                
                # Get message IDs referenced by this chunk (if switchboard provides them)
                # Otherwise fall back to all window message IDs
                chunk_message_ids = chunk.get('source_message_ids', source_message_ids)
                
                # Check if this fact references only already-extracted messages
                # If so, skip it (it's a duplicate from overlap)
                chunk_ids_set = set(chunk_message_ids)
                if chunk_ids_set.issubset(already_extracted_ids):
                    skipped_duplicate += 1
                    summary = chunk.get('extracted_summary', '')[:50]
                    logger.info(f"🔀 SWITCHBOARD:   ⏭️  Skipping duplicate fact: '{summary}...' (all {len(chunk_ids_set)} message IDs already extracted)")
                    continue
                
                fact_id = str(uuid.uuid4())
                facts_to_save.append({
                    'id': fact_id,
                    'category': category,
                    'summary': chunk.get('extracted_summary', ''),
                    'confidence': chunk.get('confidence', 0.0),
                    'tags': chunk.get('tags', []),  # Added: Tags for routing
                    'source_message_ids': chunk_message_ids,  # Messages referenced by this chunk
                    'window_end_id': window_end_id,  # High water mark
                    'processed': False,  # Not yet processed by Memory Manager
                    'created_at': datetime.now(timezone.utc)
                })
            
            if facts_to_save:
                session.bulk_insert_mappings(ExtractedFact, facts_to_save)
                session.commit()
                logger.info(f"🔀 SWITCHBOARD:   💾 Saved {len(facts_to_save)} facts to extracted_facts table")
                for i, fact in enumerate(facts_to_save):
                    logger.info(f"🔀 SWITCHBOARD:     Fact {i+1}: category={fact['category']}, confidence={fact['confidence']:.2f}, summary='{fact['summary'][:60]}...'")
                
                if skipped_duplicate > 0 or skipped_no_category > 0:
                    logger.info(f"🔀 SWITCHBOARD:   Filtered: {skipped_duplicate} duplicates, {skipped_no_category} no-category")
            else:
                logger.info(f"🔀 SWITCHBOARD:   ⚠️  No new facts to save ({skipped_duplicate} duplicates, {skipped_no_category} no-category)")
            
        except Exception as e:
            session.rollback()
            logger.error(f"🔀 SWITCHBOARD: ❌ Error saving extracted facts: {e}", exc_info=True)
        finally:
            session.close()
    
    def run(self) -> Dict[str, Any]:
        """
        Main entry point: Process one window of messages with overlap.
        
        Returns:
            Dict with stats about processing
        """
        logger.info("🔀 SWITCHBOARD: Starting window processing...")
        
        # Get last processed message ID
        last_processed_id = self._get_last_processed_message_id()
        logger.info(f"🔀 SWITCHBOARD: Last processed message ID: {last_processed_id or 'None (starting fresh)'}")
        
        # Get next window of messages (with overlap if resuming, unless time gap detected)
        messages, is_new_conversation = self._get_messages_for_window(start_after_message_id=last_processed_id)
        
        if not messages:
            logger.info("🔀 SWITCHBOARD: No new messages to process")
            return {
                'processed': 0,
                'facts_extracted': 0,
                'message': 'No new messages'
            }
        
        # Identify new messages (not in overlap)
        # If is_new_conversation, there's no overlap - all messages are "new"
        if is_new_conversation:
            overlap_messages = []
            new_messages = messages
        elif last_processed_id and len(messages) > self.overlap_size:
            overlap_messages = messages[:self.overlap_size]
            new_messages = messages[self.overlap_size:]
        else:
            overlap_messages = []
            new_messages = messages
        
        window_end_id = messages[-1]['id']
        window_start_id = messages[0]['id']
        
        logger.info(f"🔀 SWITCHBOARD: Window [{window_start_id}..{window_end_id}]")
        if is_new_conversation:
            logger.info(f"🔀 SWITCHBOARD:   🆕 NEW CONVERSATION (time gap > {self.TIME_GAP_THRESHOLD})")
        logger.info(f"🔀 SWITCHBOARD:   Total messages: {len(messages)} ({len(overlap_messages)} overlap, {len(new_messages)} new)")
        if overlap_messages:
            logger.info(f"🔀 SWITCHBOARD:   Overlap range: [{overlap_messages[0]['id']}..{overlap_messages[-1]['id']}]")
        if new_messages:
            logger.info(f"🔀 SWITCHBOARD:   New range: [{new_messages[0]['id']}..{new_messages[-1]['id']}]")
        
        # Check if this window has already been processed
        if self._check_window_already_processed(window_end_id):
            logger.info(f"🔀 SWITCHBOARD: ⏭️  Window ending at {window_end_id} already processed, skipping")
            # Advance by window_size - overlap_size to get next window
            if new_messages:
                advance_to_id = new_messages[-1]['id']
                self._update_last_processed_message_id(advance_to_id)
                logger.info(f"🔀 SWITCHBOARD:   Advanced to {advance_to_id} for next window")
            else:
                self._update_last_processed_message_id(window_end_id)
            return {
                'processed': 0,
                'facts_extracted': 0,
                'message': 'Window already processed'
            }
        
        # Get already-extracted message IDs for deduplication
        already_extracted_ids = self._get_already_extracted_message_ids()
        logger.info(f"🔀 SWITCHBOARD:   Already extracted {len(already_extracted_ids)} message IDs (for deduplication)")
        
        # Run switchboard agent on the full window (including overlap for context)
        logger.info(f"🔀 SWITCHBOARD:   Running switchboard agent on {len(messages)} messages...")
        tagged_chunks = self._classify_messages_in_window(messages)
        
        logger.info(f"🔀 SWITCHBOARD:   Agent returned {len(tagged_chunks)} tagged chunks")
        for i, chunk in enumerate(tagged_chunks):
            category = chunk.get('category', 'none')
            summary = chunk.get('extracted_summary', '')[:60]
            confidence = chunk.get('confidence', 0.0)
            logger.info(f"🔀 SWITCHBOARD:     Chunk {i+1}: category={category}, confidence={confidence:.2f}, summary='{summary}...'")
        
        # Save extracted facts (will filter duplicates)
        source_message_ids = [msg['id'] for msg in messages]
        self._save_extracted_facts(tagged_chunks, window_end_id, source_message_ids, already_extracted_ids)
        
        # Update last processed message ID: advance by (window_size - overlap_size) to get next window
        # This ensures we have overlap_size overlap in the next window
        if new_messages:
            # Advance to the last new message (not including overlap)
            advance_to_id = new_messages[-1]['id']
            self._update_last_processed_message_id(advance_to_id)
            logger.info(f"🔀 SWITCHBOARD:   Advanced last_processed_message_id to {advance_to_id} (next window will start with overlap)")
        else:
            # If no new messages (edge case), just advance to end
            self._update_last_processed_message_id(window_end_id)
        
        facts_count = len([c for c in tagged_chunks if c.get('category')])
        
        logger.info(f"🔀 SWITCHBOARD: ✅ Completed: {len(new_messages)} new messages processed, {facts_count} facts extracted")
        
        return {
            'processed': len(new_messages) if new_messages else len(messages),
            'facts_extracted': facts_count,
            'window_end_id': window_end_id
        }
    
    def get_unprocessed_facts(self, category: Optional[str] = None) -> List[ExtractedFact]:
        """
        Get unprocessed facts from extracted_facts table (for Memory Manager).
        
        Args:
            category: Optional filter by category ('preference', 'feedback')
        
        Returns:
            List of ExtractedFact objects
        """
        session = get_session()
        try:
            query = session.query(ExtractedFact).filter(ExtractedFact.processed == False)
            
            if category:
                query = query.filter(ExtractedFact.category == category)
            
            query = query.order_by(ExtractedFact.created_at.asc())
            
            return query.all()
        finally:
            session.close()
    
    def mark_fact_processed(self, fact_id: str):
        """Mark an extracted fact as processed by Memory Manager."""
        session = get_session()
        try:
            fact = session.query(ExtractedFact).filter(ExtractedFact.id == fact_id).first()
            if fact:
                fact.processed = True
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error marking fact as processed: {e}")
        finally:
            session.close()

