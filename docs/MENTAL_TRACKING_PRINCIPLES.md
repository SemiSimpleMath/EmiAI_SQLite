# Mental Tracking: What Would Actually Help?

## The Core Question
**"If I were a helpful friend checking in on you, what would I want to know to be genuinely helpful?"**

---

## TIER 1: OBSERVABLE FACTS (Must Track)

### 1. **What You're Currently Working On**
**Why it matters:** Can't help if I don't know what you're doing

**What to track:**
- Current task/project from chat ("working on the database migration")
- Current calendar event ("Analytics meeting")
- Recent accepted activities ("just walked the dogs")

**How it helps:**
- ✅ Don't suggest walks when you just walked
- ✅ Don't interrupt deep work with non-urgent items
- ✅ Suggest relevant resources ("need the API docs?")
- ✅ Remember context across sessions ("how's the migration going?")

**Trackable?** YES - from chat + calendar + recent tickets

---

### 2. **Physical Needs Being Neglected**
**Why it matters:** Health matters more than work

**What to track:**
- Time since last: water, food, bathroom break, movement
- Chronic pain timers (finger stretch overdue by 30 min)
- Sleep debt accumulation

**How it helps:**
- ✅ "You haven't had water in 3 hours - here's your bottle reminder"
- ✅ "Your fingers are overdue for a stretch by 30 min"
- ✅ Escalate urgency as neglect grows

**Trackable?** YES - we do this already

---

### 3. **How Busy/Available You Are**
**Why it matters:** Timing is everything

**What to track:**
- Meetings in next 2 hours
- Back-to-back meeting risk
- Current work session duration (proxy for focus)
- Recent dismissal rate (am I being annoying?)

**How it helps:**
- ✅ "Meeting in 10 min - quick stretch now?"
- ✅ Don't interrupt 2-hour deep work session
- ✅ Batch suggestions when you have gaps
- ✅ Back off if you're dismissing everything

**Trackable?** YES - from calendar + AFK + ticket responses

---

### 4. **What You Usually Do When**
**Why it matters:** Work with your rhythms, not against them

**What to track:**
- Typical coffee times (9 AM, 2 PM)
- Typical meal times (12 PM, 6 PM)
- Focus hours (9 AM - 12 PM)
- Exercise patterns (evening walks)

**How it helps:**
- ✅ Suggest coffee at your usual time
- ✅ Don't suggest exercise during focus hours
- ✅ Adapt to your schedule changes
- ✅ Notice anomalies ("you usually have lunch by now")

**Trackable?** YES - learn from historical wellness_activities + calendar

---

### 5. **What Suggestions You Accept/Reject**
**Why it matters:** Learn what helps, stop what annoys

**What to track:**
- Acceptance rate by suggestion type
- Acceptance rate by time-of-day
- Which suggestions get text responses
- Pattern: "always dismisses exercise suggestions"

**How it helps:**
- ✅ Stop suggesting things you never do
- ✅ Learn preferred timing for each activity
- ✅ Prioritize suggestions you engage with
- ✅ Adapt to changing preferences

**Trackable?** YES - from proactive_tickets history

---

## TIER 2: INFERRABLE STATE (Worth Computing)

### 6. **Energy/Fatigue Level**
**Why it matters:** Tired people need different help

**What to infer from:**
- Sleep quality + time awake
- Time of day (afternoon dip)
- Recent meal timing
- Work session duration

**How it helps:**
- ✅ "You're 8 hours from last meal and low sleep - coffee or food?"
- ✅ Suggest power nap at 2 PM after bad sleep
- ✅ Don't suggest exercise when exhausted
- ✅ Reduce suggestion complexity when tired

**Trackable?** YES - rule-based from measurable inputs

---

### 7. **Cognitive Load / "Can I Handle This?"**
**Why it matters:** Don't add to overwhelm

**What to infer from:**
- Number of upcoming meetings
- Work session duration (proxy for focus)
- Chat tone/length (short = busy)
- Recent context switches

**How it helps:**
- ✅ "Packed schedule detected - only critical reminders today"
- ✅ Wait for natural break to suggest
- ✅ Keep messages shorter when busy
- ✅ Don't ask open-ended questions when slammed

**Trackable?** MOSTLY - from calendar + work session + chat

---

### 8. **Pain/Discomfort Level**
**Why it matters:** Pain changes priorities

**What to infer from:**
- Time since last preventive activity (stretch)
- Explicit mentions in chat ("my back hurts")
- Chronic condition flare patterns

