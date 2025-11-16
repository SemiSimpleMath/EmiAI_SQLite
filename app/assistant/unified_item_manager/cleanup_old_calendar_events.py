"""
Cleanup script: Remove old calendar events from EventRepository
This fixes the pollution caused by find_calendar_event_by_name fetching 2 years of data.
"""

from datetime import datetime, timedelta, timezone
from app.assistant.event_repository.event_repository import EventRepositoryManager, EventRepository
from app.assistant.utils.time_utils import get_local_time

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🧹 CLEANUP: Remove old calendar events from EventRepository")
    print("="*80 + "\n")
    
    repo = EventRepositoryManager()
    session = repo.session_factory()
    
    try:
        # Calculate the valid range (today's midnight + 7 days)
        local_now = get_local_time()
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Convert to UTC for comparison
        start_date_local = local_midnight
        end_date_local = local_midnight + timedelta(days=7)
        
        print(f"📅 Valid calendar range:")
        print(f"   Start: {start_date_local.isoformat()}")
        print(f"   End:   {end_date_local.isoformat()}\n")
        
        # Get all calendar events
        all_calendar_events = session.query(EventRepository).filter(
            EventRepository.data_type == 'calendar'
        ).all()
        
        print(f"📊 Found {len(all_calendar_events)} calendar events in repo\n")
        
        # Filter events to find ones outside the valid range
        events_to_delete = []
        for event in all_calendar_events:
            event_data = event.data
            
            # Parse event start time
            event_start_str = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not event_start_str:
                continue
            
            try:
                # Parse the start time
                if 'T' in event_start_str:
                    event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
                else:
                    # All-day event (date only)
                    event_start = datetime.fromisoformat(event_start_str + 'T00:00:00+00:00')
                
                # Remove timezone for comparison with local times
                if event_start.tzinfo:
                    event_start_naive = event_start.replace(tzinfo=None)
                else:
                    event_start_naive = event_start
                
                start_date_naive = start_date_local.replace(tzinfo=None)
                end_date_naive = end_date_local.replace(tzinfo=None)
                
                # Check if event is outside the valid range
                if event_start_naive < start_date_naive or event_start_naive >= end_date_naive:
                    events_to_delete.append(event)
                    
            except Exception as e:
                print(f"⚠️  Error parsing event: {e}")
                continue
        
        print(f"🗑️  Events outside valid range: {len(events_to_delete)}")
        print(f"✅ Events within valid range: {len(all_calendar_events) - len(events_to_delete)}\n")
        
        if events_to_delete:
            print("🔥 Deleting old events...")
            event_ids = [event.id for event in events_to_delete]
            
            deleted_count = session.query(EventRepository).filter(
                EventRepository.id.in_(event_ids)
            ).delete(synchronize_session=False)
            
            session.commit()
            
            print(f"✅ Deleted {deleted_count} old calendar events\n")
        else:
            print("✅ No cleanup needed - all events are within valid range\n")
        
        # Show final stats
        remaining_count = session.query(EventRepository).filter(
            EventRepository.data_type == 'calendar'
        ).count()
        
        print("="*80)
        print(f"📊 Final count: {remaining_count} calendar events in repo")
        print("="*80 + "\n")
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ Error during cleanup: {e}")
        raise
    finally:
        session.close()


