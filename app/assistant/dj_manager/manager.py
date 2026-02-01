from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.ServiceLocator.service_locator import DI

from app.assistant.dj_manager.events import (
    DJEvent,
    Enable,
    Disable,
    SetContinuousMode,
    SetPauseOnAfk,
    TrackChanged,
    RequestPickAndQueue,
    PickSong,
    FrontendQueued,
    StopThread,
)
from app.assistant.dj_manager.socket_client import MusicSocketClient
from app.assistant.dj_manager.vibe import VibePlanner
from app.assistant.dj_manager.selector import CandidateSelector
from app.assistant.dj_manager.query_utils import parse_search_query, build_search_query

logger = get_logger(__name__)

PICK_DEBOUNCE_SECONDS = 5
QUEUE_RETRY_COOLDOWN_SECONDS = 20
MUSIC_CHAT_POLL_SECONDS = 2.5
MUSIC_CHAT_LOOKBACK_HOURS = 6

PICK_SONG_TIMEOUT_SECONDS = 90


class DJManager:
    """
    Thread-owned state machine:
    - External callers enqueue events
    - Only the DJ thread mutates internal state
    """

    def __init__(
            self,
            socket_client: Optional[MusicSocketClient] = None,
            vibe: Optional[VibePlanner] = None,
            selector: Optional[CandidateSelector] = None,
    ):
        self._q: "queue.Queue[DJEvent]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        self._socket = socket_client or MusicSocketClient()
        self._vibe = vibe or VibePlanner()
        self._selector = selector or CandidateSelector()

        self._enabled = False
        self._continuous_mode = False

        # Legacy fields kept for status compatibility only.
        # AFK pause/resume policy is now handled by the frontend (music_afk_state).
        self._pause_on_afk = True
        self._paused_by_dj = False

        self._next_song_queued = False
        self._pick_in_progress = False
        self._last_pick_utc: Optional[datetime] = None
        self._queue_retry_after_utc: Optional[datetime] = None

        self._current_track_id: Optional[str] = None

        # Music-chat trigger: if a new /music instruction arrives, trigger a fresh pick.
        self._last_seen_music_chat_utc: Optional[datetime] = None
        self._last_music_chat_poll_monotonic: float = 0.0
        self._last_music_chat_trigger_utc: Optional[datetime] = None

        self._stats = {
            "started_at": None,
            "last_action": None,
            "last_action_time": None,
        }

    # Public API, safe from any thread

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stats["started_at"] = datetime.now(timezone.utc).isoformat()

        self._thread = threading.Thread(target=self._loop, daemon=True, name="dj-manager")
        self._thread.start()
        logger.info("DJ Manager thread started")

    def stop(self) -> None:
        if not self._running:
            return
        self.enqueue(StopThread())
        if self._thread:
            self._thread.join(timeout=2)
        self._running = False
        logger.info("DJ Manager thread stopped")

    def enqueue(self, event: DJEvent) -> None:
        self._q.put(event)

    def enable(self) -> None:
        self.start()
        self.enqueue(Enable(continuous_mode=True))

    def disable(self) -> None:
        self.enqueue(Disable())

    def set_continuous_mode(self, enabled: bool) -> None:
        self.enqueue(SetContinuousMode(enabled=enabled))

    def set_pause_on_afk(self, enabled: bool) -> None:
        # AFK pause/resume policy is handled in the frontend now (via music_afk_state socket event).
        # Keep this method for API compatibility, but it is intentionally a no-op.
        return

    def on_track_changed(self, track: Optional[Dict[str, Any]]) -> None:
        self.enqueue(TrackChanged(track=track))

    def request_pick_and_queue(self, reason: str = "manual") -> None:
        self.enqueue(RequestPickAndQueue(reason=reason))

    def pick_song(self, reason: str = "manual", timeout_seconds: int = PICK_SONG_TIMEOUT_SECONDS) -> Optional[Dict[str, Any]]:
        """
        Pick a song (selection only) on the DJ thread and return the pick result.

        This is intentionally separated from playback. Call `play_song()` with the returned
        `search_query` afterwards.

        Note: this method requires DJ mode to be enabled; use `pick_song_once()` for a one-shot
        pick when DJ mode is disabled.
        """
        if not self._enabled:
            return None

        # Route selection through the DJ thread (thread-owned state).
        reply_q: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(maxsize=1)
        self.enqueue(PickSong(reason=reason, reply_queue=reply_q, allow_when_disabled=False))

        try:
            return reply_q.get(timeout=max(1, int(timeout_seconds)))
        except Exception:
            return None

    def pick_song_once(self, reason: str = "manual_once", timeout_seconds: int = PICK_SONG_TIMEOUT_SECONDS) -> Optional[Dict[str, Any]]:
        """
        Pick a song even when DJ mode is disabled (one-shot, no continuous mode required).

        This does NOT toggle enable/disable state; it only routes a pick through the DJ thread.
        """
        self.start()

        reply_q: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(maxsize=1)
        self.enqueue(PickSong(reason=reason, reply_queue=reply_q, allow_when_disabled=True))

        try:
            return reply_q.get(timeout=max(1, int(timeout_seconds)))
        except Exception:
            return None

    def on_frontend_queued(self, data: Dict[str, Any]) -> None:
        self.enqueue(FrontendQueued(data=data))

    def get_status(self) -> Dict[str, Any]:
        """
        Snapshot status without locking.
        If you need strict consistency, route this through the DJ thread.
        """
        thread_alive = self._thread.is_alive() if self._thread else False
        return {
            "enabled": self._enabled,
            "running": self._running,
            "thread_alive": thread_alive,
            "paused_by_dj": self._paused_by_dj,
            "continuous_mode": self._continuous_mode,
            "pause_on_afk": self._pause_on_afk,
            "next_song_queued": self._next_song_queued,
            "pick_in_progress": self._pick_in_progress,
            "backup_candidates": self._selector.backup_count() if self._selector else 0,
            "vibe_plan": self._vibe.get_plan_debug(),
            "stats": dict(self._stats),
        }

    def is_enabled(self) -> bool:
        return self._enabled

    def is_continuous_mode(self) -> bool:
        return self._continuous_mode

    def is_pick_in_progress(self) -> bool:
        return self._pick_in_progress

    # Direct playback commands (pass-through to socket client)

    def play(self) -> bool:
        return self._socket.send_command("play")

    def pause(self) -> bool:
        return self._socket.send_command("pause")

    def next_track(self) -> bool:
        return self._socket.send_command("next")

    def previous_track(self) -> bool:
        return self._socket.send_command("previous")

    def search_and_play(self, query: str) -> bool:
        return self._socket.send_command("search_and_play", {"query": query})

    def set_volume(self, volume: float) -> bool:
        return self._socket.send_command("set_volume", {"volume": max(0.0, min(1.0, volume))})

    def queue_next(self, query: str) -> bool:
        return self._socket.send_command("queue_next", {"query": query})

    def play_song(self, search_query: str, *, mode: str = "queue_next") -> bool:
        """
        Play/queue a song by query on the frontend player.

        Modes:
        - "queue_next": queue to play next (or play immediately if nothing playing)
        - "search_and_play": immediate search+play
        """
        q = (search_query or "").strip()
        if not q:
            return False
        if mode == "queue_next":
            return self.queue_next(q)
        if mode == "search_and_play":
            return self.search_and_play(q)
        raise ValueError(f"Unknown play mode: {mode}")

    def record_pick(self, *, title: str, artist: str, targets: Dict[str, Any], search_query: Optional[str] = None) -> None:
        """Record the chosen song to DB (no extra side effects)."""
        try:
            from app.models.played_songs import record_song_play
        except Exception as e:
            logger.exception(f"Could not import record_song_play: {e}")
            return

        try:
            t = (title or "").strip()
            a = (artist or "").strip() or "Unknown"
            if not t:
                return

            audio_targets = targets.get("audio_targets") if isinstance(targets, dict) else None
            q = (search_query or build_search_query(t, a)).strip()
            record_song_play(
                title=t,
                artist=a,
                search_query=q or None,
                audio_targets=audio_targets,
            )
            logger.info(f"Recorded at pick: {t} by {a}")
        except Exception as e:
            logger.exception(f"Failed to record pick: {e}")

    # Internal loop

    def _loop(self) -> None:
        while True:
            # Poll for new /music chat instructions (cheap; the LLM is the bottleneck anyway).
            # Only runs while DJ is enabled + continuous mode.
            self._poll_music_chat_once()

            try:
                event = self._q.get(timeout=0.25)
            except queue.Empty:
                continue

            if isinstance(event, StopThread):
                break

            try:
                self._handle_event(event)
            except Exception as e:
                logger.exception(f"Error handling DJ event {type(event).__name__}: {e}")

    def _poll_music_chat_once(self) -> None:
        """
        Periodically check for new music-scoped chat (e.g. /music commands) and trigger a pick.

        We intentionally avoid a global "new chat" event; this keeps the wake-up localized
        to the DJ subsystem and gives ~2-3s latency.
        """
        if not self._enabled or not self._continuous_mode:
            return

        now_mono = time.monotonic()
        if (now_mono - self._last_music_chat_poll_monotonic) < MUSIC_CHAT_POLL_SECONDS:
            return
        self._last_music_chat_poll_monotonic = now_mono

        try:
            from app.assistant.ServiceLocator.service_locator import DI

            now_utc = datetime.now(timezone.utc)
            # Start with a conservative lookback; once we've seen a message, use that as the cutoff.
            cutoff = self._last_seen_music_chat_utc or (now_utc - timedelta(hours=MUSIC_CHAT_LOOKBACK_HOURS))
            # Nudge back slightly so we don't miss messages with identical timestamps.
            cutoff = cutoff - timedelta(seconds=1)

            msgs = DI.global_blackboard.get_recent_chat_since_utc(
                cutoff,
                limit=20,
                content_limit=220,
                include_tags=["music"],
                include_command_scopes=["music"],
            )
            if not msgs:
                return

            newest_utc: Optional[datetime] = None
            newest_msg = None
            for m in msgs:
                ts = getattr(m, "timestamp", None)
                if ts is None:
                    continue
                if getattr(ts, "tzinfo", None) is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ts = ts.astimezone(timezone.utc)
                if newest_utc is None or ts > newest_utc:
                    newest_utc = ts
                    newest_msg = m

            if newest_utc is None:
                return

            prev = self._last_seen_music_chat_utc
            if prev is None or newest_utc > prev:
                self._last_seen_music_chat_utc = newest_utc

                # Debounce repeated triggers in a short window (e.g. multiple polls before a pick starts).
                if self._last_music_chat_trigger_utc and (now_utc - self._last_music_chat_trigger_utc).total_seconds() < 2.0:
                    return
                self._last_music_chat_trigger_utc = now_utc

                preview = ""
                try:
                    preview = (getattr(newest_msg, "content", "") or "").strip()
                except Exception:
                    preview = ""
                logger.info(f"DJ: new /music instruction detected -> triggering pick (preview='{preview[:120]}')")

                # Queue next song; do not interrupt current track.
                self.enqueue(RequestPickAndQueue(reason="music_chat"))

        except Exception as e:
            logger.debug(f"DJ: music chat poll failed: {e}", exc_info=True)

    # Event handling

    def _handle_event(self, event: DJEvent) -> None:
        if isinstance(event, Enable):
            self._enabled = True
            self._continuous_mode = bool(event.continuous_mode)
            self._next_song_queued = False
            self._selector.clear_backups()
            logger.info(f"DJ enabled (continuous_mode={self._continuous_mode})")

        elif isinstance(event, Disable):
            self._enabled = False
            self._continuous_mode = False
            self._next_song_queued = False
            self._pick_in_progress = False
            self._paused_by_dj = False
            self._vibe.clear()
            self._selector.clear_backups()
            logger.info("DJ disabled")

        elif isinstance(event, SetContinuousMode):
            self._continuous_mode = event.enabled
            if not event.enabled:
                self._next_song_queued = False
            logger.info(f"Continuous mode set to {self._continuous_mode}")

        elif isinstance(event, SetPauseOnAfk):
            # Legacy: ignore. AFK is handled by frontend.
            return

        elif isinstance(event, TrackChanged):
            self._on_track_changed(event.track)

        elif isinstance(event, RequestPickAndQueue):
            self._maybe_pick_and_queue(reason=event.reason)

        elif isinstance(event, PickSong):
            result: Optional[Dict[str, Any]] = None
            try:
                result = self._pick_song(debounce=False, allow_when_disabled=bool(getattr(event, "allow_when_disabled", False)))
            except Exception as e:
                logger.exception(f"Error picking song ({event.reason}): {e}")
                result = None

            try:
                if event.reply_queue is not None:
                    event.reply_queue.put(result)
            except Exception as e:
                logger.warning(f"Could not reply to PickSong request: {e}", exc_info=True)

        elif isinstance(event, FrontendQueued):
            title = event.data.get("title", "")
            artist = event.data.get("artist", "")
            logger.debug(f"Frontend confirmed queue: {title} by {artist}")

    # NOTE: AFK pause/resume is handled in the frontend now (music_afk_state socket event).

    # Music events: queueing and track changes

    def _on_track_changed(self, track: Optional[Dict[str, Any]]) -> None:
        if track:
            new_id = f"{track.get('title', '')}-{track.get('artist', '')}"
            if new_id != self._current_track_id:
                old_id = self._current_track_id
                self._current_track_id = new_id
                self._next_song_queued = False
                logger.info(f"Track changed: '{old_id}' to '{new_id}', queue flag reset")
        else:
            if self._current_track_id is not None:
                logger.info(f"Track ended (was: {self._current_track_id})")
                self._current_track_id = None
                self._next_song_queued = False

    # Pick flow

    def _maybe_pick_and_queue(self, reason: str) -> None:
        try:
            # Enforce queue retry cooldown if we recently failed to queue.
            if self._queue_retry_after_utc is not None:
                now_utc = datetime.now(timezone.utc)
                if now_utc < self._queue_retry_after_utc:
                    return

            # Pick requests from the frontend are authoritative; do not require "DJ enabled"
            # (that flag is for AFK automation / optional chat-driven behavior).
            picked = self._pick_song(debounce=True, allow_when_disabled=True)
            if not picked:
                self._schedule_queue_retry("no_pick_result")
                return

            if picked.get("skip_music", False):
                self._schedule_queue_retry("skip_music")
                return

            title = (picked.get("title") or "").strip()
            artist = (picked.get("artist") or "").strip()

            # Backward-compatible fallback
            if (not title or not artist) and (picked.get("search_query") or "").strip():
                t2, a2 = parse_search_query(str(picked.get("search_query")))
                title = title or t2
                artist = artist or a2

            if not title:
                self._schedule_queue_retry("empty_query")
                return

            targets = picked.get("targets", {}) if isinstance(picked.get("targets"), dict) else {}
            self.record_pick(title=title, artist=artist or "Unknown", targets=targets)

            ok = self.play_song(build_search_query(title, artist), mode="queue_next")
            if ok:
                self._next_song_queued = True
                self._queue_retry_after_utc = None
                self._stats["last_action"] = f"queue_next({reason})"
                self._stats["last_action_time"] = datetime.now(timezone.utc).isoformat()
            else:
                self._schedule_queue_retry("socket_failed")
        except Exception as e:
            logger.exception(f"Error during pick and queue: {e}")
            self._schedule_queue_retry("exception")
        finally:
            self._pick_in_progress = False

    def _schedule_queue_retry(self, why: str) -> None:
        self._next_song_queued = False
        self._queue_retry_after_utc = datetime.now(timezone.utc) + timedelta_seconds(QUEUE_RETRY_COOLDOWN_SECONDS)
        logger.info(f"Queue retry scheduled in {QUEUE_RETRY_COOLDOWN_SECONDS}s (reason: {why})")

    def _pick_song(self, *, debounce: bool, allow_when_disabled: bool = False) -> Optional[Dict[str, Any]]:
        """
        Flow:
        1) Ensure vibe plan fresh
        2) Compute targets
        3) Call dj_orchestrator for candidates
        4) Score and choose, store backups
        """
        if (not allow_when_disabled) and (not self._enabled):
            return None

        now_utc = datetime.now(timezone.utc)
        if debounce and self._last_pick_utc:
            elapsed = (now_utc - self._last_pick_utc).total_seconds()
            if elapsed < PICK_DEBOUNCE_SECONDS:
                logger.debug(f"Debounced pick ({elapsed:.1f}s since last)")
                return None

        if self._pick_in_progress:
            return None

        self._pick_in_progress = True
        self._last_pick_utc = now_utc

        try:
            from app.assistant.utils.pydantic_classes import Message
            from app.assistant.utils.time_utils import get_local_time
            from app.assistant.day_flow_manager.utils.context_sources import get_calendar_events_for_orchestrator
            from app.assistant.utils.chat_formatting import messages_to_chat_excerpts

            now_local = get_local_time()

            calendar_events = []
            recent_chat = []
            try:
                calendar_events = get_calendar_events_for_orchestrator()
            except Exception as e:
                logger.warning(f"Could not load calendar events for DJManager: {e}", exc_info=True)
            try:
                from app.assistant.ServiceLocator.service_locator import DI

                logger.info("DJ recent_chat(music) fetch starting")
                # Vibe check should receive ONLY music-scoped chat instructions.
                now_utc2 = datetime.now(timezone.utc)
                msgs = DI.global_blackboard.get_recent_chat_since_utc(
                    now_utc2 - timedelta(hours=3),
                    limit=50,
                    content_limit=220,
                    include_tags=["music"],
                    include_command_scopes=["music"],
                    )
                recent_chat = messages_to_chat_excerpts(msgs)

                # TEMP DEBUG: log what we fetched so we can confirm routing.
                try:
                    logger.info(f"DJ recent_chat(music) fetched={len(recent_chat)} (last 3h)")
                    for i, m in enumerate(recent_chat[:5]):
                        logger.info(f"DJ recent_chat(music)[{i+1}]: [{m.get('time_local')}] {m.get('sender')}: {m.get('content')}")
                except Exception as e:
                    logger.warning(f"DJ recent_chat(music) preview log failed: {e}", exc_info=True)
            except Exception as e:
                # Don't swallow: if this fails, /music routing will be invisible.
                logger.warning(f"DJ recent_chat(music) fetch failed: {e}")

            self._vibe.ensure_fresh_plan(calendar_events=calendar_events, recent_chat=recent_chat)
            targets = self._vibe.get_targets()

            recently_played = self._get_recently_played()
            last_played = None
            try:
                from app.models.played_songs import get_last_played_song

                last_played = get_last_played_song()
            except Exception:
                last_played = None

            # Pull 100 closest dataset matches, then choose 10 to show the DJ
            provided_songs = []
            try:
                from app.assistant.dj_manager.music_dataset import SqliteMusicDataset

                audio_targets = targets.get("audio_targets") if isinstance(targets, dict) else None
                if isinstance(audio_targets, dict):
                    music_filters = targets.get("music_filters") if isinstance(targets, dict) else None
                    dataset = SqliteMusicDataset()
                    seed = int(datetime.now(timezone.utc).timestamp() * 1000) & 0xFFFFFFFF
                    _pool_100, prompt_10 = dataset.sample_for_prompt(
                        audio_targets,
                        music_filters=music_filters,
                        match_pool_size=100,
                        # SQLite path: ask for a larger close-match base pool so the
                        # weighted sampling has enough variety after filters/recency.
                        base_pool_size=10000,
                        prompt_pick_count=10,
                        # Make favorite genres ~4x more likely among the close-match pool
                        boost_genres=[
                            "alt-rock",
                            "alternative",
                            "grunge",
                            "hard-rock",
                            "psych-rock",
                            "rock",
                            "metal",
                            "jazz",
                            "indie",
                            # "folk-rock" is not a genre in this dataset; closest equivalents:
                            "singer-songwriter",
                            "songwriter",
                            "acoustic",
                        ],
                        boost_factor=4.0,
                        # Hard constraints so energy/valence can't drift too far
                        max_energy_delta=5.0,
                        max_valence_delta=10.0,
                        seed=seed,
                    )
                    provided_songs = [
                        {
                            "title": s.track_name,
                            "artist": s.artist,
                            "genre": s.genre,
                            "sliders": s.sliders,
                            "prob_factor": getattr(s, "prob_factor", 1.0),
                        }
                        for s in prompt_10
                    ]
                    logger.info(f"Prepared provided_songs={len(provided_songs)} from sqlite dataset (seed={seed})")
                    for i, s in enumerate(provided_songs):
                        logger.info(
                            "ProvidedSongPrompt[%s]: %s (%s)",
                            i + 1,
                            build_search_query(s.get("title", ""), s.get("artist", "")),
                            s.get("genre"),
                            )
            except Exception as e:
                logger.warning(f"Could not prepare provided songs from dataset: {e}")

            agent_input = {
                "day_of_week": now_local.strftime("%A"),
                "vibe": targets,
                "recently_played": recently_played,
                "last_played": last_played,
                "provided_songs": provided_songs,
            }

            agent = DI.agent_factory.create_agent("dj_orchestrator")
            result = agent.action_handler(Message(agent_input=agent_input))

            data = None
            if hasattr(result, "data") and isinstance(result.data, dict):
                data = result.data
            elif isinstance(result, dict):
                data = result

            if not data:
                return None

            if data.get("skip_music", False):
                return {"skip_music": True, "skip_reason": data.get("skip_reason", "skip")}

            candidates = data.get("candidates", []) or []

            # Enforce contract: up to 5 provided + remainder new
            try:
                provided_set = set()
                for s in provided_songs:
                    t = (s.get("title") or "").strip()
                    a = (s.get("artist") or "").strip()
                    if t and a:
                        provided_set.add((t, a))

                provided = []
                new = []
                for c in candidates:
                    t = (c.get("title") or "").strip()
                    a = (c.get("artist") or "").strip()

                    if (not t or not a) and (c.get("search_query") or "").strip():
                        t2, a2 = parse_search_query(str(c.get("search_query")))
                        t = t or t2
                        a = a or a2

                    if not t:
                        continue
                    if not a:
                        a = "Unknown"

                    if (t, a) in provided_set:
                        provided.append({**c, "title": t, "artist": a, "source": "provided"})
                    else:
                        new.append({**c, "title": t, "artist": a, "source": "new"})

                desired_provided = min(5, len(provided_songs or []))

                # Fill provided slots from the provided list if needed
                if len(provided) < desired_provided and provided_songs:
                    already = set([(x.get("title"), x.get("artist")) for x in provided] + [(x.get("title"), x.get("artist")) for x in new])
                    for s in provided_songs:
                        t = (s.get("title") or "").strip()
                        a = (s.get("artist") or "").strip()
                        if not t or not a or (t, a) in already:
                            continue
                        provided.append(
                            {
                                "title": t,
                                "artist": a,
                                "reasoning": "Selected from provided list (server fill)",
                                "source": "provided",
                            }
                        )
                        if len(provided) >= desired_provided:
                            break

                provided = provided[:desired_provided]
                remaining_needed = max(0, 10 - len(provided))
                new = new[:remaining_needed]

                if provided_songs and desired_provided >= 5 and (len(provided) != 5 or len(new) != 5):
                    logger.warning(f"DJ contract mismatch after enforcement: provided={len(provided)} new={len(new)}")

                # Use enforced list if we have any provided songs at all
                if provided_songs and desired_provided > 0:
                    candidates = provided + new
                    data["candidates"] = candidates
            except Exception as e:
                logger.warning(f"Could not enforce provided/new contract: {e}")

            chosen_bundle = self._selector.choose(candidates=candidates)
            if not chosen_bundle:
                return None

            chosen = chosen_bundle["chosen"]
            logger.info(
                f"Picked: '{chosen.get('title', '')}' by {chosen.get('artist', '')} phase={targets.get('phase_note', 'n/a')}"
            )

            return {
                "title": chosen.get("title", ""),
                "artist": chosen.get("artist", ""),
                "reasoning": chosen.get("reasoning", ""),
                "skip_music": False,
                "targets": targets,
            }
        except Exception as e:
            logger.exception(f"DJ pick failed: {e}")
            return None
        finally:
            self._pick_in_progress = False

    def _get_recently_played(self) -> list:
        try:
            from app.models.played_songs import get_recently_played
            return get_recently_played(limit=10)
        except Exception as e:
            logger.debug(f"Could not get recently played: {e}")
            return []

    # Backup API, used when the frontend cannot find the chosen song

    def get_backup_song(self) -> Optional[Dict[str, Any]]:
        """
        IMPORTANT: This should be called from the DJ thread for strict correctness.
        If you call it from outside, route it through an event and a reply channel.
        """
        backup = self._selector.pop_backup()
        if not backup:
            logger.info("No backup candidates available")
            return None

        targets = self._vibe.get_targets()
        self.record_pick(title=backup.title, artist=backup.artist, targets=targets, search_query=backup.search_query)

        logger.info(f"Using backup: '{backup.title}' by {backup.artist} (score={backup.score:.3f})")
        return {"title": backup.title, "artist": backup.artist, "search_query": backup.search_query, "reasoning": backup.reasoning}


def timedelta_seconds(seconds: int) -> timedelta:
    return timedelta(seconds=int(seconds))
