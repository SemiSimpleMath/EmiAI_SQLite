# afk_db.py
"""
AFK Database Layer

Handles all database operations for active/AFK tracking:
- Recording active sessions (when user is at keyboard)
- Querying active segments
- Cleanup of old records

The model is "Active-First":
- We record when user IS active (positive evidence)
- AFK time = gaps between active segments
- No data = unknown (conservative default)
"""
from datetime import datetime, timedelta, timezone
import json
from typing import List, Optional, Dict, Any
from sqlalchemy import desc, asc
from sqlalchemy.exc import SQLAlchemyError

from app.models.base import get_session
from app.models.active_segments import ActiveSegment
from app.models.base import Base
from app.assistant.utils.error_logging import log_critical_error
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

# region agent log
_DEBUG_LOG_PATH = r"e:\EmiAi_sqlite\.cursor\debug.log"


def _debug_ts_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _debug_log(hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": "wake_time_investigation_active_segments",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": _debug_ts_ms(),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception as e:
        # Don't swallow: this makes investigations impossible when the debug sink breaks.
        logger.debug(f"afk_db debug log write failed: {e}", exc_info=True)
# endregion


_table_initialized = False


def _init_table(session) -> None:
    """Create active_segments table if it doesn't exist."""
    global _table_initialized
    if _table_initialized:
        return
    try:
        Base.metadata.create_all(session.bind, tables=[
            ActiveSegment.__table__
        ], checkfirst=True)
        _table_initialized = True
    except Exception as e:
        logger.warning(f"Failed to create active_segments table: {e}")


# =============================================================================
# Active Segment Functions (NEW - source of truth)
# =============================================================================

def record_active_segment(
        start_time_utc: datetime,
        end_time_utc: datetime,
) -> bool:
    """
    Record a completed active session.
    
    Called when user goes AFK (closing their active session).
    
    Args:
        start_time_utc: When user became active (UTC)
        end_time_utc: When user went AFK (UTC)
    
    Returns:
        True if successful, False otherwise
    """
    session = get_session()
    try:
        _init_table(session)
        
        if end_time_utc <= start_time_utc:
            logger.warning("Active segment end_time <= start_time; skipping record")
            return False

        duration_minutes = (end_time_utc - start_time_utc).total_seconds() / 60.0
        
        active_segment = ActiveSegment(
            start_time=start_time_utc,
            end_time=end_time_utc,
            duration_minutes=duration_minutes,
        )
        session.add(active_segment)
        session.commit()
        
        logger.info(f"Recorded active segment: {duration_minutes:.1f} min")
        # region agent log
        _debug_log(
            "H1",
            "afk_db.py:record_active_segment",
            "Recorded finalized active segment",
            {
                "start_time_utc": start_time_utc.isoformat(),
                "end_time_utc": end_time_utc.isoformat(),
                "duration_minutes": round(duration_minutes, 2),
            },
        )
        # endregion
        return True

    except SQLAlchemyError as e:
        session.rollback()
        log_critical_error(
            "afk_db.record_active_segment",
            "Failed to record active segment",
            e
        )
        return False
    finally:
        session.close()


def create_provisional_segment(start_time_utc: datetime) -> Optional[int]:
    """
    Create a provisional (open) active segment when user becomes active.
    
    The segment is created with end_time = start_time, duration = 0, and is_provisional = True.
    It should be updated periodically and finalized when user goes AFK.
    
    Args:
        start_time_utc: When user became active (UTC)
    
    Returns:
        Segment ID if successful, None otherwise
    """
    session = get_session()
    try:
        _init_table(session)
        
        active_segment = ActiveSegment(
            start_time=start_time_utc,
            end_time=start_time_utc,  # Provisional: end = start
            duration_minutes=0.0,
            is_provisional=True,  # Mark as provisional (open)
        )
        session.add(active_segment)
        session.commit()
        
        segment_id = active_segment.id
        logger.info(f"Created provisional segment ID={segment_id}")
        # region agent log
        _debug_log(
            "H2",
            "afk_db.py:create_provisional_segment",
            "Created provisional active segment",
            {
                "segment_id": segment_id,
                "start_time_utc": start_time_utc.isoformat(),
            },
        )
        # endregion
        return segment_id

    except SQLAlchemyError as e:
        session.rollback()
        log_critical_error(
            "afk_db.create_provisional_segment",
            "Failed to create provisional segment",
            e
        )
        return None
    finally:
        session.close()


def update_segment(segment_id: int, end_time_utc: datetime, finalize: bool = False) -> bool:
    """
    Update an existing segment's end_time and duration.
    
    Used to periodically update provisional segments and finalize them.
    
    Args:
        segment_id: ID of segment to update
        end_time_utc: New end time (UTC)
        finalize: If True, set is_provisional=False (segment is complete)
    
    Returns:
        True if successful, False otherwise
    """
    session = get_session()
    try:
        _init_table(session)
        
        segment = session.query(ActiveSegment).filter(
            ActiveSegment.id == segment_id
        ).first()
        
        if not segment:
            logger.warning(f"Segment ID={segment_id} not found for update")
            return False
        
        # Calculate new duration
        start_time = segment.start_time
        if hasattr(start_time, 'tzinfo') and start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        
        duration_minutes = (end_time_utc - start_time).total_seconds() / 60.0
        if duration_minutes < 0:
            duration_minutes = 0.0
        
        segment.end_time = end_time_utc
        segment.duration_minutes = duration_minutes
        
        if finalize:
            segment.is_provisional = False
        
        session.commit()
        # region agent log
        _debug_log(
            "H2",
            "afk_db.py:update_segment",
            "Updated active segment",
            {
                "segment_id": segment_id,
                "end_time_utc": end_time_utc.isoformat(),
                "duration_minutes": round(duration_minutes, 2),
                "finalize": finalize,
                "is_provisional": segment.is_provisional,
            },
        )
        # endregion
        
        return True

    except SQLAlchemyError as e:
        session.rollback()
        log_critical_error(
            "afk_db.update_segment",
            f"Failed to update segment ID={segment_id}",
            e
        )
        return False
    finally:
        session.close()


def get_open_segment(max_age_minutes: int = 30) -> Optional[Dict[str, Any]]:
    """
    Find an open (provisional) segment from a previous session.
    
    An "open" segment is one where:
    - is_provisional = True
    - end_time is within the last max_age_minutes (safety check for stale segments)
    
    Args:
        max_age_minutes: How recent the end_time must be to consider recovering
    
    Returns:
        Segment dict if found, None otherwise
    """
    session = get_session()
    try:
        _init_table(session)
        
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        
        # Look for provisional segment that's recent enough
        segment = session.query(ActiveSegment).filter(
            ActiveSegment.is_provisional == True
        ).order_by(desc(ActiveSegment.end_time)).first()
        
        if not segment:
            return None
        
        # Check if end_time is recent enough to be worth recovering
        end_time = segment.end_time
        if hasattr(end_time, 'tzinfo') and end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        
        if end_time >= cutoff:
            return {
                'id': segment.id,
                'start_time': segment.start_time,
                'end_time': segment.end_time,
                'duration_minutes': segment.duration_minutes,
                'is_provisional': segment.is_provisional,
            }
        else:
            # Segment is too old - finalize it at its last known time
            segment.is_provisional = False
            session.commit()
            logger.info(f"Finalized stale provisional segment ID={segment.id}")
        
        return None

    except SQLAlchemyError as e:
        log_critical_error(
            "afk_db.get_open_segment",
            "Failed to check for open segment",
            e
        )
        return None
    finally:
        session.close()


def get_active_segments_since(since_utc: datetime) -> List[ActiveSegment]:
    """
    Get FINALIZED active segments that overlap with or are after since_utc.
    
    Excludes provisional (open) segments to avoid double-counting with
    the current active session tracked in memory.
    
    Returns raw ORM objects for statistics computation.
    """
    session = get_session()
    try:
        _init_table(session)
        
        segments = session.query(ActiveSegment).filter(
            ActiveSegment.end_time >= since_utc,
            ActiveSegment.is_provisional == False  # Exclude provisional segments
        ).order_by(asc(ActiveSegment.start_time)).all()
        
        # Detach from session
        for seg in segments:
            session.expunge(seg)
        
        return segments

    except SQLAlchemyError as e:
        log_critical_error(
            "afk_db.get_active_segments_since",
            f"Failed to fetch active segments since {since_utc}",
            e
        )
        return []
    finally:
        session.close()


def get_active_segments_overlapping_range(
    start_utc: datetime,
    end_utc: datetime,
    include_provisional: bool = True,
) -> List[ActiveSegment]:
    """
    Get active segments that overlap a time range.

    Args:
        start_utc: Range start (UTC)
        end_utc: Range end (UTC)
        include_provisional: Include open segments if True

    Returns:
        List of ActiveSegment ORM objects (detached)
    """
    session = get_session()
    try:
        _init_table(session)

        query = session.query(ActiveSegment).filter(
            ActiveSegment.start_time <= end_utc,
            ActiveSegment.end_time >= start_utc,
        )
        if not include_provisional:
            query = query.filter(ActiveSegment.is_provisional == False)

        segments = query.order_by(asc(ActiveSegment.start_time)).all()

        for seg in segments:
            session.expunge(seg)

        return segments
    except SQLAlchemyError as e:
        log_critical_error(
            "afk_db.get_active_segments_overlapping_range",
            f"Failed to fetch active segments between {start_utc} and {end_utc}",
            e,
        )
        return []
    finally:
        session.close()


def get_recent_active_segments(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get active segments from the last N hours.
    
    Returns:
        List of active segment dictionaries, oldest first
    """
    session = get_session()
    try:
        _init_table(session)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        segments = session.query(ActiveSegment).filter(
            ActiveSegment.end_time >= cutoff_time
        ).order_by(asc(ActiveSegment.start_time)).all()

        result = [
            {
                'id': s.id,
                'start_time': s.start_time.isoformat(),
                'end_time': s.end_time.isoformat(),
                'duration_minutes': s.duration_minutes,
                'created_at': s.created_at.isoformat() if s.created_at else None,
            }
            for s in segments
        ]
        # region agent log
        _debug_log(
            "H3",
            "afk_db.py:get_recent_active_segments",
            "Fetched recent active segments",
            {
                "hours": hours,
                "count": len(result),
                "first_start_time": result[0].get("start_time") if result else None,
                "last_start_time": result[-1].get("start_time") if result else None,
            },
        )
        # endregion
        return result

    except SQLAlchemyError as e:
        log_critical_error(
            "afk_db.get_recent_active_segments",
            f"Failed to fetch active segments for last {hours}h",
            e
        )
        return []
    finally:
        session.close()


def get_last_active_segment() -> Optional[Dict[str, Any]]:
    """
    Get the most recent active segment.
    """
    session = get_session()
    try:
        _init_table(session)
        segment = session.query(ActiveSegment).order_by(desc(ActiveSegment.end_time)).first()

        if segment:
            return {
                'id': segment.id,
                'start_time': segment.start_time.isoformat(),
                'end_time': segment.end_time.isoformat(),
                'duration_minutes': segment.duration_minutes,
            }
        return None

    except SQLAlchemyError as e:
        log_critical_error(
            "afk_db.get_last_active_segment",
            "Failed to fetch last active segment",
            e
        )
        return None
    finally:
        session.close()


def cleanup_old_active_segments(days: int = 7) -> int:
    """
    Delete active segments older than N days.
    
    Returns:
        Number of records deleted
    """
    session = get_session()
    try:
        _init_table(session)
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        deleted_count = session.query(ActiveSegment).filter(
            ActiveSegment.end_time < cutoff_time
        ).delete()

        session.commit()
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old active segments (>{days} days)")
        
        return deleted_count

    except SQLAlchemyError as e:
        session.rollback()
        log_critical_error(
            "afk_db.cleanup_old_active_segments",
            f"Failed to cleanup active segments older than {days} days",
            e
        )
        return 0
    finally:
        session.close()
