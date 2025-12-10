# event_repository.py


from datetime import datetime, timezone
import time

from pydantic import BaseModel
from sqlalchemy import func

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message



import hashlib
import json

from sqlalchemy.exc import SQLAlchemyError, OperationalError
from app.models.base import get_session
from app.assistant.database.db_handler import EventRepository

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

# Retry configuration for database locking
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 0.5  # Start with 500ms, will exponentially backoff

class EventRepositoryManager:
    def __init__(self, session_factory=get_session):
        """
        Initialize the repository manager with a SQLAlchemy session factory.
        Also initialize a tracking dict to keep track of event IDs per data type.
        """
        self.session_factory = session_factory
        # Dictionary to track event IDs seen during a sync, keyed by data_type.
        self.tracked_events = {}

    @staticmethod
    def compute_data_hash(data: dict) -> str:
        """
        Computes a hash of the event data to detect changes.
        """
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def store_event(self, id, event_data: dict, data_type: str, event_id=None) -> (str, bool):
        """
        Store or update an event with a composite unique id and external event_id.

        For non-repeating events, 'id' and 'event_id' are the same.
        For repeating events, 'id' is a composite (e.g., event_id + occurrence timestamp)
        while event_id remains the external identifier.

        Returns:
            (event_id, updated) where updated is True if an insert or update occurred.
        """
        if event_id is None:
            event_id = id  # For non-repeating events
        
        # Compute the hash of event_data for change detection.
        if isinstance(event_data, BaseModel):
            event_data = event_data.model_dump()

        event_json = json.dumps(event_data, sort_keys=True)
        event_hash = hashlib.sha256(event_json.encode()).hexdigest()

        logger.debug("store_event called with id=%s, event_id=%s, data_hash=%s, data_type=%s",
                     id, event_id, event_hash, data_type)

        # Retry logic for database locking
        last_exception = None
        for attempt in range(MAX_RETRIES):
            session = self.session_factory()
            try:
                # Query by both the composite unique id and external event_id.
                existing_event = session.query(EventRepository).filter_by(id=id, event_id=event_id).one_or_none()

                if existing_event:
                    # If the data hasn't changed, skip updating.
                    if existing_event.data_hash == event_hash:
                        logger.debug("No changes detected for event with id=%s", id)
                        updated = False
                    else:
                        # Update the existing event.
                        existing_event.data = event_data
                        existing_event.data_hash = event_hash
                        existing_event.created_at = datetime.now(timezone.utc)
                        session.commit()
                        logger.debug("Updated event with id=%s", id)
                        updated = True
                else:
                    # Insert a new event.
                    event = EventRepository(
                        id=id,
                        event_id=event_id,
                        data=event_data,
                        data_type=data_type,
                        data_hash=event_hash
                    )
                    session.add(event)
                    session.commit()
                    logger.debug("Inserted new event with id=%s", id)
                    updated = True

                # Track this event as seen for the given data_type.
                if data_type not in self.tracked_events:
                    self.tracked_events[data_type] = set()
                self.tracked_events[data_type].add(id)

                return id, updated

            except OperationalError as e:
                session.rollback()
                # Check if it's a database lock error
                if "database is locked" in str(e):
                    last_exception = e
                    delay = RETRY_DELAY_SECONDS * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        "Database locked on attempt %d/%d for event id=%s. Retrying in %.2fs...",
                        attempt + 1, MAX_RETRIES, id, delay
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error("Error storing event: %s", e)
                    raise
            except SQLAlchemyError as e:
                session.rollback()
                logger.error("Error storing event: %s", e)
                raise
            finally:
                session.close()
        
        # All retries exhausted
        logger.error("Failed to store event after %d retries: %s", MAX_RETRIES, last_exception)
        raise last_exception

    def get_event_by_id(self, event_id: str) -> dict:
        """
        Retrieves an event from the repository by its id.

        Returns:
            dict: Dictionary containing 'data_type' and 'data' if found, else None.
        """
        session = self.session_factory()
        try:
            event = session.query(EventRepository).filter(EventRepository.id == event_id).one_or_none()
            if event:
                logger.debug(f"Retrieved event with id: {event_id}")
                return {"data_type": event.data_type, "data": event.data}
            else:
                logger.warning(f"Event with id {event_id} not found")
                return None
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving event by id: {e}")
            raise
        finally:
            session.close()

    def search_events(self, data_type: str = None, keyword: str = None) -> str:
        """
        Searches events by data_type and an optional keyword inside the JSON field.

        Returns:
            str: A JSON string containing a list of dictionaries with 'id', 'data_type', and 'data'.
        """
        session = self.session_factory()
        try:
            query = session.query(EventRepository)

            if data_type:
                query = query.filter(EventRepository.data_type == data_type)

            if keyword:
                # Assumes a "summary" field exists inside the JSON data
                query = query.filter(
                    EventRepository.data["summary"].astext.ilike(f"%{keyword}%")
                )

            events = query.all()
            logger.debug(f"Found {len(events)} events with filters data_type={data_type}, keyword={keyword}")

            event_dicts = [
                {
                    "data_type": event.data_type,
                    "data": event.data
                }
                for event in events
            ]

            # Return JSON string, ensuring consistency with `get_new_events()`
            return json.dumps(event_dicts)
        except SQLAlchemyError as e:
            logger.error(f"Error searching events: {e}")
            raise
        finally:
            session.close()

    def delete_event(self, event_id: str, data_type: str) -> bool:
        """
        Deletes all events from the repository that have the given external event_id.

        Returns:
            bool: True if one or more events were found and deleted; False otherwise.
        """
        session = self.session_factory()
        try:
            # Query all events with the matching external event_id.
            events = session.query(EventRepository).filter(
                EventRepository.data_type == data_type,
                EventRepository.event_id == event_id
            ).all()

            if events:
                for event in events:
                    session.delete(event)
                session.commit()
                logger.debug(
                    f"Deleted {len(events)} event(s) with external event_id: {event_id} in data_type: {data_type}")
                return True
            else:
                logger.warning(f"No event found with external event_id: {event_id} in data_type: {data_type}")
                return False
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Error deleting event: {e}")
            raise
        finally:
            session.close()

    def get_last_altered_by_data_type(self) -> dict:
        """
        Returns a dictionary mapping each data type to the most recent (max) last_updated timestamp.

        Returns:
            dict: Keys are data types (e.g., "calendar", "email", "todo") and values are the corresponding
                  created_at timestamps.
        """
        session = self.session_factory()
        try:
            results = session.query(
                EventRepository.data_type,
                func.max(EventRepository.created_at).label("last_altered")
            ).group_by(EventRepository.data_type).all()

            # Build and return the dictionary
            last_altered_dict = {data_type: last_altered for data_type, last_altered in results}
            return last_altered_dict
        except Exception as e:
            # Log and re-raise if needed
            raise e
        finally:
            session.close()

    def get_new_events(self, category: str, since_dt: datetime) -> str:
        """
        Retrieves events of the given category that were created since `since_dt`.

        Args:
            category (str): The category of events (e.g., 'calendar', 'todo_task').
            since_dt (datetime): The timestamp to filter new events.

        Returns:
            str: JSON string of new events.
        """
        session = self.session_factory()
        try:
            query = session.query(EventRepository).filter(
                EventRepository.data_type == category,
                EventRepository.created_at > since_dt  # Use created_at column
            )

            events = query.all()

            event_dicts = [
                {"data_type": event.data_type, "data": event.data}
                for event in events
            ]

            return json.dumps(event_dicts)

        except SQLAlchemyError as e:
            logger.error(f"Error fetching new events: {e}")
            raise
        finally:
            session.close()

    def sync_events_with_server(self, server_events: list, data_type: str):
        from datetime import datetime, timezone, timedelta

        logger.debug("sync_events_with_server called for %s", data_type)
        session = self.session_factory()

        try:
            if data_type == "calendar":
                # Existing behavior: reconcile against server_ids
                server_ids = set(server_events)

                db_events = session.query(EventRepository).filter(
                    EventRepository.data_type == data_type
                ).all()
                db_ids = {event.id for event in db_events}
                missing_ids = db_ids - server_ids

                if missing_ids:
                    deleted_count = session.query(EventRepository).filter(
                        EventRepository.id.in_(missing_ids)
                    ).delete(synchronize_session=False)
                    session.commit()

                    if deleted_count > 0:
                        logger.debug(
                            f"Deleted {deleted_count} calendar events not in current fetch window."
                        )
                else:
                    logger.debug("No stale calendar events found.")

            else:
                # Email and other transient types: sliding time window only.
                # Ignore server_events; just enforce retention.
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=10)

                deleted_count = session.query(EventRepository).filter(
                    EventRepository.data_type == data_type,
                    EventRepository.created_at < cutoff_time,
                    ).delete(synchronize_session=False)
                session.commit()

                if deleted_count > 0:
                    logger.debug(
                        f"Deleted {deleted_count} '{data_type}' events older than {cutoff_time.isoformat()}."
                    )
                else:
                    logger.debug(
                        f"No '{data_type}' events older than {cutoff_time.isoformat()} to delete."
                    )

        except SQLAlchemyError as e:
            session.rollback()
            logger.error("Error syncing events: %s", e)
            raise
        finally:
            session.close()

        # Notify system of repo update
        repo_msg = Message(
            sender="repo_sync",
            receiver=None,
            data_type="agent_msg",
            content=data_type,
        )
        repo_msg.event_topic = "repo_update"
        DI.event_hub.publish(repo_msg)



if __name__ == "__main__":

    # Initialize the repository manager.
    erm = EventRepositoryManager()

    # Example event data.
    sample_event = {
        "title": "Test Event",
        "details": "This is a sample event for testing."
    }
    data_type = "calendar"

    # Search events by category.
    events = erm.search_events(data_type=data_type)
    print(f"Found {len(events)} event(s) in category '{data_type}'.")
    for event in events:
        print(event)