**How it helps:**
- ✅ Escalate stretch reminders when overdue
- ✅ "Your back is hurting - time for a stretch?"
- ✅ Suggest rest when pain mentioned multiple times
- ✅ Learn what triggers flares

**Trackable?** YES - timers + chat analysis

---

## TIER 3: ASPIRATIONAL (Hard to Track, High Value)

### 9. **What You're Stressed/Worried About**
**Why it matters:** Emotional support + context

**What you'd need:**
- Explicit mentions ("stressed about deadline")
- Tone analysis (frustrated language)
- Behavior changes (working late, skipping meals)

**How it would help:**
- ✅ "You seem stressed - want to talk about it?"
- ✅ Offer relevant help ("want me to reschedule non-critical meetings?")
- ✅ Suggest stress-relief activities
- ✅ Check in later ("how'd the presentation go?")

**Trackable?** PARTIALLY - from chat, but requires nuanced understanding

---

### 10. **Progress on Goals**
**Why it matters:** Celebrate wins, identify blockers

**What you'd need:**
- Explicit goals ("finish migration by Friday")
- Progress updates from chat
- Completion signals

**How it would help:**
- ✅ "Migration done! Great work. Take a break?"
- ✅ "Friday deadline coming up - still on track?"
- ✅ "You've been stuck on this for 2 days - need help?"
- ✅ Celebrate milestones

**Trackable?** HARD - requires goal tracking system

---

### 11. **What Help You Actually Need**
**Why it matters:** Proactive assistance > reactive

**What you'd need:**
- Recognize confused/stuck signals
- Understand what resources you need
- Know what you're likely to forget

**Examples:**
- "You're searching for X repeatedly - here's the link"
- "Last 3 times you did this, you needed Y"
- "It's Thursday - did you update your timesheet?"

**Trackable?** VERY HARD - requires deep context understanding

---

## TIER 4: PROBABLY NOT WORTH IT

### ❌ Social Battery
**Why skip:** No reliable way to measure, too personal

### ❌ Accomplishment Boost / Mood Details
**Why skip:** Too speculative, better to ask directly

### ❌ Decision Fatigue
**Why skip:** Can compute from ticket dismissals when needed

### ❌ Mental Clarity
**Why skip:** Only matters in extreme cases (drunk/medicated), which user will mention

---

## PRIORITY IMPLEMENTATION

**Implement first (High value, trackable now):**
1. ✅ Current context (what you're doing) - from chat/calendar
2. ✅ Physical need timers (already have)
3. ✅ Schedule pressure (already have)
4. ✅ Energy level (from sleep + time)
5. ✅ Suggestion acceptance patterns (from tickets)

**Implement next (High value, needs work):**
1. 🔨 Historical patterns (learn typical times for each activity)
2. 🔨 Pain escalation (track overdue durations more carefully)
3. 🔨 Work session analysis (focus depth from session length)

**Consider later (Hard, but valuable):**
1. 💡 Stress detection (from chat tone + behavior)
2. 💡 Goal tracking (explicit goal system)
3. 💡 Predictive needs (anticipate based on patterns)

**Skip entirely:**
1. ❌ Social battery, accomplishment boost, decision fatigue
2. ❌ Anything requiring psychological assessment
3. ❌ Anything that's speculative 90% of the time

---

## THE KEY PRINCIPLE

**"Track what enables decisions, not what sounds interesting."**

Every field should answer:
- **What decision does this enable?**
- **Can I measure/compute it reliably?**
- **Will it be useful >50% of the time?**

If not all three → don't track it.

---

## EXAMPLE: GOOD ASSISTANT BEHAVIOR

**9:00 AM:**
- *Sees: First coffee at 9 AM (pattern), no coffee yet today*
- *Suggests:* "Morning coffee time?"

**11:30 AM:**
- *Sees: Work session 2.5 hours, finger stretch overdue 30 min*
- *Suggests:* "Quick finger stretch? You've been at it for 2.5 hours"

**2:00 PM:**
- *Sees: Packed meeting afternoon, back-to-back starting at 2:30*
- *Suggests:* "Back-to-back meetings coming up - bathroom/water break?"

**6:00 PM:**
- *Sees: You usually walk dogs at 6 PM, haven't walked yet*
- *Suggests:* "Dog walk time?"

**9:00 PM:**
- *Sees: You mentioned "stressed about deadline" earlier*
- *Checks in:* "How'd the deadline crunch go?"

This is helpful because it's:
- ✅ Based on observable facts + learned patterns
- ✅ Timely (respects schedule)
- ✅ Relevant (not random)
- ✅ Respectful (doesn't interrupt deep work)
- ✅ Personal (remembers context)

No speculation about mood or social battery needed!
