# ASCII only.

from typing import Dict, Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.models.base import get_session  # keep your existing loader
from app.assistant.kg_core.predicate_registry import get_allowed_domain_range, remap_variant
from app.assistant.kg_core.models_standardization import (
    LabelCanon, LabelAlias, EdgeCanon, EdgeAlias, ReviewQueue
)
import logging
import re
import json

logger = logging.getLogger(__name__)

def to_title_case(label: str) -> str:
    # Keep acronyms as-is when all caps. Basic title casing otherwise.
    parts = re.split(r"\s+", label.strip())
    out = []
    for p in parts:
        if len(p) <= 4 and p.isupper():
            out.append(p)
        else:
            out.append(p[:1].upper() + p[1:].lower())
    return " ".join(out)

def norm_lower(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def to_snake_case(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9\s_]", " ", text)
    s = re.sub(r"[-\s]+", "_", s.strip())
    s = re.sub(r"_+", "_", s)
    return s.lower()

class StandardizationManager:
    """
    Canonical and alias store with candidate retrieval.

    Important integration note:
    - This manager does not call agents.
    - Call the STANDARDIZER AGENT in your orchestrator BEFORE you use the lookups below,
      to produce a proposed label or predicate.
    - If exact or alias lookups miss, call get_*_candidates(...) and then run the VERIFIER AGENT
      in your orchestrator to pick a canonical or decide to create a new one.
    - Only create canonicals after the verifier decision or a safe auto-create rule.
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()

    # ===== label canonical lookups =====
    def find_label_canonical_exact(self, node_type: str, label_text: str) -> Optional[Dict]:
        """
        Orchestrator flow:
        1) Run STANDARDIZER AGENT first to get 'proposed' Title Case label for this node_type.
        2) Call this method with node_type and the proposed label.
        3) If hit, you can stop. If miss, try find_label_alias(...) next.
        """
        t = to_title_case(label_text)
        row = self.session.query(LabelCanon).filter(
            and_(LabelCanon.node_type == node_type,
                 LabelCanon.lowercase_norm == norm_lower(t))
        ).first()
        return self._canon_label_to_dict(row) if row else None

    def find_label_alias(self, node_type: str, alias_text: str) -> Optional[Dict]:
        """
        Orchestrator flow:
        - Call after find_label_canonical_exact(...) misses.
        - If this hits, map and stop.
        - If this also misses, call get_label_candidates(...) and then run the VERIFIER AGENT.
        """
        a = self.session.query(LabelAlias, LabelCanon).join(
            LabelCanon, LabelCanon.id == LabelAlias.canon_id
        ).filter(
            and_(LabelAlias.node_type == node_type,
                 LabelAlias.alias_text == alias_text)
        ).first()
        if not a:
            return None
        alias, canon = a
        return {"canon_id": canon.id, "canonical_label_titlecase": canon.canonical_label_titlecase}

    def get_label_canonical_by_id(self, canon_id: str) -> Optional[Dict]:
        return self._canon_label_to_dict(
            self.session.query(LabelCanon).filter(LabelCanon.id == canon_id).first()
        ) or None

    def get_label_candidates(self, node_type: str, text: str, top_k: int = 50, ensure_diverse: bool = True) -> List[Dict]:
        """
        Orchestrator flow:
        - Use ONLY within the exact node_type bucket.
        - After exact and alias miss, call this to retrieve candidates for the VERIFIER AGENT.
        - Pass the returned list (top K, or trimmed to 20 with diversity) to the verifier.
        - Based on verifier decision:
            * Map to target_id -> then call record_label_alias(...) for the raw text.
            * Create new canonical -> then call create_label_canonical(...).
            * Mid band -> call queue_review(...).
        """
        # Simple lexical ranking using lowercased trigram-like ordering.
        # Replace with pg_trgm and pgvector in production.
        t = norm_lower(text)
        rows = self.session.query(LabelCanon).filter(LabelCanon.node_type == node_type).all()
        scored = []
        for r in rows:
            lex = self._lexical_score(t, r.lowercase_norm)
            # No embedding here for brevity. Set semantic to lex.
            sem = lex
            s = 0.5 * lex + 0.5 * sem
            scored.append((s, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = [{"id": r.id, "canonical_label_titlecase": r.canonical_label_titlecase, "score": s} for s, r in scored[:top_k]]
        if ensure_diverse:
            out = self._simple_diversity(out, k=min(20, len(out)))
        return out

    def create_label_canonical(self, node_type: str, label_text: str, source: str, context: str) -> Tuple[str, str]:
        """
        Orchestrator flow:
        - Call ONLY after the VERIFIER AGENT says create_new with sufficient confidence,
          and after a near-duplicate collision check in-bucket fails to find a close match.
        """
        t = to_title_case(label_text)
        row = LabelCanon(
            node_type=node_type,
            canonical_label_titlecase=t,
            lowercase_norm=norm_lower(t),
            embedding=None,
            notes=f"source={source} ctx={context[:120]}"
        )
        self.session.add(row)
        self.session.commit()
        return row.id, row.canonical_label_titlecase

    def record_label_alias(self, raw_text: str, canon_id: str, node_type: str, method: str, confidence: float, provenance: Dict):
        """
        Orchestrator flow:
        - Call after a mapping is accepted, either:
            * exact or alias hit, method='exact' or 'alias_hit'
            * VERIFIER AGENT accepted, method='verifier_accept'
            * auto create, method='auto_create'
        """
        a = self.session.query(LabelAlias).filter(
            and_(LabelAlias.node_type == node_type,
                 LabelAlias.alias_text == raw_text,
                 LabelAlias.canon_id == canon_id)
        ).first()
        if a:
            a.usage_count += 1
        else:
            a = LabelAlias(
                node_type=node_type,
                alias_text=raw_text,
                canon_id=canon_id,
                method=method,
                confidence=int(round(confidence * 100)),
                source=provenance.get("source"),
                example_context=provenance.get("context"),
                agent_reasoning=provenance.get("reason"),
            )
            self.session.add(a)
        self.session.commit()

    def find_label_near_collision(self, node_type: str, text: str, threshold: float) -> Optional[Dict]:
        """
        Orchestrator flow:
        - Before create_label_canonical(...), call this.
        - If any near collision is found above threshold, DO NOT create new. Queue review instead.
        """
        t = norm_lower(text)
        rows = self.session.query(LabelCanon).filter(LabelCanon.node_type == node_type).all()
        for r in rows:
            if self._lexical_score(t, r.lowercase_norm) >= threshold:
                return self._canon_label_to_dict(r)
        return None

    # ===== edge canonical lookups =====
    def remap_predicate_variant(self, text: str) -> Optional[str]:
        """
        Orchestrator flow:
        - Run STANDARDIZER AGENT first to get proposed snake_case predicate.
        - Optionally call this to fast-map common variants before DB work.
        - Then validate domain and range with predicate_domain_range_ok(...).
        """
        return remap_variant(text)

    def predicate_domain_range_ok(self, predicate: str, domain_type: str, range_type: str) -> bool:
        """
        Orchestrator flow:
        - Call this immediately after you have a proposed predicate to enforce the bucket gate.
        - If false, either remap with remap_predicate_variant(...) or queue review.
        """
        allowed = get_allowed_domain_range(predicate)
        return bool(allowed and allowed[0] == domain_type and allowed[1] == range_type)

    def find_edge_canonical_exact(self, domain_type: str, range_type: str, predicate_text: str) -> Optional[Dict]:
        """
        Orchestrator flow:
        1) After standardizer and domain/range validation, try exact canonical.
        2) If miss, try find_edge_alias(...).
        3) If miss, call get_edge_candidates(...) and then run the VERIFIER AGENT.
        """
        snake = to_snake_case(predicate_text)
        row = self.session.query(EdgeCanon).filter(
            and_(EdgeCanon.domain_type == domain_type,
                 EdgeCanon.range_type == range_type,
                 EdgeCanon.edge_type == snake)
        ).first()
        return self._canon_edge_to_dict(row) if row else None

    def find_edge_alias(self, domain_type: str, range_type: str, alias_text: str) -> Optional[Dict]:
        """
        Orchestrator flow:
        - Call after find_edge_canonical_exact(...) misses.
        - If this hits, map and stop.
        - If miss, call get_edge_candidates(...) then run the VERIFIER AGENT.
        """
        a = self.session.query(EdgeAlias, EdgeCanon).join(
            EdgeCanon, EdgeCanon.id == EdgeAlias.canon_id
        ).filter(
            and_(EdgeAlias.domain_type == domain_type,
                 EdgeAlias.range_type == range_type,
                 EdgeAlias.raw_text == to_snake_case(alias_text))
        ).first()
        if not a:
            return None
        alias, canon = a
        return {"canon_id": canon.id, "edge_type": canon.edge_type}

    def get_edge_canonical_by_id(self, canon_id: str) -> Optional[Dict]:
        row = self.session.query(EdgeCanon).filter(EdgeCanon.id == canon_id).first
        row = row() if callable(row) else None
        return self._canon_edge_to_dict(row) if row else None

    def get_edge_candidates(self, domain_type: str, range_type: str, text: str, top_k: int = 50, ensure_diverse: bool = True) -> List[Dict]:
        """
        Orchestrator flow:
        - Use ONLY within the exact domain_type and range_type bucket.
        - After exact and alias miss, call this to get candidates for the VERIFIER AGENT.
        - Pass the top N (for example 20) to the verifier along with the proposal.
        """
        s = to_snake_case(text)
        rows = self.session.query(EdgeCanon).filter(
            and_(EdgeCanon.domain_type == domain_type,
                 EdgeCanon.range_type == range_type)
        ).all()
        scored = []
        for r in rows:
            lex = self._lexical_score(s, r.edge_type)
            sem = lex
            score = 0.5 * lex + 0.5 * sem
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = [{"id": r.id, "edge_type": r.edge_type, "score": sc} for sc, r in scored[:top_k]]
        if ensure_diverse:
            out = self._simple_diversity(out, k=min(20, len(out)))
        return out

    def create_edge_canonical(self, domain_type: str, range_type: str, predicate_text: str, source: str, context: str) -> Tuple[str, str]:
        """
        Orchestrator flow:
        - Call ONLY after the VERIFIER AGENT says create_new with sufficient confidence,
          and after a near-duplicate collision check in-bucket fails to find a close match.
        - Never return an uncataloged predicate from the orchestrator.
        """
        snake = to_snake_case(predicate_text)
        row = EdgeCanon(
            domain_type=domain_type,
            range_type=range_type,
            edge_type=snake,
            edge_type_embedding=None,
            is_symmetric=False,
            created_by=source,
        )
        self.session.add(row)
        self.session.commit()
        return row.id, row.edge_type

    def record_edge_alias(self, raw_text: str, canon_id: str, domain_type: str, range_type: str, method: str, confidence: float, provenance: Dict):
        """
        Orchestrator flow:
        - Call after any accepted mapping:
            * exact or alias hit
            * VERIFIER AGENT accepted
            * auto create
        """
        a = self.session.query(EdgeAlias).filter(
            and_(EdgeAlias.domain_type == domain_type,
                 EdgeAlias.range_type == range_type,
                 EdgeAlias.raw_text == to_snake_case(raw_text),
                 EdgeAlias.canon_id == canon_id)
        ).first()
        if a:
            # Already exists, skip
            return
        else:
            a = EdgeAlias(
                canon_id=canon_id,
                raw_text=to_snake_case(raw_text),
                domain_type=domain_type,
                range_type=range_type,
                method=method,
                confidence=int(round(confidence * 100)),
                provenance=provenance
            )
            self.session.add(a)
        self.session.commit()

    def find_edge_near_collision(self, domain_type: str, range_type: str, text: str, threshold: float) -> Optional[Dict]:
        """
        Orchestrator flow:
        - Before create_edge_canonical(...), call this.
        - If any near collision is found above threshold, DO NOT create new. Queue review instead.
        """
        snake = to_snake_case(text)
        rows = self.session.query(EdgeCanon).filter(
            and_(EdgeCanon.domain_type == domain_type,
                 EdgeCanon.range_type == range_type)
        ).all()
        for r in rows:
            if self._lexical_score(snake, r.edge_type) >= threshold:
                return self._canon_edge_to_dict(r)
        return None

    # ===== review queue =====
    def queue_review(self, item_type: str, proposal_text: str, bucket: Dict, candidates: List[Dict], reason: str, provenance: Dict):
        """
        Orchestrator flow:
        - Use when the VERIFIER AGENT returns mid confidence, or when collision checks block create.
        - A reviewer will later resolve and write alias or create canonical.
        """
        row = ReviewQueue(
            item_type=item_type,
            proposal_text=proposal_text,
            bucket_json=bucket,
            candidates_json=candidates,
            scores_json=None,
            reason=reason,
        )
        self.session.add(row)
        self.session.commit()

    # ===== light utilities =====
    def infer_domain_type(self, source_label: str) -> Optional[str]:
        # Optional: implement if you have typed nodes and want to derive domain from source_label.
        return None

    def infer_range_type(self, target_label: str) -> Optional[str]:
        # Optional: implement if you have typed nodes and want to derive range from target_label.
        return None

    def close(self):
        if self.session:
            self.session.close()

    # ===== private helpers =====
    def _canon_label_to_dict(self, r: LabelCanon) -> Dict:
        return {
            "id": r.id,
            "node_type": r.node_type,
            "canonical_label_titlecase": r.canonical_label_titlecase,
            "lowercase_norm": r.lowercase_norm,
            "status": r.status,
        }

    def _canon_edge_to_dict(self, r: EdgeCanon) -> Dict:
        return {
            "id": r.id,
            "domain_type": r.domain_type,
            "range_type": r.range_type,
            "edge_type": r.edge_type,
            "status": r.status,
        }

    def _lexical_score(self, a: str, b: str) -> float:
        # Simple token overlap as a stand-in. Replace with pg_trgm similarity.
        ta = set(a.split("_" if "_" in a else " "))
        tb = set(b.split("_" if "_" in b else " "))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def _simple_diversity(self, items: List[Dict], k: int) -> List[Dict]:
        # Greedy MMR-like selection using token overlap as distance.
        if len(items) <= k:
            return items
        selected = [items[0]]
        cand = items[1:]
        while len(selected) < k and cand:
            best = None
            best_score = -1.0
            for c in cand:
                key_c = c.get("edge_type", c.get("canonical_label_titlecase", "")).lower()
                min_overlap = 1.0
                for s in selected:
                    key_s = s.get("edge_type", s.get("canonical_label_titlecase", "")).lower()
                    min_overlap = min(min_overlap, self._lexical_score(key_c, key_s))
                own = c.get("score", 0.0)
                score = 0.7 * own + 0.3 * (1.0 - min_overlap)
                if score > best_score:
                    best = c
                    best_score = score
            selected.append(best)
            cand = [x for x in cand if x is not best]
        return selected
