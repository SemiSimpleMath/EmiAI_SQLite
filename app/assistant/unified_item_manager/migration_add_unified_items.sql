-- Migration: Add unified_items table
-- Purpose: State-based tracking of external events (email, calendar, todos, scheduler)
--
-- Run this migration:
-- psql -d your_database < migration_add_unified_items.sql
-- OR: python app/assistant/unified_item_manager/unified_item.py init

CREATE TABLE IF NOT EXISTS unified_items (
    id SERIAL PRIMARY KEY,
    unique_id VARCHAR(512) NOT NULL UNIQUE,
    source_type VARCHAR(50) NOT NULL,
    
    -- State machine
    state VARCHAR(50) NOT NULL DEFAULT 'new',
    state_history JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Content
    title VARCHAR(500),
    content TEXT,
    data JSONB,
    item_metadata JSONB,
    
    -- Timestamps
    source_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Snoozing
    snooze_until TIMESTAMP WITH TIME ZONE,
    snooze_count INTEGER DEFAULT 0,
    
    -- Agent decisions
    agent_decision TEXT,
    agent_notes TEXT,
    related_action_id VARCHAR(100),
    
    -- Priority
    importance INTEGER DEFAULT 5
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_unified_items_unique_id ON unified_items(unique_id);
CREATE INDEX IF NOT EXISTS idx_unified_items_state ON unified_items(state);
CREATE INDEX IF NOT EXISTS idx_unified_items_state_created ON unified_items(state, created_at);
CREATE INDEX IF NOT EXISTS idx_unified_items_state_source ON unified_items(state, source_type);
CREATE INDEX IF NOT EXISTS idx_unified_items_source_type_state ON unified_items(source_type, state);
CREATE INDEX IF NOT EXISTS idx_unified_items_snooze_until ON unified_items(snooze_until);
CREATE INDEX IF NOT EXISTS idx_unified_items_created_at ON unified_items(created_at);

-- Comments for documentation
COMMENT ON TABLE unified_items IS 'State-tracked items from external sources (email, calendar, todos, scheduler)';
COMMENT ON COLUMN unified_items.unique_id IS 'Source-specific unique identifier (e.g., email:msg123, calendar:event456)';
COMMENT ON COLUMN unified_items.state IS 'Current state: new, triaged, action_pending, action_taken, dismissed, snoozed, failed';
COMMENT ON COLUMN unified_items.state_history IS 'JSON log of all state transitions';
COMMENT ON COLUMN unified_items.source_type IS 'Source: email, calendar, todo_task, scheduler, calendar_series';
COMMENT ON COLUMN unified_items.source_timestamp IS 'When the event actually occurred (email sent, meeting scheduled)';
COMMENT ON COLUMN unified_items.snooze_until IS 'When to re-present this item if snoozed';
COMMENT ON COLUMN unified_items.importance IS '1-10 scale, higher = more important';

