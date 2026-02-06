# DJ Manager Architecture

## Overview

The DJ Manager is an intelligent music automation system integrated into Emi. It uses Apple MusicKit for playback and leverages Emi's existing context pipeline (mood, activity, calendar) to pick contextually appropriate music.

## Components

### 1. Music Manager (`app/assistant/music_manager/`)

**Purpose:** Handles Apple MusicKit authentication and playback state tracking.

**Key Files:**
- `music_manager.py` - JWT token generation, playback state

**Responsibilities:**
- Generate Apple MusicKit developer tokens 
- Cache tokens with automatic refresh
- Track current playback state (is_playing, current_track, progress)

**Credentials:**
- Private key: `musickit/AuthKey_XAX3GKSV7M.p8`
- Key ID: `XAX3GKSV7M`
- Team ID: `65WK889FT4`

---

### 2. DJ Manager (`app/assistant/dj_manager/`)

**Purpose:** Orchestrates automatic music playback with context awareness.

**Key Files:**
- `manager.py` - Main DJ state machine (`DJManager`) running on a dedicated thread
- `socket_client.py` - Backend → frontend command sender (`music_command`)
- `vibe.py` - Vibe plan management (calls `vibe_check` agent) and exposes `audio_targets` (0-100 sliders)
- `music_dataset.py` - Curated dataset sampling for “provided songs” close to current targets
- `selector.py` - Candidate scoring/selection + backup list
- `query_utils.py` - Shared parsing helpers (e.g., `parse_search_query`)
- `events.py` - Event dataclasses for the DJ thread state machine

**Features:**
- **AFK Detection:** Pauses music when user goes AFK, resumes when they return
- **Context-Aware Picking:** Uses LLM agents + curated dataset to select songs based on vibe targets and context
- **Play History:** Tracks played songs to avoid repetition
- **WebSocket Control:** Sends commands to frontend player

**Thread Model:**
- Runs on its own daemon thread
- Polls AFK state every 3 seconds (when enabled)
- Enabled/disabled via UI toggle

**Key Methods:**
```python
enable()              # Start DJ mode
disable()             # Stop DJ mode
pick_song()           # Select a song (no playback)
play_song(query)      # Send playback/queue command to frontend
play() / pause()      # Direct playback control
search_and_play(q)    # Search and play a specific query
```

---

### 3. DJ Orchestrator Agent (`app/assistant/agents/dj_orchestrator/`)

**Purpose:** LLM-based song selection using user context.

**Files:**
- `config.yaml` - Agent configuration, context items
- `agent_form.py` - Output schema (Pydantic)
- `prompts/system.j2` - DJ personality and guidelines
- `prompts/user.j2` - Context template

**Input Context (from resource files):**
| Context | Source | Purpose |
|---------|--------|---------|
| `resource_health_inference_output` | Health stage | Mood, energy, stress |
| `resource_daily_context_generator_output` | Context stage | Current activity |
| `resource_afk_statistics_output` | AFK monitor | Computer presence |
| `calendar_events` | Calendar | Upcoming meetings |
| `recently_played` | played_songs table | Avoid repetition |
| `resource_music_preferences` | Resource file | User's taste |

**Output Schema (current):**
```python
class AgentForm(BaseModel):
    candidates: List[SongCandidate]  # Exactly 10: prefer 5 provided + 5 new
    vibe_interpretation: str
    skip_music: bool
    skip_reason: Optional[str]
```

---

### 4. Music Preferences (`resources/resource_music_preferences.md`)

**Purpose:** User's music taste guidelines for the DJ agent.

**Sections:**
- Favorite genres and artists
- Activity-based rules (coding → jazz, gaming → metal)
- Time-of-day preferences
- Things to avoid

**Example:**
```markdown
### Gaming
- **Project Zomboid**: Heavy metal - Metallica, Slayer, Pantera
- **Relaxing games**: Alternative rock, indie

### Working/Coding
- Jazz - John Coltrane, Miles Davis (great for deep focus)
- Fela Kuti / Afrobeat (hypnotic, good for flow state)
```

---

### 5. Played Songs Database (`app/models/played_songs.py`)

**Purpose:** Track play history to avoid repetition.

