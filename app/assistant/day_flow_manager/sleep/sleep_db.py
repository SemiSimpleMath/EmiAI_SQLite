# sleep_db.py
"""
Sleep Database Layer

Handles all database operations for sleep and wake segments:
- Recording sleep segments
- Recording wake segments (night wakings)
- Querying sleep/wake data
- Cleanup of old segments
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError

from app.models.base import get_session
from app.models.sleep_segments import SleepSegment
from app.models.wake_segments import WakeSegment
from app.assistant.utils.error_logging import log_critical_error
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


# =========================================================================
# Sleep Segment Operations
# =========================================================================

def record_sleep_segment(
        start_time: datetime,
        end_time: Optional[datetime] = None,
        duration_minutes: Optional[float] = None,
        source: str = 'afk_detection',
        raw_mention: Optional[str] = None
) -> Optional[int]:
    """
    Record a new sleep segment.
    
    Args:
        start_time: When sleep started (bedtime) - UTC
        end_time: When sleep ended (wake time) - UTC, None if ongoing
        duration_minutes: Sleep duration (computed if both times provided)
        source: 'afk_detection', 'user_chat', 'cold_start_assumed', 'manual'
        raw_mention: User's original text (if from chat)
    
    Returns:
        ID of created sleep segment, or None if failed
    """
    session = get_session()
    try:
        # Calculate duration if both times provided
        if end_time and not duration_minutes:
            duration_minutes = (end_time - start_time).total_seconds() / 60

        sleep_segment = SleepSegment(
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            source=source,
            raw_mention=raw_mention
        )
        session.add(sleep_segment)
        session.commit()

        segment_id = sleep_segment.id
        logger.info(f"Recorded sleep segment (ID: {segment_id}): {duration_minutes:.1f if duration_minutes else 0} min [source: {source}]")
        return segment_id

    except SQLAlchemyError as e:
        session.rollback()
        log_critical_error(
            "sleep_db.record_sleep_segment",
            f"Failed to record sleep segment starting {start_time}",
            e
        )
        return None
    finally:
        session.close()


def update_sleep_segment_end(segment_id: int, end_time: datetime) -> bool:
    """
    Update an existing sleep segment with an end time.
    
    Args:
        segment_id: ID of the sleep segment to update
        end_time: When the sleep ended (wake time) - UTC
    
    Returns:
        True if successful, False otherwise
    """
    session = get_session()
    try:
        segment = session.query(SleepSegment).filter(
            SleepSegment.id == segment_id
        ).first()

        if not segment:
            return False

        segment.end_time = end_time
        segment.duration_minutes = (end_time - segment.start_time).total_seconds() / 60

        session.commit()
        return True

    except SQLAlchemyError as e:
        session.rollback()
        log_critical_error(
            "sleep_db.update_sleep_segment_end",
            f"Failed to update sleep segment {segment_id}",
            e
        )
        return False
    finally:
        session.close()


def get_sleep_segments_last_24_hours() -> List[Dict[str, Any]]:
    """
    Get all sleep segments from the last 24 hours.
    
    Returns:
        List of sleep segment dictionaries, newest first
    """
    session = get_session()
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

        segments = session.query(SleepSegment).filter(
            SleepSegment.start_time >= cutoff_time
        ).order_by(desc(SleepSegment.start_time)).all()

        return [
            {
                'id': s.id,
                'start': s.start_time.isoformat(),
                'end': s.end_time.isoformat() if s.end_time else None,
                'duration_minutes': s.duration_minutes,
                'source': s.source,
                'raw_mention': s.raw_mention
            }
            for s in segments
        ]

    except SQLAlchemyError as e:
        log_critical_error(
            "sleep_db.get_sleep_segments_last_24_hours",
            "Failed to fetch sleep segments for last 24h",
            e
        )
        return []
    finally:
        session.close()


def get_ongoing_sleep_segment() -> Optional[Dict[str, Any]]:
    """
    Get the current ongoing sleep segment (end_time is NULL).
    
    Returns:
        Dictionary with ongoing sleep segment, or None if not found
    """
    session = get_session()
    try:
        segment = session.query(SleepSegment).filter(
            SleepSegment.end_time.is_(None)
        ).order_by(desc(SleepSegment.start_time)).first()

        if segment:
            return {
                'id': segment.id,
                'start': segment.start_time.isoformat(),
                'end': None,
                'duration_minutes': None,
                'source': segment.source,
                'raw_mention': segment.raw_mention
            }
        return None

    except SQLAlchemyError as e:
        log_critical_error(
            "sleep_db.get_ongoing_sleep_segment",
            "Failed to fetch ongoing sleep segment",
            e
        )
        return None
    finally:
        session.close()


def cleanup_old_sleep_segments(days: int = 7) -> int:
    """
    Delete sleep segments older than N days.
    
    Args:
        days: Number of days to keep (default: 7)
    
    Returns:
        Number of records deleted
    """
    session = get_session()
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        deleted_count = session.query(SleepSegment).filter(
            SleepSegment.start_time < cutoff_time
        ).delete()

        session.commit()
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old sleep segments (>{days} days)")
        
        return deleted_count

    except SQLAlchemyError as e:
        session.rollback()
        log_critical_error(
            "sleep_db.cleanup_old_sleep_segments",
            f"Failed to cleanup sleep segments older than {days} days",
            e
        )
        return 0
    finally:
        session.close()


# =========================================================================
# Wake Segment Operations
# =========================================================================

def record_wake_segment(
        start_time: datetime,
        end_time: Optional[datetime] = None,
        duration_minutes: Optional[float] = None,
        source: str = 'user_chat',
        notes: Optional[str] = None
) -> Optional[int]:
    """
    Record a wake segment (user was awake during sleep hours).
    
    Args:
        start_time: When user woke up during the night (UTC)
        end_time: When user went back to sleep (UTC). Optional if duration provided.
        duration_minutes: How long they were awake (minutes). Required if end_time not provided.
        source: How we learned about this ('user_chat', 'manual', 'activity_tracker')
        notes: Optional notes (e.g., 'bathroom', 'couldn't sleep')
    
    Returns:
        ID of created wake segment, or None if failed
    """
    session = get_session()
    try:
        # Calculate duration
        if end_time:
            calc_duration = (end_time - start_time).total_seconds() / 60
        elif duration_minutes:
            calc_duration = duration_minutes
        else:
            logger.error("record_wake_segment: must provide either end_time or duration_minutes")
            return None

        wake_segment = WakeSegment(
            start_time=start_time,
            end_time=end_time,
            duration_minutes=calc_duration,
            source=source,
            notes=notes
        )

        session.add(wake_segment)
        session.commit()

        segment_id = wake_segment.id
        logger.info(f"Recorded wake segment (ID: {segment_id}): {calc_duration:.1f} min [source: {source}]")

        return segment_id

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to record wake segment: {e}")
        return None
    finally:
        session.close()


def get_wake_segments_last_24_hours() -> List[Dict[str, Any]]:
    """
    Get all wake segments from the last 24 hours.
    
    Returns:
        List of wake segment dicts with keys: id, start_time, end_time, duration_minutes, source, notes
    """
    session = get_session()
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

        segments = session.query(WakeSegment).filter(
            WakeSegment.start_time >= cutoff_time
        ).order_by(WakeSegment.start_time).all()

        return [
            {
                'id': seg.id,
                'start_time': seg.start_time.isoformat(),
                'end_time': seg.end_time.isoformat() if seg.end_time else None,
                'duration_minutes': seg.duration_minutes,
                'source': seg.source,
                'notes': seg.notes
            }
            for seg in segments
        ]

    except Exception as e:
        logger.error(f"Failed to get wake segments: {e}")
        return []
    finally:
        session.close()


def cleanup_old_wake_segments(days: int = 30) -> int:
    """
    Delete wake segments older than specified days.
    
    Args:
        days: Keep segments from last N days, delete older ones
    
    Returns:
        Number of segments deleted
    """
    session = get_session()
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        deleted_count = session.query(WakeSegment).filter(
            WakeSegment.start_time < cutoff_time
        ).delete()

        session.commit()

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old wake segments (>{days} days)")

        return deleted_count

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to cleanup wake segments: {e}")
        return 0
    finally:
        session.close()
