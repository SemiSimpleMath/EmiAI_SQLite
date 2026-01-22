"""
UnifiedItemManager
==================

Business logic for managing UnifiedItems lifecycle.

Core Responsibilities:
1. Ingest events from EventRepository and create UnifiedItems
2. Handle state transitions based on agent decisions
3. Query items for agent triage (NEW/SNOOZED only)
4. Track action progress and completion
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.unified_item_manager.unified_item import UnifiedItem, ItemState
from app.assistant.event_repository.event_repository import EventRepositoryManager
from app.assistant.utils.logging_config import get_logger
from email.utils import parsedate_to_datetime

logger = get_logger(__name__)


class UnifiedItemManager:
    """
    Manages the lifecycle of UnifiedItems from ingestion to completion.
    """
    
    def __init__(self, session_factory=get_session):
        self.session_factory = session_factory
        self.event_repo = EventRepositoryManager(session_factory)
    
    # ========== INGESTION ==========
    
    def ingest_all_sources(self) -> Dict[str, List[UnifiedItem]]:
        """
        Ingest events from all sources and return newly created UnifiedItems.
        
        Returns:
            Dict mapping source_type to list of NEW UnifiedItems
        """
        results = {}
        
        sources = ['email', 'calendar', 'todo_task']  # Scheduler events fire directly, don't need UnifiedItems
        for source in sources:
            try:
                new_items = self.ingest_from_source(source)
                if new_items:
                    results[source] = new_items
                    logger.info(f"Ingested {len(new_items)} new items from {source}")
            except Exception as e:
                logger.error(f"Failed to ingest from {source}: {e}", exc_info=True)
        
        return results
    
    def ingest_from_source(self, source_type: str) -> List[UnifiedItem]:
        """
        Ingest events from a specific source (email, calendar, todo).
        
        Args:
            source_type: 'email', 'calendar', or 'todo_task' (scheduler events fire directly, don't need UnifiedItems)
        
        Returns:
            List of newly created UnifiedItems
        """
        session = self.session_factory()
        try:
            # Get events from EventRepository
            import json
            repo_events_json = self.event_repo.search_events(data_type=source_type)
            repo_events = json.loads(repo_events_json)
            
            logger.info(f"Found {len(repo_events)} events in EventRepository for {source_type}")
            
            new_items = []
            
            for event in repo_events:
                event_data = event.get('data', {})
                
                # Generate unique_id based on source type
                unique_id = self._generate_unique_id(source_type, event_data)
                
                # Check if we already have this item
                existing = session.query(UnifiedItem).filter_by(unique_id=unique_id).first()
                
                if existing:
                    # Update data in case it changed
                    existing.data = event_data
                    existing.updated_at = datetime.now(timezone.utc)
                    continue
                
                # Skip scheduler events - they fire directly, don't need UnifiedItems
                if source_type == 'scheduler':
                    logger.debug(f"Skipping {unique_id} - scheduler events fire directly")
                    continue
                
                # Filter completed todos - only ingest active tasks
                if source_type == 'todo_task':
                    status = event_data.get('status', 'needsAction').lower()
                    if status == 'completed':
                        logger.debug(f"Skipping {unique_id} - task is completed")
                        continue
                
                # Handle recurring calendar events specially
                if source_type == 'calendar':
                    recurring_event_id = event_data.get('recurring_event_id')
                    recurrence_rule = event_data.get('recurrence_rule')
                    
                    # For parent recurring events, use event's own ID as recurring_event_id
                    if not recurring_event_id and recurrence_rule:
                        if isinstance(recurrence_rule, list) and len(recurrence_rule) > 0:
                            recurring_event_id = event_data.get('id')
                        elif recurrence_rule and not isinstance(recurrence_rule, list):
                            recurring_event_id = event_data.get('id')
                    
                    # Normalize to parent ID (remove _R suffix if present)
                    if recurring_event_id:
                        from app.assistant.unified_item_manager.recurring_event_rules import RecurringEventRuleManager
                        recurring_event_id = RecurringEventRuleManager.extract_parent_id(recurring_event_id)
                    
                    if recurring_event_id:
                        # Check if the SERIES is dismissed/snoozed
                        series_id = f"calendar_series:{recurring_event_id}"
                        series_item = session.query(UnifiedItem).filter_by(unique_id=series_id).first()
                        
                        if series_item and series_item.state in [ItemState.DISMISSED, ItemState.SNOOZED]:
                            logger.debug(f"Skipping {unique_id} - series {recurring_event_id} is {series_item.state}")
                            continue
                        
                        # Check recurring event rules BEFORE creating UnifiedItem
                        # Only create UnifiedItems for recurring events that have rules (NORMAL or CUSTOM)
                        # IGNORE rules never create UnifiedItems
                        # No rule = don't create yet (will be handled by process_new_recurring_events)
                        try:
                            from app.assistant.unified_item_manager.recurring_event_rules import (
                                RecurringEventRuleManager, 
                                RecurringEventRuleAction
                            )
                            rule_manager = RecurringEventRuleManager()
                            rule = rule_manager.get_rule(recurring_event_id)
                            
                            if not rule:
                                # No rule exists - skip creating UnifiedItem
                                # Will be handled by process_new_recurring_events which asks user and creates rule
                                logger.debug(f"Skipping {unique_id} - no rule exists yet for recurring event {recurring_event_id}")
                                continue
                            elif rule.action == RecurringEventRuleAction.IGNORE:
                                # IGNORE rule - never create UnifiedItem
                                logger.debug(f"Skipping {unique_id} - recurring event has IGNORE rule for series {recurring_event_id}")
                                continue
                            # If rule is NORMAL or CUSTOM, continue to create UnifiedItem below
                            logger.debug(f"Creating UnifiedItem for recurring event {recurring_event_id} with rule {rule.action}")
                        except Exception as e:
                            # Table might not exist yet - that's okay, skip for now
                            logger.debug(f"Could not check recurring rule (table may not exist yet): {e}, skipping recurring event")
                            continue
                
                # Create NEW UnifiedItem
                unified_item = self._create_unified_item(source_type, event_data, session)
                new_items.append(unified_item)
            
            session.commit()
            logger.info(f"Created {len(new_items)} new UnifiedItems from {source_type}")
            return new_items
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error ingesting from {source_type}: {e}", exc_info=True)
            raise
        finally:
            session.close()
    
    def _generate_unique_id(self, source_type: str, event_data: dict) -> str:
        """Generate a unique ID for tracking this item."""
        if source_type == 'email':
            # Use email message ID or UID
            msg_id = event_data.get('id') or event_data.get('uid')
            return f"email:{msg_id}"
        
        elif source_type == 'calendar':
            # Use Google Calendar event ID
            event_id = event_data.get('id')
            return f"calendar:{event_id}"
        
        elif source_type == 'todo_task':
            # Use Google Tasks ID
            task_id = event_data.get('id')
            return f"todo:{task_id}"
        
        elif source_type == 'scheduler':
            # Use event_id + occurrence timestamp for repeating events
            event_id = event_data.get('event_id')
            occurrence = event_data.get('occurrence', '')
            return f"scheduler:{event_id}:{occurrence}"
        
        else:
            raise ValueError(f"Unknown source_type: {source_type}")
    
    def _create_unified_item(self, source_type: str, event_data: dict, session: Session) -> UnifiedItem:
        """Create a new UnifiedItem from event data."""
        # Extract common fields based on source type
        title, content, source_timestamp, importance = self._extract_fields(source_type, event_data)
        
        # Generate unique_id
        unique_id = self._generate_unique_id(source_type, event_data)
        
        # Build metadata
        item_metadata = {}
        if source_type == 'calendar':
            # Normalize recurring_event_id to parent ID (remove _R suffix if present)
            raw_recurring_id = event_data.get('recurring_event_id')
            if raw_recurring_id:
                from app.assistant.unified_item_manager.recurring_event_rules import RecurringEventRuleManager
                item_metadata['recurring_event_id'] = RecurringEventRuleManager.extract_parent_id(raw_recurring_id)
            else:
                item_metadata['recurring_event_id'] = None
            item_metadata['is_recurring'] = bool(item_metadata.get('recurring_event_id'))
        
        # Create UnifiedItem
        unified_item = UnifiedItem(
            unique_id=unique_id,
            source_type=source_type,
            state=ItemState.NEW,
            title=title,
            content=content,
            data=event_data,
            item_metadata=item_metadata,
            source_timestamp=source_timestamp,
            importance=importance,
            state_history=[{
                "state": ItemState.NEW,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "ingested from EventRepository"
            }]
        )
        
        session.add(unified_item)
        logger.debug(f"Created UnifiedItem: {unique_id}")
        return unified_item
    
    def _extract_fields(self, source_type: str, event_data: dict) -> tuple:
        """
        Extract title, content, timestamp, and importance from event data.
        
        Returns:
            (title, content, source_timestamp, importance)
        """
        if source_type == 'email':
            title = event_data.get('subject', 'No Subject')
            content = event_data.get('summary', '')
            date_str = event_data.get('date_received', '')
            try:
                source_timestamp = parsedate_to_datetime(date_str) if date_str else None
            except (ValueError, TypeError):
                source_timestamp = None
            importance = event_data.get('importance', 5)
        
        elif source_type == 'calendar':
            title = event_data.get('summary', 'No Title')
            content = event_data.get('description', '')
            start_str = event_data.get('start', '')
            try:
                source_timestamp = datetime.fromisoformat(start_str.replace('Z', '+00:00')) if start_str else None
            except (ValueError, TypeError):
                source_timestamp = None
            importance = 6  # Calendar events slightly higher priority by default
        
        elif source_type == 'todo_task':
            title = event_data.get('title', 'Untitled Task')
            content = event_data.get('notes', '')
            due_str = event_data.get('due', '')
            try:
                source_timestamp = datetime.fromisoformat(due_str.replace('Z', '+00:00')) if due_str else None
            except (ValueError, TypeError):
                source_timestamp = None
            importance = 7  # Todos are higher priority
        
        elif source_type == 'scheduler':
            title = event_data.get('event_payload', {}).get('title', 'Scheduler Event')
            content = event_data.get('event_payload', {}).get('message', '')
            occurrence_str = event_data.get('occurrence', '')
            try:
                source_timestamp = datetime.fromisoformat(occurrence_str.replace('Z', '+00:00')) if occurrence_str else None
            except (ValueError, TypeError):
                source_timestamp = None
            importance = event_data.get('event_payload', {}).get('importance', 5)
        
        else:
            title = 'Unknown'
            content = ''
            source_timestamp = None
            importance = 5
        
        return title, content, source_timestamp, importance
    
    # ========== QUERYING ==========
    
    def get_items_for_triage(self, limit: int = 50) -> List[UnifiedItem]:
        """
        Get items that need agent attention (NEW or expired SNOOZED items).
        
        Returns:
            List of UnifiedItems ordered by importance (desc) then created_at (asc)
        """
        session = self.session_factory()
        try:
            now = datetime.now(timezone.utc)
            
            items = session.query(UnifiedItem).filter(
                (UnifiedItem.state == ItemState.NEW) |
                ((UnifiedItem.state == ItemState.SNOOZED) & (UnifiedItem.snooze_until <= now))
            ).order_by(
                UnifiedItem.importance.desc(),
                UnifiedItem.created_at.asc()
            ).limit(limit).all()
            
            logger.info(f"Retrieved {len(items)} items for triage")
            return items
            
        finally:
            session.close()
    
    def get_items_in_progress(self) -> List[UnifiedItem]:
        """
        Get items with ACTION_PENDING state.
        
        Returns:
            List of UnifiedItems with pending actions
        """
        session = self.session_factory()
        try:
            items = session.query(UnifiedItem).filter_by(
                state=ItemState.ACTION_PENDING
            ).order_by(UnifiedItem.updated_at.desc()).all()
            
            logger.info(f"Retrieved {len(items)} items in progress")
            return items
            
        finally:
            session.close()
    
    def get_recent_actions(self, hours: int = 24) -> List[UnifiedItem]:
        """
        Get items with ACTION_TAKEN state from the last N hours.
        
        Returns:
            List of recently completed UnifiedItems
        """
        session = self.session_factory()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            items = session.query(UnifiedItem).filter(
                UnifiedItem.state == ItemState.ACTION_TAKEN,
                UnifiedItem.updated_at >= cutoff
            ).order_by(UnifiedItem.updated_at.desc()).all()
            
            logger.info(f"Retrieved {len(items)} recent actions from last {hours} hours")
            return items
            
        finally:
            session.close()
    
    # ========== STATE TRANSITIONS ==========
    
    def transition_state(
        self,
        item_id: int,
        new_state: ItemState,
        agent_decision: Optional[str] = None,
        agent_notes: Optional[str] = None,
        related_action_id: Optional[str] = None,
        snooze_until: Optional[datetime] = None
    ) -> UnifiedItem:
        """
        Transition an item to a new state (called after agent decision).
        
        Args:
            item_id: UnifiedItem ID
            new_state: Target state
            agent_decision: What the agent decided to do
            agent_notes: Agent's reasoning
            related_action_id: Link to AgentActivityLog
            snooze_until: When to wake up (for SNOOZED state)
        
        Returns:
            Updated UnifiedItem
        """
        session = self.session_factory()
        try:
            item = session.query(UnifiedItem).get(item_id)
            if not item:
                raise ValueError(f"UnifiedItem {item_id} not found")
            
            old_state = item.state
            
            # Record state transition
            transition_record = {
                "from_state": old_state,
                "to_state": new_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent_decision": agent_decision,
                "notes": agent_notes
            }
            
            if item.state_history is None:
                item.state_history = []
            item.state_history.append(transition_record)
            
            # Update state
            item.state = new_state
            item.updated_at = datetime.now(timezone.utc)
            
            if agent_decision:
                item.agent_decision = agent_decision
            if agent_notes:
                item.agent_notes = agent_notes
            if related_action_id:
                item.related_action_id = related_action_id
            
            # Handle snoozing
            if new_state == ItemState.SNOOZED:
                if not snooze_until:
                    # Default: snooze for 24 hours
                    snooze_until = datetime.now(timezone.utc) + timedelta(hours=24)
                item.snooze_until = snooze_until
                item.snooze_count += 1
                logger.info(f"Snoozed item {item_id} until {snooze_until}")
            
            session.commit()
            logger.info(f"Transitioned item {item_id}: {old_state} -> {new_state}")
            return item
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error transitioning item {item_id}: {e}", exc_info=True)
            raise
        finally:
            session.close()
    
    def dismiss_item(self, item_id: int, reason: str = None) -> UnifiedItem:
        """Convenience method to dismiss an item."""
        return self.transition_state(
            item_id=item_id,
            new_state=ItemState.DISMISSED,
            agent_notes=reason
        )
    
    def dismiss_entire_series(self, recurring_event_id: str, reason: str = None) -> UnifiedItem:
        """
        Create or update a DISMISSED UnifiedItem for a calendar series.
        This blocks all future instances of this recurring event.
        
        Args:
            recurring_event_id: The Google Calendar recurring event ID
            reason: Why this series is being dismissed
        
        Returns:
            The series UnifiedItem
        """
        session = self.session_factory()
        try:
            series_id = f"calendar_series:{recurring_event_id}"
            
            # Check if series item already exists
            series_item = session.query(UnifiedItem).filter_by(unique_id=series_id).first()
            
            if not series_item:
                # Create it as DISMISSED
                series_item = UnifiedItem(
                    unique_id=series_id,
                    source_type='calendar_series',
                    state=ItemState.DISMISSED,
                    title=f"Series: {recurring_event_id}",
                    content=reason or "Entire series dismissed",
                    agent_notes=reason,
                    importance=0,  # Low importance since it's just a blocker
                    state_history=[{
                        "state": ItemState.DISMISSED,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "reason": "series permanently dismissed"
                    }]
                )
                session.add(series_item)
            else:
                # Update existing
                series_item.state = ItemState.DISMISSED
                series_item.agent_notes = reason
                series_item.updated_at = datetime.now(timezone.utc)
            
            session.commit()
            logger.info(f"Series {recurring_event_id} dismissed - future instances will be auto-skipped")
            return series_item
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error dismissing series {recurring_event_id}: {e}", exc_info=True)
            raise
        finally:
            session.close()
    
    # ========== UTILITY ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about UnifiedItems."""
        session = self.session_factory()
        try:
            from sqlalchemy import func
            
            total = session.query(func.count(UnifiedItem.id)).scalar()
            
            state_counts = {}
            for state in ItemState:
                count = session.query(func.count(UnifiedItem.id)).filter_by(state=state).scalar()
                state_counts[state.value] = count
            
            source_counts = {}
            for source in ['email', 'calendar', 'todo_task', 'calendar_series']:  # Scheduler events fire directly
                count = session.query(func.count(UnifiedItem.id)).filter_by(source_type=source).scalar()
                source_counts[source] = count
            
            return {
                'total': total,
                'by_state': state_counts,
                'by_source': source_counts
            }
            
        finally:
            session.close()


# ========== EXPORT ==========
__all__ = ['UnifiedItemManager', 'ItemState']