**Table Schema:**
| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| title | String | Song title |
| artist | String | Artist name |
| search_query | String | Query used to find song |
| first_played_utc | DateTime | First play timestamp |
| last_played_utc | DateTime | Most recent play |
| play_count_today | Integer | Plays today |
| play_count_week | Integer | Plays this week |
| play_count_month | Integer | Plays this month |
| play_count_year | Integer | Plays this year |
| play_count_all_time | Integer | Total plays |

**Auto-Reset:** Period counts reset automatically when crossing day/week/month/year boundaries.

---

### 6. Frontend (`app/static/js/music_player.js`, `app/templates/music.html`)

**Purpose:** Apple MusicKit integration and UI.

**Features:**
- MusicKit initialization and authorization
- Playback controls (play, pause, next, previous)
- Search and play
- DJ mode toggle
- "Let DJ Pick" button
- "Fetch My Music Taste" - pulls listening history from Apple

**WebSocket Events:**
| Event | Direction | Purpose |
|-------|-----------|---------|
| `music_command` | Backend → Frontend | Play, pause, search_and_play |
| `music_state_update` | Frontend → Backend | Playback state sync |
| `music_pick_request` | Frontend → Backend | Frontend asks DJ to pick/queue next song (continuous mode) |
| `music_backup_request` | Frontend → Backend | Ask for a backup when a query yields no Apple results |
| `music_song_queued` | Frontend → Backend | Confirmation that the frontend queued a song |

---

## Data Flow

### Manual "Let DJ Pick"

```
User clicks "Let DJ Pick"
    ↓
POST /api/music/dj/pick
    ↓
DJManager.pick_and_play_song()  (enqueues a pick request)
    ↓
DJ thread handles RequestPickAndQueue
    ↓
_pick_song_via_agent():
  - vibe_check → creates/refreshes a vibe plan with audio_targets (0-100 sliders)
  - curated dataset → picks "provided songs" close to targets
  - dj_orchestrator → returns 10 candidates (5 provided + 5 new when available)
  - score + weighted-random choose (penalize repeats via played_songs)
    ↓
Record pick immediately (played_songs DB)
    ↓
Backend emits music_command: queue_next({query})
    ↓
Frontend receives, searches Apple Music, queues next (or plays immediately if nothing playing)
    ↓
Music plays!
```

### Continuous Mode (auto-queue next)

Important: **Queue timing is frontend-owned** to avoid double-queueing and excessive Apple API traffic.
The music tab checks its own queue/remaining-time and requests picks when needed.

```
Frontend (every ~5s):
    ↓
checkQueueNeedsSongs()
    ↓
socket emit "music_pick_request"
    ↓
Backend enqueues RequestPickAndQueue (DJ thread)
    ↓
DJ thread picks and emits "music_command: queue_next"
    ↓
Frontend queues the song and emits "music_song_queued"
```

If Apple search returns no matches for the chosen query:

```
Frontend emits "music_backup_request" (includes failed_query)
    ↓
Backend pops a backup candidate and emits "music_command: queue_next" again
```

### AFK Auto-Pause/Resume

```
DJManager thread (every 3s):
    ↓
Poll DI.afk_monitor.get_computer_activity()
    ↓
Detect transition: active → AFK
    ↓
If music was playing: emit "pause" command
    ↓
Set _paused_by_dj = True
    ↓
... user returns ...
    ↓
Detect transition: AFK → active
    ↓
If _paused_by_dj: emit "play" command
    ↓
Music resumes!
```

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/music` | GET | Music player UI |
| `/api/music/token` | GET | Get MusicKit JWT token |
| `/api/music/state` | GET/POST | Get/update playback state |
| `/api/music/dj/status` | GET | DJ manager status |
| `/api/music/dj/enable` | POST | Enable DJ mode |
| `/api/music/dj/disable` | POST | Disable DJ mode |
| `/api/music/dj/pick` | POST | Have DJ pick a song |
| `/api/music/dj/command` | POST | Send playback command |

---

## Future Enhancements

1. **Continuous Mode:** Auto-pick next song when current ends (monitor playback progress)
2. **Meeting Detection:** Auto-stop music before meetings
3. **Queue Management:** Pre-queue songs before current ends
4. **Mood Learning:** Track which songs user skips to refine preferences
5. **Playlist Generation:** Create playlists for activities/moods
