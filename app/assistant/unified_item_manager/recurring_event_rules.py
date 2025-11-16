"""
Recurring Event Rules: Store and apply user preferences for recurring calendar events.

When a user decides how to handle a recurring event (e.g., "always ignore daily standup"),
we store that rule and automatically apply it to future instances.
"""

from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Index, func, JSON
from app.models.base import Base, get_session

import logging
logger = logging.getLogger(__name__)


class RecurringEventRuleAction(str, Enum):
    """Actions to automatically apply to recurring events"""
    IGNORE = "ignore"      # Mark as DISMISSED immediately
    NORMAL = "normal"      # Treat like any other event (no special handling)
    CUSTOM = "custom"      # Custom rule with agent_instructions


class RecurringEventRule(Base):
    """
    Stores user preferences for how to handle recurring calendar events.
    
    Example: "Always dismiss 'Daily Standup' recurring events"
    """
    __tablename__ = 'recurring_event_rules'
    
    # Identification
    id = Column(String(512), primary_key=True)  # Same as recurring_event_id from Google Calendar
    event_title = Column(String(500))  # Human-readable title for display
    
    # Rule definition
    action = Column(String(50), nullable=False, index=True)  # RecurringEventRuleAction
    reason = Column(Text)  # Why the user chose this rule (e.g., "This is a routine meeting I never need reminders for")
    agent_instructions = Column(Text)  # For CUSTOM rules: specific instructions from user
    
    # Metadata
    rule_config = Column(JSON)  # Additional config (e.g., {"notify_on_day": "friday"}) - SQLite compatible
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_applied = Column(DateTime(timezone=True))  # Last time this rule was applied
    application_count = Column(JSON, default=dict)  # Track how many times rule was applied - SQLite compatible
    
    # Indexes
    __table_args__ = (
        Index('idx_recurring_rules_action', 'action'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'event_title': self.event_title,
            'action': self.action,
            'reason': self.reason,
            'agent_instructions': self.agent_instructions,
            'rule_config': self.rule_config,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_applied': self.last_applied.isoformat() if self.last_applied else None,
            'application_count': self.application_count,
        }
    
    def __repr__(self):
        return f"<RecurringEventRule(id={self.id}, title='{self.event_title}', action={self.action})>"


class RecurringEventRuleManager:
    """Manages creation, retrieval, and application of recurring event rules"""
    
    def __init__(self, session_factory=get_session):
        self.session_factory = session_factory
    
    @staticmethod
    def extract_parent_id(recurring_event_id: str) -> str:
        """
        Extract the parent recurring event ID from a child event ID.
        
        Child events have format: {parent_id}_R{timestamp}
        Parent events have format: {parent_id}
        
        Args:
            recurring_event_id: Either parent or child event ID
            
        Returns:
            The parent ID (normalized)
        """
        if not recurring_event_id:
            return recurring_event_id
        
        # If it contains _R, it's a child event - extract parent ID
        if '_R' in recurring_event_id:
            parent_id = recurring_event_id.split('_R')[0]
            return parent_id
        
        # Otherwise it's already a parent ID
        return recurring_event_id
    
    def create_rule(self, recurring_event_id: str, event_title: str, 
                   action: RecurringEventRuleAction, reason: str = None,
                   agent_instructions: str = None, rule_config: dict = None) -> RecurringEventRule:
        """
        Create a new rule for a recurring event.
        
        Always uses the parent ID (normalizes child IDs by removing _R suffix).
        
        Args:
            recurring_event_id: The Google Calendar recurring_event_id (parent or child)
            event_title: Human-readable event title
            action: What to do with future instances
            reason: User's explanation for this rule
            agent_instructions: For CUSTOM rules
            rule_config: Additional configuration
        
        Returns:
            The created RecurringEventRule
        """
        # Normalize to parent ID
        parent_id = self.extract_parent_id(recurring_event_id)
        
        session = self.session_factory()
        try:
            # Check if rule already exists (by parent ID)
            existing = session.query(RecurringEventRule).filter_by(id=parent_id).first()
            if existing:
                # Update existing rule
                existing.event_title = event_title
                existing.action = action
                existing.reason = reason
                existing.agent_instructions = agent_instructions
                existing.rule_config = rule_config or {}
                existing.updated_at = datetime.now(timezone.utc)
                session.commit()
                logger.info(f"Updated recurring event rule: {parent_id} -> {action}")
                return existing
            
            # Create new rule (always using parent ID)
            rule = RecurringEventRule(
                id=parent_id,
                event_title=event_title,
                action=action,
                reason=reason,
                agent_instructions=agent_instructions,
                rule_config=rule_config or {},
                application_count={}
            )
            session.add(rule)
            session.commit()
            logger.info(f"Created recurring event rule: {parent_id} -> {action}")
            return rule
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating recurring event rule: {e}")
            raise
        finally:
            session.close()
    
    def get_rule(self, recurring_event_id: str) -> RecurringEventRule | None:
        """
        Get the rule for a recurring event, or None if no rule exists.
        
        Automatically normalizes child event IDs to parent IDs for lookup.
        
        Args:
            recurring_event_id: Either parent or child event ID
            
        Returns:
            The RecurringEventRule for the parent, or None
        """
        # Normalize to parent ID
        parent_id = self.extract_parent_id(recurring_event_id)
        
        session = self.session_factory()
        try:
            return session.query(RecurringEventRule).filter_by(id=parent_id).first()
        finally:
            session.close()
    
    def apply_rule(self, recurring_event_id: str, unified_item) -> bool:
        """
        Apply the stored rule to a UnifiedItem.
        
        Returns:
            True if a rule was applied, False if no rule exists
        """
        rule = self.get_rule(recurring_event_id)
        if not rule:
            return False
        
        session = self.session_factory()
        try:
            # Update application tracking
            now = datetime.now(timezone.utc)
            rule.last_applied = now
            
            # Track applications by date
            date_key = now.strftime("%Y-%m-%d")
            if not rule.application_count:
                rule.application_count = {}
            rule.application_count[date_key] = rule.application_count.get(date_key, 0) + 1
            
            # Apply the action
            from app.assistant.unified_item_manager.unified_item import ItemState
            
            if rule.action == RecurringEventRuleAction.IGNORE:
                unified_item.state = ItemState.DISMISSED
                unified_item.agent_decision = f"Auto-dismissed by recurring rule: {rule.reason or 'User preference'}"
                
            elif rule.action == RecurringEventRuleAction.NORMAL:
                # Leave in NEW state - treat like any other event
                unified_item.agent_notes = f"Recurring event - treat normally: {rule.reason or 'User preference'}"
                
            elif rule.action == RecurringEventRuleAction.CUSTOM:
                unified_item.agent_notes = f"Custom rule: {rule.agent_instructions}"
                # Don't change state - let agent process with custom instructions
                
            # Store rule reference in metadata
            if not unified_item.item_metadata:
                unified_item.item_metadata = {}
            unified_item.item_metadata['applied_rule'] = {
                'rule_id': rule.id,
                'action': rule.action,
                'applied_at': now.isoformat()
            }
            
            session.commit()
            logger.info(f"Applied rule {rule.action} to item {unified_item.unique_id}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error applying rule: {e}")
            raise
        finally:
            session.close()
    
    def get_all_rules(self) -> list[RecurringEventRule]:
        """Get all recurring event rules"""
        session = self.session_factory()
        try:
            return session.query(RecurringEventRule).order_by(RecurringEventRule.event_title).all()
        finally:
            session.close()
    
    def delete_rule(self, recurring_event_id: str) -> bool:
        """Delete a recurring event rule"""
        session = self.session_factory()
        try:
            deleted = session.query(RecurringEventRule).filter_by(id=recurring_event_id).delete()
            session.commit()
            if deleted:
                logger.info(f"Deleted recurring event rule: {recurring_event_id}")
            return deleted > 0
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting rule: {e}")
            raise
        finally:
            session.close()


# ==================== Database Management ====================

def initialize_recurring_event_rules_db():
    """Create recurring_event_rules table if it doesn't exist"""
    session = get_session()
    engine = session.bind
    print("🔧 Creating recurring_event_rules table...")
    Base.metadata.create_all(engine, tables=[RecurringEventRule.__table__], checkfirst=True)
    print("✅ recurring_event_rules table ready")


def drop_recurring_event_rules_db():
    """Drop the recurring_event_rules table"""
    session = get_session()
    engine = session.bind
    print("🗑️  Dropping recurring_event_rules table...")
    RecurringEventRule.__table__.drop(engine, checkfirst=True)
    print("✅ recurring_event_rules table dropped")


def reset_recurring_event_rules_db():
    """Reset the recurring_event_rules table (drop and recreate)"""
    print("🔄 Resetting recurring_event_rules table...")
    drop_recurring_event_rules_db()
    initialize_recurring_event_rules_db()
    print("✅ recurring_event_rules table reset completed")


if __name__ == "__main__":
    print("\n🚀 Initializing recurring_event_rules table...")
    initialize_recurring_event_rules_db()
    print("\n💡 Table created successfully (or already exists)!")
    print("📊 You can now use RecurringEventRuleManager to create and apply rules.\n")

