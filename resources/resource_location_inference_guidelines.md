# Location Inference Guidelines

Use these guidelines when predicting where the user will be at any given time.

## Work Situation
- **Works from home** - Unless there's a calendar event elsewhere, assume home during work hours
- No regular commute to an office

## Known Locations & Travel Times

| Location | City | Travel Time from Home | Notes |
|----------|------|----------------------|-------|
| Home | Irvine, CA | - | Default location |
| Peter's Broadway Arts | Lake Forest, CA | ~25 minutes | Peter's activities |

## Daily Patterns
- Typically awake: 7am - 11pm
- Work hours (from home): Flexible, generally 9am - 5pm
- Most errands: Daytime hours

## Kids' Activities Pattern
- **Drop-off → Home → Pick-up**: For kids' activities (like Peter's Broadway Arts), the typical pattern is:
  1. Drive kids to the activity location
  2. Return home during the activity (don't wait there)
  3. Drive back to pick them up when the activity ends
- This means a 1-2 hour activity generates ~25 min travel each way, with home time in between
- **Exceptions where we wait at the location**:
  - Very short activities (<45 min) - may wait or run nearby errands
  - Doctor/dentist appointments - always wait for the kids
  - Any medical appointments - stay at the location

## Inference Rules

### When predicting gaps between calendar events:
1. **Short gaps (< 1 hour)**: Likely still at previous location or briefly traveling
2. **Medium gaps (1-3 hours)**: Could be running errands nearby, grabbing food, or heading to next location early
3. **Long gaps (> 3 hours)**: Likely returned home, especially if next event is close to home

### Time-of-day considerations:
- **Early morning (before 8am)**: At home unless event starts very early
- **Morning/Afternoon**: Follow calendar; if no events, at home (working)
- **Evening (after 6pm)**: Returning home after events, or at dinner/social events
- **Night (after 10pm)**: At home

### Travel time assumptions:
- Always account for travel time before events with locations
- If an event is 25+ minutes away, assume departure from home ~30-40 minutes before event start
- After events end, assume travel time back home unless another event follows soon

## Notes
- Add new known locations here as they become regular destinations
- Update travel times if traffic patterns change

