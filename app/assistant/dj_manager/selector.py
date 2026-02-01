from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.dj_manager.query_utils import parse_search_query, build_search_query

logger = get_logger(__name__)


@dataclass
class ScoredCandidate:
    search_query: str
    reasoning: str
    title: str
    artist: str
    score: float
    probability: float = 0.0


class CandidateSelector:
    def __init__(self):
        self._backups: List[ScoredCandidate] = []

    def clear_backups(self) -> None:
        self._backups.clear()

    def has_backups(self) -> bool:
        return len(self._backups) > 0

    def backup_count(self) -> int:
        return len(self._backups)

    def pop_backup(self) -> Optional[ScoredCandidate]:
        if not self._backups:
            return None
        return self._backups.pop(0)

    def choose(self, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Returns:
          {
            "chosen": {"title": ..., "artist": ..., "search_query": ..., "reasoning": ...},
            "backups_count": int
          }

        Note:
        - Backup candidates are stored internally and can be retrieved via `pop_backup()`.
        """
        if not candidates:
            return None

        try:
            import random
            from app.models.played_songs import score_song_candidate
        except Exception as e:
            logger.exception(f"Candidate scoring unavailable: {e}")
            score_song_candidate = None

        scored: List[ScoredCandidate] = []
        for c in candidates:
            reasoning = c.get("reasoning", "")

            title = (c.get("title") or "").strip()
            artist = (c.get("artist") or "").strip()

            # Backward-compatible fallback if an older caller still passes search_query only.
            if (not title or not artist) and (c.get("search_query") or "").strip():
                t2, a2 = parse_search_query(str(c.get("search_query")))
                title = title or t2
                artist = artist or a2

            if not title:
                continue
            if not artist:
                artist = "Unknown"

            query = build_search_query(title, artist)

            score = 1.0
            if score_song_candidate:
                try:
                    score = float(score_song_candidate(title, artist))
                except Exception:
                    score = 1.0

            scored.append(
                ScoredCandidate(
                    search_query=query,
                    reasoning=reasoning,
                    title=title,
                    artist=artist,
                    score=score,
                )
            )

        if not scored:
            return None

        scores = [max(0.0, s.score) for s in scored]
        total = sum(scores)

        if total > 0:
            for s in scored:
                s.probability = (max(0.0, s.score) / total) * 100.0

        for i, s in enumerate(scored):
            logger.info(
                f"Candidate [{i+1}] {s.title[:35]:<35} by {s.artist[:20]:<20} "
                f"| score={s.score:.3f} | prob={s.probability:5.1f}%"
            )

        if total <= 0:
            chosen = scored[0]
        else:
            chosen = random.choices(scored, weights=scores, k=1)[0]

        remaining = [s for s in scored if s is not chosen]
        remaining.sort(key=lambda x: x.score, reverse=True)
        self._backups = remaining

        logger.info(
            f"Selected: '{chosen.title}' by {chosen.artist} (prob was {chosen.probability:.1f}%)"
        )

        return {
            "chosen": {
                "title": chosen.title,
                "artist": chosen.artist,
                "search_query": chosen.search_query,
                "reasoning": chosen.reasoning,
            },
            "backups_count": len(remaining),
        }
