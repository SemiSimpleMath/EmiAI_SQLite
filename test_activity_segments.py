"""
Test script to debug activity segment computation.
Run with: python test_activity_segments.py
"""

from datetime import datetime, timezone, timedelta
from app.assistant.afk_manager.afk_db import get_active_segments_overlapping_range
from app.assistant.day_flow_manager.utils.context_sources import get_significant_activity_segments
from app.assistant.utils.time_utils import utc_to_local

def main():
    now_utc = datetime.now(timezone.utc)
    
    # Use day start from pipeline status or fallback to 14 hours ago
    try:
        import json
        from pathlib import Path
        status_path = Path("resources/resource_wellness_pipeline_status.json")
        status = json.loads(status_path.read_text())
        day_start_str = status.get("day_start_time_utc")
        if day_start_str:
            since_utc = datetime.fromisoformat(day_start_str.replace("Z", "+00:00"))
        else:
            since_utc = now_utc - timedelta(hours=14)
    except:
        since_utc = now_utc - timedelta(hours=14)
    
    print(f"=" * 70)
    print(f"NOW (UTC):       {now_utc.isoformat()}")
    print(f"NOW (local):     {utc_to_local(now_utc).strftime('%I:%M %p')}")
    print(f"SINCE (UTC):     {since_utc.isoformat()}")
    print(f"SINCE (local):   {utc_to_local(since_utc).strftime('%I:%M %p')}")
    print(f"=" * 70)
    
    # Get raw active segments
    print("\n## RAW ACTIVE SEGMENTS FROM DB:")
    print("-" * 70)
    
    active_segments = get_active_segments_overlapping_range(
        start_utc=since_utc,
        end_utc=now_utc,
        include_provisional=True,
    )
    
    # Sort and print
    sorted_segs = sorted(active_segments, key=lambda s: s.start_time)
    
    for i, seg in enumerate(sorted_segs):
        start_local = utc_to_local(seg.start_time).strftime('%I:%M %p')
        end_local = utc_to_local(seg.end_time).strftime('%I:%M %p')
        duration = (seg.end_time - seg.start_time).total_seconds() / 60
        print(f"  {i+1:2}. {start_local:>8} - {end_local:>8}  ({duration:6.1f} min)  provisional={seg.is_provisional}")
    
    print(f"\nTotal raw segments: {len(sorted_segs)}")
    
    # Compute gaps between segments
    print("\n## GAPS BETWEEN SEGMENTS (potential AFK periods):")
    print("-" * 70)
    
    cursor = since_utc
    for seg in sorted_segs:
        seg_start = seg.start_time
        seg_end = seg.end_time
        # Make timezone aware if needed
        if seg_start.tzinfo is None:
            seg_start = seg_start.replace(tzinfo=timezone.utc)
        if seg_end.tzinfo is None:
            seg_end = seg_end.replace(tzinfo=timezone.utc)
            
        if seg_start > cursor:
            gap_start_local = utc_to_local(cursor).strftime('%I:%M %p')
            gap_end_local = utc_to_local(seg_start).strftime('%I:%M %p')
            gap_duration = (seg_start - cursor).total_seconds() / 60
            marker = " ** SIGNIFICANT" if gap_duration >= 10 else ""
            print(f"  GAP: {gap_start_local:>8} - {gap_end_local:>8}  ({gap_duration:6.1f} min){marker}")
        cursor = max(cursor, seg_end)
    
    # Final gap to now
    if cursor < now_utc:
        gap_start_local = utc_to_local(cursor).strftime('%I:%M %p')
        gap_end_local = utc_to_local(now_utc).strftime('%I:%M %p')
        gap_duration = (now_utc - cursor).total_seconds() / 60
        marker = " ** SIGNIFICANT" if gap_duration >= 10 else ""
        print(f"  GAP: {gap_start_local:>8} - {gap_end_local:>8}  ({gap_duration:6.1f} min)  [to now]{marker}")
    
    # Filter < 5 min segments
    print("\n## SEGMENTS AFTER FILTERING < 5 min:")
    print("-" * 70)
    filtered_count = 0
    for seg in sorted_segs:
        seg_start = seg.start_time
        seg_end = seg.end_time
        if seg_start.tzinfo is None:
            seg_start = seg_start.replace(tzinfo=timezone.utc)
        if seg_end.tzinfo is None:
            seg_end = seg_end.replace(tzinfo=timezone.utc)
        duration = (seg_end - seg_start).total_seconds() / 60
        if duration < 5.0:
            start_local = utc_to_local(seg_start).strftime('%I:%M %p')
            end_local = utc_to_local(seg_end).strftime('%I:%M %p')
            print(f"  FILTERED: {start_local:>8} - {end_local:>8}  ({duration:6.1f} min)")
            filtered_count += 1
    print(f"  Total filtered: {filtered_count}")
    
    # Now show what the function outputs
    print("\n## FUNCTION OUTPUT (get_significant_activity_segments):")
    print("   noise_threshold=5 min, merge_gap=10 min")
    print("-" * 70)
    
    result = get_significant_activity_segments(since_utc, noise_threshold_minutes=5.0, merge_gap_minutes=10.0)
    for line in result:
        print(f"  - {line}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
