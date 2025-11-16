# standardization_orchestrator.py
from typing import Dict, Optional, List, Tuple
from app.assistant.kg_core.standardization_manager import StandardizationManager
from app.assistant.utils.pydantic_classes import Message
import logging

logger = logging.getLogger(__name__)

ACCEPT_THRESHOLD = 0.90
REJECT_THRESHOLD = 0.70
CANDIDATE_TOP_K = 50
VERIFIER_K = 20

class StandardizationOrchestrator:
    """
    Orchestrates standardization with this policy:
      1) Always call the standardizer agent first to get a proposed standard label.
      2) Enforce bucket gates (node_type for labels, domain and range for edges).
      3) Try exact/alias match in canonical store for that bucket.
      4) If no hit, retrieve diverse candidates in-bucket, call verifier agent.
      5) Decide: map, create, or review. Never return uncataloged edge predicates.
    """

    def __init__(self, manager: Optional[StandardizationManager] = None):
        self.manager = manager or StandardizationManager()

    # =========================
    # NODE LABEL STANDARDIZATION
    # =========================
    def standardize_node(
            self,
            node: Dict,
            context_text: str,
            node_standardizer_agent
    ) -> Dict:
        """
        Generates semantic_label for node using standardizer agent.
        Taxonomy classification now handles label canonicalization.
        Required node fields: label, node_type.
        """
        raw_label = node.get("label", "") or ""
        node_type = node.get("node_type", "") or ""

        if not raw_label or not node_type:
            logger.warning("Node missing label or node_type, returning unchanged.")
            return node

        # Generate semantic_label using standardizer agent
        agent_in = {
            "node_label": raw_label,
            "node_type": node_type,
            "context_text": context_text
        }
        agent_out = node_standardizer_agent.action_handler(Message(agent_input=agent_in))
        agent_data = getattr(agent_out, "data", {}) or {}
        semantic_label = agent_data.get("semantic_label", "")
        
        # Return node with semantic_label attached
        # Label canonicalization is now handled by taxonomy classification
        logger.debug(f"Generated semantic_label '{semantic_label}' for node '{raw_label}'")
        return {
            **node,
            "semantic_label": semantic_label
        }

    # =========================
    # EDGE RELATION STANDARDIZATION
    # =========================
    def standardize_edge(
            self,
            edge: Dict,
            source_label: str,
            target_label: str,
            context_text: str,
            edge_standardizer_agent
    ) -> Dict:
        """
        Standardizes edge.label (relationship_type) using standardizer agent.
        Taxonomy classification now handles relationship canonicalization.
        Descriptor is passed through unchanged.
        """
        raw_pred = edge.get("label", "") or ""
        old_descriptor = edge.get("relationship_descriptor")  # Preserve old descriptor as fallback
        sentence = edge.get("sentence", "")

        # Resolve domain and range types if not provided
        domain_type = edge.get("domain_type") or self.manager.infer_domain_type(source_label)
        range_type = edge.get("range_type") or self.manager.infer_range_type(target_label)
        if not raw_pred or not domain_type or not range_type:
            logger.warning("Edge missing predicate or domain/range. Returning unchanged.")
            return edge

        # Pass old descriptor to agent as input for context
        agent_in = {
            "relationship_type": raw_pred,
            "domain_type": domain_type,
            "range_type": range_type,
            "source_label": source_label,
            "target_label": target_label,
            "sentence": sentence,
            "relationship_descriptor": old_descriptor or "",  # Provide context to agent
            "policy_notes": "Return predicate in snake_case, lowercase. ASCII only. Validate domain and range."
        }
        agent_out = edge_standardizer_agent.action_handler(Message(agent_input=agent_in))
        agent_data = getattr(agent_out, "data", {}) or {}
        standardized_pred = agent_data.get("relationship_type") or self.manager.to_snake_case(raw_pred)
        
        # Use agent's NEW descriptor output (not the old one!)
        new_descriptor = agent_data.get("relationship_descriptor") or old_descriptor or ""

        # Optional: Try registry remap for known variants (but don't block if not in registry)
        remapped = self.manager.remap_predicate_variant(standardized_pred)
        if remapped:
            # If registry has a preferred variant, use it
            standardized_pred = remapped
            logger.info(f"Remapped predicate via registry: {agent_data.get('relationship_type')} → {standardized_pred}")
        
        # Return edge with standardized relationship_type and NEW descriptor from agent
        logger.debug(f"Generated standardized relationship_type '{standardized_pred}' for edge '{raw_pred}'")
        return {
            **edge,
            "label": standardized_pred,
            "relationship_descriptor": new_descriptor  # Use agent's output!
        }

    def close(self):
        if self.manager:
            self.manager.close()

    # ===== helpers =====
    def _log_map(self, kind: str, raw: str, proposed: str, canon_id: str, method: str, conf: Optional[float] = None):
        logger.info(
            "standardize_map",
            extra={"kind": kind, "raw": raw, "proposed": proposed, "canon_id": canon_id, "method": method, "confidence": conf},
        )

    def _log_create(self, kind: str, raw: str, proposed: str, canon_id: str):
        logger.info(
            "standardize_create",
            extra={"kind": kind, "raw": raw, "proposed": proposed, "canon_id": canon_id},
        )

    def _queue_node_review(self, raw_label: str, proposed_label: str, node_type: str, cands: List[Dict], reason: str):
        self.manager.queue_review(
            item_type="label",
            proposal_text=proposed_label,
            bucket={"node_type": node_type},
            candidates=cands,
            reason=reason or "mid_band",
            provenance={"raw": raw_label},
        )

    def _queue_edge_review(
            self,
            raw_pred: str,
            proposed_pred: str,
            domain_type: str,
            range_type: str,
            source_label: str = "",
            target_label: str = "",
            sentence: str = "",
            reason: str = "",
    ):
        self.manager.queue_review(
            item_type="edge",
            proposal_text=proposed_pred,
            bucket={"domain_type": domain_type, "range_type": range_type},
            candidates=self.manager.get_edge_candidates(domain_type, range_type, proposed_pred, top_k=10, ensure_diverse=True),
            reason=reason or "mid_band",
            provenance={
                "raw": raw_pred,
                "source_label": source_label,
                "target_label": target_label,
                "sentence": sentence[:300],
            },
        )
