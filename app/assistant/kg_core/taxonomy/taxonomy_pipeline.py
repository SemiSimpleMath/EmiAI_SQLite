# taxonomy_pipeline.py
"""
Taxonomy Classification Pipeline - Separate from KG Ingestion

This pipeline runs AFTER nodes have been created in the knowledge graph.
It uses a proposer-critic architecture to classify nodes into the taxonomy hierarchy.

Architecture:
1. Proposer: Concept Extractor → Beam Search → Path Generator → Verifier
2. Critic: Reviews proposer's classification and makes final decision
3. Action Handler: Implements critic's decision (auto-implement, queue for review, etc.)

Usage:
    python taxonomy_pipeline.py --batch-size 100 --max-batches 10
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db_sqlite import Node
from app.assistant.kg_core.taxonomy.models import Taxonomy, NodeTaxonomyLink
from app.assistant.kg_core.taxonomy.manager import TaxonomyManager
from app.assistant.kg_core.taxonomy.orchestrator import TaxonomyOrchestrator
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_maintenance_logger

logger = get_maintenance_logger(__name__)


# ============================================================================
# DATABASE QUERIES
# ============================================================================

def get_unclassified_nodes(session: Session, limit: int = 100, node_type: Optional[str] = None) -> List[Node]:
    """
    Get nodes that don't have any taxonomy classification yet.
    
    Args:
        session: Database session
        limit: Maximum number of nodes to return
        node_type: Optional filter by node type (e.g., 'Entity', 'Event')
        
    Returns:
        List of unclassified Node objects
    """
    query = (
        select(Node)
        .outerjoin(NodeTaxonomyLink, Node.id == NodeTaxonomyLink.node_id)
        .where(NodeTaxonomyLink.node_id.is_(None))  # No taxonomy links exist
        .order_by(Node.created_at.asc())  # Oldest first
        .limit(limit)
    )
    
    if node_type:
        query = query.where(Node.node_type == node_type)
    
    results = session.execute(query).scalars().all()
    return results


def get_provisionally_classified_nodes(session: Session, limit: int = 100) -> List[Tuple[Node, NodeTaxonomyLink]]:
    """
    Get nodes with provisional (low-confidence) taxonomy classifications for re-review.
    
    Args:
        session: Database session
        limit: Maximum number of nodes to return
        
    Returns:
        List of tuples (Node, NodeTaxonomyLink)
    """
    query = (
        select(Node, NodeTaxonomyLink)
        .join(NodeTaxonomyLink, Node.id == NodeTaxonomyLink.node_id)
        .where(
            or_(
                NodeTaxonomyLink.source == 'probationary',
                NodeTaxonomyLink.source == 'placeholder',
                NodeTaxonomyLink.confidence < 0.7
            )
        )
        .order_by(NodeTaxonomyLink.confidence.asc())  # Lowest confidence first
        .limit(limit)
    )
    
    results = session.execute(query).all()
    return results


def get_classification_statistics(session: Session) -> Dict[str, int]:
    """
    Get statistics on node classification status.
    
    Returns:
        Dictionary with classification counts
    """
    total_nodes = session.execute(select(func.count(Node.id))).scalar()
    
    classified_nodes = session.execute(
        select(func.count(func.distinct(NodeTaxonomyLink.node_id)))
        .select_from(NodeTaxonomyLink)
    ).scalar()
    
    provisional_nodes = session.execute(
        select(func.count(func.distinct(NodeTaxonomyLink.node_id)))
        .select_from(NodeTaxonomyLink)
        .where(
            or_(
                NodeTaxonomyLink.source == 'probationary',
                NodeTaxonomyLink.source == 'placeholder',
                NodeTaxonomyLink.confidence < 0.7
            )
        )
    ).scalar()
    
    unclassified_nodes = total_nodes - classified_nodes
    
    return {
        'total_nodes': total_nodes,
        'classified_nodes': classified_nodes,
        'unclassified_nodes': unclassified_nodes,
        'provisional_nodes': provisional_nodes,
        'high_confidence_nodes': classified_nodes - provisional_nodes
    }


# ============================================================================
# TAXONOMY ASSIGNMENT & REVIEW QUEUES
# ============================================================================

def assign_taxonomy(
    node_id,  # SQLite: string UUID
    taxonomy_id: int,
    confidence: float,
    source: str,
    provisional: bool,
    session: Session,
    tax_manager: TaxonomyManager
) -> None:
    """
    Assign a taxonomy classification to a node.
    
    Args:
        node_id: Node ID to classify (SQLite: string UUID)
        taxonomy_id: Taxonomy type ID
        confidence: Classification confidence (0.0-1.0)
        source: Classification source ('matched', 'probationary', 'placeholder')
        provisional: Whether this is a provisional classification
        session: Database session
        tax_manager: TaxonomyManager instance
    """
    try:
        # Ensure node_id is a string for SQLite
        node_id = str(node_id)
        
        # Check if a link already exists
        existing_link = session.execute(
            select(NodeTaxonomyLink)
            .where(
                and_(
                    NodeTaxonomyLink.node_id == node_id,
                    NodeTaxonomyLink.taxonomy_id == taxonomy_id
                )
            )
        ).scalar_one_or_none()
        
        if existing_link:
            # Update existing link
            existing_link.confidence = max(existing_link.confidence, confidence)
            existing_link.count += 1
            existing_link.last_seen = datetime.utcnow()
            existing_link.source = source if confidence > existing_link.confidence else existing_link.source
            logger.info(f"Updated existing taxonomy link for node {node_id}")
        else:
            # Create new link
            new_link = NodeTaxonomyLink(
                node_id=node_id,
                taxonomy_id=taxonomy_id,
                confidence=confidence,
                source=source,
                count=1,
                last_seen=datetime.utcnow()
            )
            session.add(new_link)
            session.flush()  # Flush immediately to prevent autoflush conflicts
            logger.info(f"Created new taxonomy link for node {node_id}")
            
    except Exception as e:
        logger.error(f"Error assigning taxonomy to node {node_id}: {e}")
        # Rollback the session to clean state
        session.rollback()
        raise


def add_taxonomy_suggestion(
    parent_path: str,
    suggested_label: str,
    reasoning: str,
    example_node_id: int,
    confidence: float,
    session: Session
) -> None:
    """
    Add a suggestion for a new taxonomy type to the review queue.
    
    Args:
        parent_path: Parent taxonomy path (e.g., "entity > person")
        suggested_label: Suggested new child label (e.g., "software_developer")
        reasoning: Why this new type is needed
        example_node_id: Example node that would fit this type
        confidence: Confidence in this suggestion
        session: Database session
    """
    from app.assistant.kg_core.taxonomy.models import TaxonomySuggestions
    
    # First, check if this taxonomy type already exists in the main taxonomy
    try:
        tax_manager = TaxonomyManager(session)
        full_path = f"{parent_path} > {suggested_label}"
        
        # Check if the taxonomy path already exists
        existing_taxonomy = tax_manager.find_taxonomy_by_path(full_path)
        if existing_taxonomy:
            logger.info(f"Taxonomy type already exists, skipping suggestion: {full_path}")
            return
            
    except Exception as e:
        logger.warning(f"Could not check existing taxonomy types: {e}")
        # Continue with suggestion creation if we can't check taxonomy
    
    # Check if this suggestion already exists (any status)
    existing = session.execute(
        select(TaxonomySuggestions)
        .where(
            and_(
                TaxonomySuggestions.parent_path == parent_path,
                TaxonomySuggestions.suggested_label == suggested_label
            )
        )
    ).scalar_one_or_none()
    
    if existing:
        if existing.status == 'pending':
            # Update existing pending suggestion with new example
            existing.example_nodes.append({'node_id': str(example_node_id)})
            existing.confidence = max(existing.confidence, confidence)
            logger.info(f"Updated existing pending taxonomy suggestion: {parent_path} > {suggested_label}")
        elif existing.status == 'approved':
            # Already approved - don't create duplicate
            logger.info(f"Taxonomy suggestion already approved, skipping: {parent_path} > {suggested_label}")
            return
        elif existing.status == 'rejected':
            # Previously rejected - don't re-suggest
            logger.info(f"Taxonomy suggestion previously rejected, skipping: {parent_path} > {suggested_label}")
            return
    else:
        # Create new suggestion
        suggestion = TaxonomySuggestions(
            parent_path=parent_path,
            suggested_label=suggested_label,
            description=reasoning,
            example_nodes=[{'node_id': str(example_node_id)}],
            confidence=confidence,
            reasoning=reasoning,
            status='pending',
            created_at=datetime.utcnow()
        )
        session.add(suggestion)
        logger.info(f"Created new taxonomy suggestion: {parent_path} > {suggested_label}")


def queue_for_manual_review(
    node_id: int,
    proposed_path: str,
    validated_path: str,
    action: str,
    confidence: float,
    reasoning: str,
    session: Session
) -> None:
    """
    Queue a node classification for manual review.
    
    Args:
        node_id: Node ID
        proposed_path: Originally proposed path from proposer
        validated_path: Validated/corrected path from critic
        action: Critic action (CORRECT_PATH, REJECT)
        confidence: Classification confidence
        reasoning: Critic's reasoning
        session: Database session
    """
    from app.assistant.kg_core.taxonomy.models import NodeTaxonomyReviewQueue
    from sqlalchemy import select
    
    # Check if there's already a pending review for this node
    existing_reviews = session.execute(
        select(NodeTaxonomyReviewQueue)
        .where(
            NodeTaxonomyReviewQueue.node_id == node_id,
            NodeTaxonomyReviewQueue.status == 'pending'
        )
    ).scalars().all()
    
    if existing_reviews:
        # If there are multiple, log warning and update the first one
        if len(existing_reviews) > 1:
            logger.warning(f"Found {len(existing_reviews)} pending reviews for node {node_id}, updating the first one")
        
        existing_review = existing_reviews[0]
        # Update existing review with latest information
        existing_review.proposed_path = proposed_path
        existing_review.validated_path = validated_path
        existing_review.action = action
        existing_review.confidence = confidence
        existing_review.reasoning = reasoning
        logger.info(f"Updated existing review for node {node_id} (action: {action})")
    else:
        # Create new review
        review_item = NodeTaxonomyReviewQueue(
            node_id=node_id,
            proposed_path=proposed_path,
            validated_path=validated_path,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            status='pending',
            created_at=datetime.utcnow()
        )
        session.add(review_item)
        logger.info(f"Queued node {node_id} for manual review (action: {action})")


def correct_taxonomy_path(
    node: Node,
    critic_base_path: str,
    session: Session,
    tax_manager: TaxonomyManager,
    llm_top_paths: Optional[List[Dict]] = None  # NEW: Top 3 paths from LLM-guided descent
) -> Dict[str, Any]:
    """
    Use the path corrector agent to suggest an optimal taxonomy path.
    
    OPTIMIZATION: If llm_top_paths is provided, only search within the subtrees
    of the second-level categories from those paths (e.g., 'entity > artifact', 
    'entity > intangible'). This dramatically reduces search space and cost.
    
    Args:
        node: Node being classified
        llm_top_paths: Optional top 3 paths from LLM-guided descent
        critic_base_path: Root type to classify under (e.g., "entity", "event", "state")
        session: Database session
        tax_manager: TaxonomyManager instance
        
    Returns:
        Dictionary with corrected path and confidence
    """
    try:
        # Create path corrector agent
        path_corrector_agent = DI.agent_factory.create_agent("knowledge_graph_add::taxonomy_path_corrector")
        
        # Get the root taxonomy for the node type (entity, event, state, etc.)
        root_taxonomy_id = tax_manager.find_taxonomy_by_path(critic_base_path)
        if not root_taxonomy_id:
            logger.error(f"Root path not found: {critic_base_path}")
            return {
                'success': False,
                'error': f'Root path not found: {critic_base_path}'
            }
        
        # Fetch the actual taxonomy object
        root_taxonomy = session.get(Taxonomy, root_taxonomy_id)
        if not root_taxonomy:
            logger.error(f"Root taxonomy object not found for ID: {root_taxonomy_id}")
            return {
                'success': False,
                'error': f'Root taxonomy object not found for ID: {root_taxonomy_id}'
            }
        
        # NEW: OPTIMIZATION - Extract second-level categories from LLM top paths
        second_level_taxonomy_ids = []
        if llm_top_paths:
            # DEBUG: Print out the actual LLM-guided paths
            logger.info(f"📋 LLM-GUIDED TOP PATHS ({len(llm_top_paths)} paths):")
            for i, path_info in enumerate(llm_top_paths):
                path_ids = path_info.get('path_ids', [])
                # Convert path IDs to labels
                path_labels = []
                for pid in path_ids:
                    tax = session.get(Taxonomy, pid)
                    if tax:
                        path_labels.append(tax.label)
                path_str = " > ".join(path_labels)
                logger.info(f"   Path {i+1}: {path_str} (taxonomy_id={path_info.get('taxonomy_id')}, score={path_info.get('score', 0):.2f})")
            
            # CRITICAL: Only use paths if they match the current root type
            # (critic might have changed the root type from what proposer used)
            paths_match_root = False
            for path_info in llm_top_paths:
                path_ids = path_info.get('path_ids', [])
                if len(path_ids) >= 1:
                    # Check if first ID matches our root
                    if path_ids[0] == root_taxonomy.id:
                        paths_match_root = True
                        break
            
            if paths_match_root:
                logger.info(f"🚀 OPTIMIZATION: Using top {len(llm_top_paths)} paths to reduce search space")
                for path_info in llm_top_paths:
                    path_ids = path_info.get('path_ids', [])
                    # Extract second level (index 1, after root)
                    if len(path_ids) >= 2 and path_ids[0] == root_taxonomy.id:
                        second_level_id = path_ids[1]
                        if second_level_id not in second_level_taxonomy_ids:
                            second_level_taxonomy_ids.append(second_level_id)
                            second_level_tax = session.get(Taxonomy, second_level_id)
                            if second_level_tax:
                                logger.info(f"   📌 Will search: {root_taxonomy.label} > {second_level_tax.label}")
            else:
                logger.warning(f"⚠️  LLM paths don't match root type '{root_taxonomy.label}' (critic changed root), using full subtree")
        
        # Get full subtree structure for the entity type (with depth limit for safety)
        def get_full_subtree_structure(taxonomy_id, max_depth=5, current_depth=0):
            if current_depth >= max_depth:
                logger.warning(f"Max depth {max_depth} reached for taxonomy {taxonomy_id}")
                return None
                
            taxonomy = session.get(Taxonomy, taxonomy_id)
            if not taxonomy:
                return None
            
            children = session.query(Taxonomy).filter(Taxonomy.parent_id == taxonomy_id).all()
            subtree = {
                'id': taxonomy.id,
                'label': taxonomy.label,
                'description': taxonomy.description,
                'children': []
            }
            
            for child in children:
                child_subtree = get_full_subtree_structure(child.id, max_depth, current_depth + 1)
                if child_subtree:
                    subtree['children'].append(child_subtree)
            
            return subtree
        
        # Get the taxonomy structure
        logger.info(f"🔧 Getting taxonomy structure for root: {root_taxonomy.label} (ID: {root_taxonomy.id})")
        
        if second_level_taxonomy_ids:
            # OPTIMIZED: Only include relevant second-level subtrees
            logger.info(f"🚀 Building OPTIMIZED structure with {len(second_level_taxonomy_ids)} subtrees")
            taxonomy_structure = {
                'id': root_taxonomy.id,
                'label': root_taxonomy.label,
                'description': root_taxonomy.description,
                'children': []
            }
            
            for second_level_id in second_level_taxonomy_ids:
                subtree = get_full_subtree_structure(second_level_id)
                if subtree:
                    taxonomy_structure['children'].append(subtree)
            
            logger.info(f"   ✅ Optimized structure size: {len(json.dumps(taxonomy_structure))} characters")
        else:
            # FALLBACK: Use full subtree (old behavior)
            logger.info(f"⚠️  No LLM paths provided, using full subtree (expensive)")
            taxonomy_structure = get_full_subtree_structure(root_taxonomy.id)
        
        if not taxonomy_structure or not taxonomy_structure.get('children'):
            logger.error(f"Failed to get taxonomy structure for root: {root_taxonomy.label}")
            return {
                'success': False,
                'error': f'Failed to get taxonomy structure for root: {root_taxonomy.label}'
            }
        
        # Prepare input for path corrector
        input_data = {
            'node': {
                'label': node.label,
                'original_sentence': node.original_sentence or "",
                'node_type': node.node_type,
                'category': node.category or ""
            },
            'critic_base_path': critic_base_path,
            'taxonomy_structure': json.dumps(taxonomy_structure, indent=2)
        }
        
        logger.info(f"🔧 PATH CORRECTOR: Analyzing base path '{critic_base_path}' for node '{node.label}'")
        logger.info(f"   Taxonomy structure size: {len(json.dumps(taxonomy_structure))} characters")
        
        # Call path corrector agent
        logger.info(f"🔧 Calling path corrector agent...")
        response = path_corrector_agent.action_handler(Message(agent_input=input_data))
        logger.info(f"🔧 Path corrector agent response received")
        
        if not response or not response.data:
            logger.error("Path corrector agent returned invalid response")
            return {
                'success': False,
                'error': 'Invalid response from path corrector agent'
            }
        
        # response.data is a dict for structured output agents
        correction = response.data.get('correction')
        if not correction:
            logger.error(f"Path corrector response missing 'correction' field. Response data: {response.data}")
            return {
                'success': False,
                'error': 'Path corrector response missing correction field'
            }
        
        corrected_path = correction.get('corrected_path')
        confidence = correction.get('confidence')
        reasoning = correction.get('reasoning')
        
        logger.info(f"✅ PATH CORRECTED: '{corrected_path}' (confidence: {confidence:.2f})")
        logger.info(f"   Reasoning: {reasoning}")
        
        # Find taxonomy ID for corrected path
        corrected_taxonomy_id = tax_manager.find_taxonomy_by_path(corrected_path)
        
        return {
            'success': True,
            'corrected_path': corrected_path,
            'corrected_taxonomy_id': corrected_taxonomy_id,
            'confidence': confidence,
            'reasoning': reasoning
        }
        
    except Exception as e:
        logger.error(f"Error in path correction: {e}")
        return {
            'success': False,
            'error': str(e)
        }


# ============================================================================
# PROPOSER-CRITIC WORKFLOW
# ============================================================================

def classify_node_with_critic(
    node: Node,
    tax_orchestrator: TaxonomyOrchestrator,
    path_generator_agent,
    verifier_agent,
    branch_selector_agent,
    critic_agent,
    session: Session
) -> Dict[str, Any]:
    """
    Full proposer-critic classification workflow for a single node.
    
    Args:
        node: Node to classify
        tax_orchestrator: TaxonomyOrchestrator instance
        path_generator_agent: Agent to generate taxonomy paths
        verifier_agent: Agent to verify/select best path
        branch_selector_agent: Agent to select branches during search
        critic_agent: Agent to review and validate classification
        session: Database session
        
    Returns:
        Dictionary with classification result and critic decision
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"🎯 CLASSIFYING NODE: '{node.label}' (ID: {node.id}, Type: {node.node_type})")
    logger.info(f"{'='*80}")
    
    # STEP 1: PROPOSER - Make initial classification
    logger.info(f"📊 STEP 1: PROPOSER - Running taxonomy classification...")
    
    # Debug: Log the node data being passed
    node_data = {
        "label": node.label,
        "sentence": node.original_sentence or "",
        "node_type": node.node_type,
        "category": node.category
    }
    logger.info(f"🔍 DEBUG - Node data being classified:")
    logger.info(f"   Label: {node_data['label']}")
    logger.info(f"   Sentence: {node_data['sentence'][:100]}..." if len(node_data['sentence']) > 100 else f"   Sentence: {node_data['sentence']}")
    logger.info(f"   Type: {node_data['node_type']}")
    logger.info(f"   Category: {node_data['category']}")
    
    try:
        # Call orchestrator to get ALL candidate paths
        logger.info(f"🔍 DEBUG: Calling classify_node to get all candidates")
        result = tax_orchestrator.classify_node(
            node=node_data,
            path_generator_agent=path_generator_agent,
            verifier_agent=verifier_agent,
            branch_selector_agent=branch_selector_agent,
            session=session,
            return_top_paths=True  # Always request top paths
        )
        
        # Handle new format: dict with 'candidates' and 'llm_top_paths'
        if isinstance(result, dict) and 'candidates' in result:
            candidates = result['candidates']
            llm_top_paths = result.get('llm_top_paths', [])
            
            logger.info(f"🔍 DEBUG: Received {len(candidates)} candidates from orchestrator")
            logger.info(f"🔍 DEBUG: Received {len(llm_top_paths)} top paths for optimization")
            
            # For now, use the top candidate as the "proposed" path
            # The critic will evaluate all candidates
            if candidates:
                top_candidate = candidates[0]
                taxonomy_id = top_candidate['taxonomy_id']
                prop_confidence = top_candidate['score']
                prop_source = top_candidate['method']
            else:
                raise Exception("No candidates returned from orchestrator")
        else:
            # Old format fallback (should not happen)
            taxonomy_id, prop_confidence, prop_source = result
            candidates = [{'taxonomy_id': taxonomy_id, 'score': prop_confidence, 'method': prop_source}]
            llm_top_paths = getattr(tax_orchestrator, 'last_top_paths', [])
            logger.warning("⚠️  Orchestrator returned old format, using fallback")
        
        logger.info(f"🔍 DEBUG: Extracted {len(llm_top_paths)} top paths from LLM-guided descent")
        if llm_top_paths:
            for i, path_info in enumerate(llm_top_paths):
                path_ids = path_info.get('path_ids', [])
                logger.info(f"   Path {i+1}: {len(path_ids)} levels, taxonomy_id={path_info.get('taxonomy_id')}")
        else:
            logger.warning(f"⚠️  DEBUG: llm_top_paths is empty! This means last_top_paths was not set.")
        
        if not taxonomy_id:
            logger.warning(f"⚠️  Proposer failed to classify node '{node.label}'")
            return {
                'success': False,
                'reason': 'proposer_failed',
                'node_id': node.id
            }
        
        # Get the proposed path
        tax_manager = tax_orchestrator.manager
        proposed_path = tax_manager.get_taxonomy_path(taxonomy_id)
        proposed_path_str = ' > '.join(proposed_path)
        
        logger.info(f"✅ PROPOSER RESULT:")
        logger.info(f"   Path: {proposed_path_str}")
        logger.info(f"   Confidence: {prop_confidence:.2f}")
        logger.info(f"   Source: {prop_source}")
        
        # Determine proposal type
        if prop_source == 'probationary':
            proposal_type = 'NEW_CATEGORY_SUGGESTION'
        elif prop_source == 'placeholder':
            proposal_type = 'STOPPED_EARLY'
        else:
            proposal_type = 'FULL_PATH'
        
    except Exception as e:
        logger.error(f"❌ Proposer failed for node '{node.label}': {e}")
        return {
            'success': False,
            'reason': 'proposer_exception',
            'node_id': node.id,
            'error': str(e)
        }
    
    # STEP 2: CRITIC - Review the proposal
    logger.info(f"\n📋 STEP 2: CRITIC - Reviewing {len(candidates)} candidate paths...")
    
    try:
        # Format all candidates with their full paths and descriptions
        candidate_details = []
        for i, cand in enumerate(candidates, 1):
            cand_tax_id = cand['taxonomy_id']
            cand_path = cand['path']
            cand_score = cand['score']
            cand_method = cand['method']
            
            # Get path descriptions
            path_taxonomy_ids = []
            current_id = cand_tax_id
            while current_id:
                path_taxonomy_ids.insert(0, current_id)
                tax = session.get(Taxonomy, current_id)
                if tax and tax.parent_id:
                    current_id = tax.parent_id
                else:
                    break
            
            path_descriptions = []
            for tax_id in path_taxonomy_ids:
                tax = session.get(Taxonomy, tax_id)
                if tax:
                    desc = tax.description if tax.description else "Description unavailable"
                    path_descriptions.append(f"{tax.label} - {desc}")
            
            candidate_details.append({
                'rank': i,
                'path': cand_path,
                'taxonomy_id': cand_tax_id,
                'score': cand_score,
                'method': cand_method,
                'path_descriptions': "\n    ".join(path_descriptions)
            })
        
        # Call critic agent with ALL candidates
        critic_input = {
            'node_label': node.label,
            'node_category': node.category,
            'node_sentence': node.original_sentence or "",
            'node_type': node.node_type,
            'candidates': candidate_details  # NEW: All candidates
        }
        
        critic_response = critic_agent.action_handler(Message(agent_input=critic_input))
        critic_result = critic_response.data or {}
        
        decision = critic_result.get('decision')
        approved_rank = critic_result.get('approved_candidate_rank')
        critic_confidence = critic_result.get('confidence', 0.5)
        reasoning = critic_result.get('reasoning', '')
        
        logger.info(f"✅ CRITIC RESULT for node '{node.label}' (ID: {node.id}):")
        logger.info(f"   Decision: {decision}")
        if approved_rank:
            logger.info(f"   Approved Candidate: Rank {approved_rank}")
        logger.info(f"   Confidence: {critic_confidence:.2f}")
        logger.info(f"   Reasoning: {reasoning[:200]}...")
        
        # Handle critic's decision
        if decision == 'APPROVE' and approved_rank:
            # Use the approved candidate
            if 1 <= approved_rank <= len(candidates):
                approved_candidate = candidates[approved_rank - 1]  # Convert 1-based to 0-based
                taxonomy_id = approved_candidate['taxonomy_id']
                validated_path_str = approved_candidate['path']
                prop_source = approved_candidate['method']
                action = 'ACCEPT_AS_IS'
                logger.info(f"   ✅ Using approved candidate: {validated_path_str}")
            else:
                logger.error(f"   ❌ Invalid approved_rank: {approved_rank} (only {len(candidates)} candidates)")
                action = 'CORRECT_PATH'
                validated_path_str = candidates[0]['path']  # Fallback to top candidate
        elif decision == 'REJECT':
            action = 'CORRECT_PATH'
            validated_path_str = candidates[0]['path']  # Use top candidate as base for correction
            logger.info(f"🔧 CRITIC REJECTED all {len(candidates)} candidates")
        else:
            logger.warning(f"⚠️  Invalid critic response: decision={decision}, approved_rank={approved_rank}")
            action = 'CORRECT_PATH'
            validated_path_str = candidates[0]['path']
        
    except Exception as e:
        logger.error(f"❌ Critic failed for node '{node.label}': {e}")
        # Fallback: accept proposer's classification
        action = 'ACCEPT_AS_IS'
        validated_path_str = proposed_path_str
        critic_confidence = prop_confidence
        reasoning = f"Critic failed, accepting proposer result: {str(e)}"
    
    # STEP 3: ACTION HANDLER - Implement critic's decision
    logger.info(f"\n🎬 STEP 3: ACTION HANDLER - Implementing decision...")
    
    result = {
        'success': True,
        'node_id': node.id,
        'node_label': node.label,
        'proposed_path': proposed_path_str,
        'validated_path': validated_path_str,
        'action': action,
        'confidence': critic_confidence,
        'reasoning': reasoning
    }
    
    try:
        if action == 'ACCEPT_AS_IS':
            # Auto-implement: Use proposer's classification
            assign_taxonomy(
                node_id=node.id,
                taxonomy_id=taxonomy_id,
                confidence=critic_confidence,
                source=prop_source,
                provisional=False,
                session=session,
                tax_manager=tax_manager
            )
            logger.info(f"✅ AUTO-IMPLEMENTED: Accepted proposer classification")
            result['implemented'] = True
            result['implementation'] = 'auto'
        
        elif action == 'CORRECT_PATH':
            # Use path corrector to suggest optimal path from critic's base
            logger.info(f"🔧 Using path corrector for rejected path: {validated_path_str}")
            
            # Extract the root type from the proposed path (e.g., "entity" from "entity > creative_work > tv_show")
            root_type = validated_path_str.split(' > ')[0] if ' > ' in validated_path_str else validated_path_str
            logger.info(f"🔧 Extracted root type: '{root_type}' from path: '{validated_path_str}'")
            
            try:
                logger.info(f"🔍 DEBUG: Passing {len(llm_top_paths)} top paths to path corrector")
                correction_result = correct_taxonomy_path(
                    node=node,
                    critic_base_path=root_type,
                    session=session,
                    tax_manager=tax_manager,
                    llm_top_paths=llm_top_paths  # NEW: Pass top paths for optimization
                )
                logger.info(f"🔧 Path corrector result: {correction_result}")
            except Exception as e:
                logger.error(f"❌ Path corrector failed with exception: {e}")
                import traceback
                logger.error(f"❌ Traceback: {traceback.format_exc()}")
                raise
            
            if correction_result['success']:
                corrected_path = correction_result['corrected_path']
                corrected_taxonomy_id = correction_result['corrected_taxonomy_id']
                correction_confidence = correction_result['confidence']
                correction_reasoning = correction_result['reasoning']
                
                # Path corrector always suggests a path
                # If the path exists in taxonomy, use it; if not, create a suggestion
                
                if corrected_taxonomy_id:
                    # Path exists in taxonomy
                    if correction_confidence >= 0.8:
                        # High confidence - auto-implement
                        assign_taxonomy(
                            node_id=node.id,
                            taxonomy_id=corrected_taxonomy_id,
                            confidence=correction_confidence,
                            source='path_corrected',
                            provisional=False,
                            session=session,
                            tax_manager=tax_manager
                        )
                        logger.info(f"✅ AUTO-IMPLEMENTED: Path corrected to '{corrected_path}'")
                        result['implemented'] = True
                        result['implementation'] = 'path_corrected'
                    else:
                        # Low confidence - assign provisionally and queue for review
                        assign_taxonomy(
                            node_id=node.id,
                            taxonomy_id=corrected_taxonomy_id,
                            confidence=correction_confidence,
                            source='probationary',
                            provisional=True,
                            session=session,
                            tax_manager=tax_manager
                        )
                        queue_for_manual_review(
                            node_id=node.id,
                            proposed_path=proposed_path_str,
                            validated_path=corrected_path,
                            action=action,
                            confidence=correction_confidence,
                            reasoning=correction_reasoning,
                            session=session
                        )
                        logger.info(f"📋 QUEUED FOR REVIEW: Low-confidence path correction")
                        result['implemented'] = True
                        result['implementation'] = 'queued_for_review'
                else:
                    # Path doesn't exist - need to create new taxonomy category
                    # Extract parent path and new label
                    path_parts = corrected_path.split(' > ')
                    if len(path_parts) >= 2:
                        parent_path = ' > '.join(path_parts[:-1])
                        new_label = path_parts[-1]
                        
                        # Create taxonomy suggestion for human review
                        add_taxonomy_suggestion(
                            parent_path=parent_path,
                            suggested_label=new_label,
                            reasoning=f"Path corrector suggested new category: {correction_reasoning}",
                            example_node_id=node.id,
                            confidence=correction_confidence,
                            session=session
                        )
                        
                        # Assign to parent temporarily
                        parent_taxonomy_id = tax_manager.find_taxonomy_by_path(parent_path)
                        if parent_taxonomy_id:
                            assign_taxonomy(
                                node_id=node.id,
                                taxonomy_id=parent_taxonomy_id,
                                confidence=correction_confidence,
                                source='probationary',
                                provisional=True,
                                session=session,
                                tax_manager=tax_manager
                            )
                        
                        logger.info(f"📝 NEW CATEGORY SUGGESTED: {corrected_path}")
                        result['implemented'] = True
                        result['implementation'] = 'suggestion_added'
                    else:
                        # Invalid path format
                        logger.error(f"❌ Invalid corrected path format: {corrected_path}")
                        raise Exception(f"Invalid corrected path format: {corrected_path}")
            else:
                # Path corrector agent call failed - this is a critical error
                error_msg = f"Path corrector agent failed: {correction_result['error']}"
                logger.error(f"❌ CRITICAL: {error_msg}")
                raise Exception(error_msg)
        
        elif action == 'VALIDATE_INSERT':
            # Use path corrector to suggest optimal path from critic's base
            logger.info(f"🔧 Using path corrector for base path: {validated_path_str}")
            logger.info(f"🔍 DEBUG: Passing {len(llm_top_paths)} top paths to path corrector")
            
            correction_result = correct_taxonomy_path(
                node=node,
                critic_base_path=validated_path_str,
                session=session,
                tax_manager=tax_manager,
                llm_top_paths=llm_top_paths  # NEW: Pass top paths for optimization
            )
            
            if correction_result['success']:
                corrected_path = correction_result['corrected_path']
                corrected_taxonomy_id = correction_result['corrected_taxonomy_id']
                correction_confidence = correction_result['confidence']
                
                if corrected_taxonomy_id and correction_confidence >= 0.8:
                    # High confidence correction - auto-implement
                    assign_taxonomy(
                        node_id=node.id,
                        taxonomy_id=corrected_taxonomy_id,
                        confidence=correction_confidence,
                        source='path_corrected',
                        provisional=False,
                        session=session,
                        tax_manager=tax_manager
                    )
                    logger.info(f"✅ AUTO-IMPLEMENTED: Path corrected to '{corrected_path}'")
                    result['implemented'] = True
                    result['implementation'] = 'path_corrected'
                else:
                    # Low confidence or path not found - create suggestion
                    add_taxonomy_suggestion(
                        parent_path=validated_path_str,
                        suggested_label=suggested_new_label or 'unknown',
                        reasoning=f"Path corrector suggested: {corrected_path}. {correction_result['reasoning']}",
                        example_node_id=node.id,
                        confidence=correction_confidence,
                        session=session
                    )
                    # Assign to parent temporarily
                    assign_taxonomy(
                        node_id=node.id,
                        taxonomy_id=taxonomy_id,
                        confidence=critic_confidence,
                        source='probationary',
                        provisional=True,
                        session=session,
                        tax_manager=tax_manager
                    )
                    logger.info(f"📝 PATH CORRECTION SUGGESTED: {corrected_path}")
                    result['implemented'] = True
                    result['implementation'] = 'suggestion_added'
            else:
                # Path corrector failed - fall back to original suggestion
                logger.warning(f"Path corrector failed: {correction_result['error']}")
                add_taxonomy_suggestion(
                    parent_path=validated_path_str,
                    suggested_label=suggested_new_label or 'unknown',
                    reasoning=reasoning,
                    example_node_id=node.id,
                    confidence=critic_confidence,
                    session=session
                )
                # Assign to parent temporarily
                assign_taxonomy(
                    node_id=node.id,
                    taxonomy_id=taxonomy_id,
                    confidence=critic_confidence,
                    source='probationary',
                    provisional=True,
                    session=session,
                    tax_manager=tax_manager
                )
                logger.info(f"📝 FALLBACK SUGGESTION: {validated_path_str} > {suggested_new_label}")
                result['implemented'] = True
                result['implementation'] = 'suggestion_added'
        
        elif action == 'ACCEPT_NEW_CATEGORY':
            # Critic accepts the proposed new category - queue for review
            add_taxonomy_suggestion(
                parent_path=validated_path_str,
                suggested_label=suggested_new_label or 'unknown',
                reasoning=reasoning,
                example_node_id=node.id,
                confidence=critic_confidence,
                session=session
            )
            # Assign to parent temporarily
            assign_taxonomy(
                node_id=node.id,
                taxonomy_id=taxonomy_id,
                confidence=critic_confidence,
                source='probationary',
                provisional=True,
                session=session,
                tax_manager=tax_manager
            )
            logger.info(f"✅ NEW CATEGORY ACCEPTED: {validated_path_str} > {suggested_new_label}")
            result['implemented'] = True
            result['implementation'] = 'new_category_accepted'
        
        elif action == 'REJECT':
            # Doesn't fit anywhere - queue for manual review
            queue_for_manual_review(
                node_id=node.id,
                proposed_path=proposed_path_str,
                validated_path=validated_path_str,
                action=action,
                confidence=critic_confidence,
                reasoning=reasoning,
                session=session
            )
            # Assign to deepest valid ancestor as placeholder
            assign_taxonomy(
                node_id=node.id,
                taxonomy_id=taxonomy_id,
                confidence=0.5,
                source='placeholder',
                provisional=True,
                session=session,
                tax_manager=tax_manager
            )
            logger.info(f"🚨 REJECTED: Queued for manual review")
            result['implemented'] = True
            result['implementation'] = 'rejected_and_queued'
        
        else:
            logger.warning(f"⚠️  Unknown critic action: {action}")
            result['success'] = False
            result['reason'] = 'unknown_action'
    
    except Exception as e:
        logger.error(f"❌ Action handler failed for node '{node.label}': {e}")
        import traceback
        logger.error(f"❌ Traceback:\n{traceback.format_exc()}")
        
        # Don't silently swallow critical errors - re-raise them
        # Only catch and log non-critical errors
        if "Path corrector failed" in str(e) or "CRITICAL" in str(e):
            logger.error(f"❌ CRITICAL ERROR - Re-raising exception to stop execution")
            raise
        
        result['success'] = False
        result['reason'] = 'action_handler_exception'
        result['error'] = str(e)
    
    logger.info(f"{'='*80}\n")
    return result


# ============================================================================
# BATCH PROCESSING
# ============================================================================

def process_unclassified_nodes_batch(
    batch_size: int = 100,
    node_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a batch of unclassified nodes through the taxonomy pipeline.
    
    Args:
        batch_size: Number of nodes to process
        node_type: Optional filter by node type
        
    Returns:
        Dictionary with batch processing statistics
    """
    session = get_session()
    
    try:
        # Get unclassified nodes
        nodes = get_unclassified_nodes(session, limit=batch_size, node_type=node_type)
        
        if not nodes:
            logger.info("📭 No unclassified nodes found")
            return {
                'nodes_processed': 0,
                'success': True
            }
        
        logger.info(f"📦 Processing batch of {len(nodes)} unclassified nodes")
        
        # Initialize agents and orchestrator
        path_generator_agent = DI.agent_factory.create_agent("knowledge_graph_add::taxonomy_path_generator")
        verifier_agent = DI.agent_factory.create_agent("knowledge_graph_add::taxonomy_verifier")
        branch_selector_agent = DI.agent_factory.create_agent("knowledge_graph_add::taxonomy_branch_selector")
        critic_agent = DI.agent_factory.create_agent("knowledge_graph_add::taxonomy_critic")
        
        tax_manager = TaxonomyManager(session)
        tax_orchestrator = TaxonomyOrchestrator(tax_manager)
        
        # Process each node
        results = []
        for i, node in enumerate(nodes):
            logger.info(f"\n--- Processing node {i+1}/{len(nodes)} ---")
            
            result = classify_node_with_critic(
                node=node,
                tax_orchestrator=tax_orchestrator,
                path_generator_agent=path_generator_agent,
                verifier_agent=verifier_agent,
                branch_selector_agent=branch_selector_agent,
                critic_agent=critic_agent,
                session=session
                # NOTE: llm_top_paths is extracted INSIDE classify_node_with_critic after proposer runs
            )
            results.append(result)
            
            # Log the result for debugging
            logger.info(f"📊 Node '{node.label}' result: success={result.get('success')}, action={result.get('action')}, implemented={result.get('implemented')}")
            if not result.get('success'):
                logger.error(f"❌ Node '{node.label}' failed: {result.get('reason', 'unknown')}")
                if 'error' in result:
                    logger.error(f"❌ Error details: {result['error']}")
            
            # Commit every 10 nodes to avoid losing progress
            if (i + 1) % 10 == 0:
                session.commit()
                logger.info(f"✅ Committed progress: {i+1}/{len(nodes)} nodes")
        
        # Final commit
        session.commit()
        logger.info(f"✅ Batch complete: {len(nodes)} nodes processed")
        
        # Calculate statistics
        successful = sum(1 for r in results if r.get('success'))
        auto_implemented = sum(1 for r in results if r.get('implementation') == 'auto')
        auto_corrected = sum(1 for r in results if r.get('implementation') == 'auto_corrected')
        queued = sum(1 for r in results if r.get('implementation') == 'queued_for_review')
        suggestions = sum(1 for r in results if r.get('implementation') == 'suggestion_added')
        rejected = sum(1 for r in results if r.get('implementation') == 'rejected_and_queued')
        
        return {
            'nodes_processed': len(nodes),
            'successful': successful,
            'failed': len(nodes) - successful,
            'auto_implemented': auto_implemented,
            'auto_corrected': auto_corrected,
            'queued_for_review': queued,
            'suggestions_added': suggestions,
            'rejected': rejected,
            'success': True
        }
    
    except Exception as e:
        logger.error(f"❌ Batch processing failed: {e}")
        session.rollback()
        return {
            'nodes_processed': 0,
            'success': False,
            'error': str(e)
        }
    
    finally:
        session.close()


def process_all_unclassified_nodes(
    batch_size: int = 100,
    max_batches: int = 100,
    node_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process all unclassified nodes in batches.
    
    Args:
        batch_size: Number of nodes per batch
        max_batches: Maximum number of batches to process
        node_type: Optional filter by node type
        
    Returns:
        Dictionary with overall statistics
    """
    print(f"\n{'='*80}")
    print(f"🚀 TAXONOMY CLASSIFICATION PIPELINE")
    print(f"{'='*80}")
    print(f"   Batch size: {batch_size}")
    print(f"   Max batches: {max_batches}")
    print(f"   Node type filter: {node_type or 'all types'}")
    print(f"{'='*80}\n")
    
    # Get initial statistics
    session = get_session()
    try:
        stats = get_classification_statistics(session)
        print(f"📊 INITIAL STATE:")
        print(f"   Total nodes: {stats['total_nodes']}")
        print(f"   Classified: {stats['classified_nodes']} ({stats['high_confidence_nodes']} high confidence)")
        print(f"   Unclassified: {stats['unclassified_nodes']}")
        print(f"   Provisional: {stats['provisional_nodes']}")
        print(f"\n")
    finally:
        session.close()
    
    # Process in batches
    total_processed = 0
    total_auto_implemented = 0
    total_queued = 0
    total_suggestions = 0
    batches_completed = 0
    
    for batch_num in range(max_batches):
        print(f"\n{'='*80}")
        print(f"📦 BATCH #{batch_num + 1}")
        print(f"{'='*80}")
        
        result = process_unclassified_nodes_batch(batch_size=batch_size, node_type=node_type)
        
        if not result['success']:
            print(f"❌ Batch failed: {result.get('error')}")
            break
        
        if result['nodes_processed'] == 0:
            print("✅ All nodes have been classified!")
            break
        
        total_processed += result['nodes_processed']
        total_auto_implemented += result.get('auto_implemented', 0) + result.get('auto_corrected', 0)
        total_queued += result.get('queued_for_review', 0) + result.get('rejected', 0)
        total_suggestions += result.get('suggestions_added', 0)
        batches_completed += 1
        
        print(f"\n📊 BATCH SUMMARY:")
        print(f"   Processed: {result['nodes_processed']}")
        print(f"   Auto-implemented: {result.get('auto_implemented', 0)} accepted + {result.get('auto_corrected', 0)} corrected")
        print(f"   Queued for review: {result.get('queued_for_review', 0)}")
        print(f"   Suggestions added: {result.get('suggestions_added', 0)}")
        print(f"   Rejected: {result.get('rejected', 0)}")
        print(f"\n📈 CUMULATIVE TOTAL:")
        print(f"   Total processed: {total_processed}")
        print(f"   Total auto-implemented: {total_auto_implemented}")
        print(f"   Total queued: {total_queued}")
        print(f"   Total suggestions: {total_suggestions}")
    
    # Final statistics
    print(f"\n{'='*80}")
    print(f"🏁 PIPELINE COMPLETE")
    print(f"{'='*80}")
    print(f"   Batches completed: {batches_completed}")
    print(f"   Total nodes processed: {total_processed}")
    print(f"   Auto-implemented: {total_auto_implemented}")
    print(f"   Queued for review: {total_queued}")
    print(f"   New taxonomy suggestions: {total_suggestions}")
    
    session = get_session()
    try:
        final_stats = get_classification_statistics(session)
        print(f"\n📊 FINAL STATE:")
        print(f"   Total nodes: {final_stats['total_nodes']}")
        print(f"   Classified: {final_stats['classified_nodes']} ({final_stats['high_confidence_nodes']} high confidence)")
        print(f"   Unclassified: {final_stats['unclassified_nodes']}")
        print(f"   Provisional: {final_stats['provisional_nodes']}")
    finally:
        session.close()
    
    print(f"{'='*80}\n")
    
    return {
        'batches_completed': batches_completed,
        'total_processed': total_processed,
        'total_auto_implemented': total_auto_implemented,
        'total_queued': total_queued,
        'total_suggestions': total_suggestions
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Taxonomy Classification Pipeline')
    parser.add_argument('--batch-size', type=int, default=100, help='Number of nodes per batch')
    parser.add_argument('--max-batches', type=int, default=100, help='Maximum number of batches')
    parser.add_argument('--node-type', type=str, default=None, help='Filter by node type (Entity, Event, State, Goal, Concept)')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize system
    try:
        import app.assistant.tests.test_setup
        print("✅ System initialized successfully")
    except ImportError as e:
        print(f"⚠️  Could not import test setup: {e}")
    
    # Run pipeline
    process_all_unclassified_nodes(
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        node_type=args.node_type
    )

