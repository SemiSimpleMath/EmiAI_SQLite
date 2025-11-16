"""
Seed script to populate essential core nodes (Jukka, Emi, and their relationship state) into the knowledge graph.

Run this manually after initializing the database:
    python -m app.assistant.kg_core.seed_core_nodes
"""

from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from datetime import datetime, timezone
from sentence_transformers import SentenceTransformer
import uuid


def seed_core_nodes():
    """Seed the database with Jukka, Emi, and their relationship state."""
    
    session = get_session()
    
    # Create embedding model
    print("Loading embedding model...")
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    def create_embedding(text):
        return embedding_model.encode(text).tolist()
    
    print("=" * 80)
    print("SEEDING CORE NODES AND RELATIONSHIP")
    print("=" * 80)
    
    try:
        # Relationship start date (August 2024)
        relationship_start = datetime(2024, 8, 1, tzinfo=timezone.utc)
        
        # --- Create Jukka node ---
        existing_jukka = session.query(Node).filter_by(label="Jukka", node_type="Entity").first()
        if existing_jukka:
            print("⚠️  Jukka node already exists, using existing...")
            jukka_node = existing_jukka
        else:
            jukka_node = Node(
                id=uuid.uuid4(),
                label="Jukka",
                node_type="Entity",
                aliases=["user", "Jukka Virtanen", "Jukka Tapio Virtanen", "Jukka T. Virtanen", "JTV", "J.T.V."],
                description="Jukka is the user.",
                category="person",
                semantic_label="Jukka",
                hash_tags=["user", "person", "self"],
                confidence=1.0,
                importance=1.0,
                source="seed",
                attributes={}
            )
            
            if jukka_node.label:
                jukka_node.label_embedding = create_embedding(jukka_node.label)
            if jukka_node.description:
                jukka_node.description_embedding = create_embedding(jukka_node.description)
            
            session.add(jukka_node)
            session.commit()
            print(f"✅ Created Jukka node (ID: {str(jukka_node.id)[:8]}...)")
        
        # Classify Jukka in taxonomy
        from app.assistant.kg_core.taxonomy.models import Taxonomy
        from app.assistant.kg_core.taxonomy.manager import TaxonomyManager
        tax_manager = TaxonomyManager(session)
        
        # Find "user" taxonomy type (entity > person > user)
        user_tax = session.query(Taxonomy).filter_by(label="user").first()
        
        if user_tax:
            tax_manager.link_node_to_taxonomy(
                node_id=str(jukka_node.id),
                taxonomy_id=user_tax.id,
                confidence=1.0,
                source="seed"
            )
            print(f"   📋 Classified Jukka as: user (entity > person > user)")
        else:
            print(f"   ⚠️  'user' taxonomy not found - run seed_taxonomy_minimal_curated.py first")
        
        # --- Create Emi node ---
        existing_emi = session.query(Node).filter_by(label="Emi", node_type="Entity").first()
        if existing_emi:
            print("⚠️  Emi node already exists, using existing...")
            emi_node = existing_emi
        else:
            emi_node = Node(
                id=uuid.uuid4(),
                label="Emi",
                node_type="Entity",
                aliases=["Emi AI", "Emi_AI", "assistant", "AI Assistant"],
                description="Jukka's AI assistant.",
                category="AI",
                semantic_label="Emi",
                hash_tags=["assistant", "ai", "ai_assistant"],
                confidence=1.0,
                importance=1.0,
                source="seed",
                attributes={}
            )
            
            if emi_node.label:
                emi_node.label_embedding = create_embedding(emi_node.label)
            if emi_node.description:
                emi_node.description_embedding = create_embedding(emi_node.description)
            
            session.add(emi_node)
            session.commit()
            print(f"✅ Created Emi node (ID: {str(emi_node.id)[:8]}...)")
        
        # Classify Emi in taxonomy
        assistant_tax = session.query(Taxonomy).filter_by(label="assistant").first()
        
        if assistant_tax:
            tax_manager.link_node_to_taxonomy(
                node_id=str(emi_node.id),
                taxonomy_id=assistant_tax.id,
                confidence=1.0,
                source="seed"
            )
            print(f"   📋 Classified Emi as: assistant (entity > person > assistant)")
        else:
            print(f"   ⚠️  'assistant' taxonomy not found - run seed_taxonomy_minimal_curated.py first")
        
        # --- Create State node ---
        existing_state = session.query(Node).filter_by(label="Emi Assists Jukka", node_type="State").first()
        if existing_state:
            print("⚠️  Relationship state already exists, skipping...")
            state_node = existing_state
        else:
            state_node = Node(
                id=uuid.uuid4(),
                label="Emi Assists Jukka",
                node_type="State",
                description="Emi serves as Jukka's AI assistant, helping with tasks, information, and conversation.",
                category="relationship",
                semantic_label="Assistant Relationship",
                hash_tags=["assistant_relationship", "ai_human_interaction", "ongoing"],
                start_date=relationship_start,
                start_date_confidence="confirmed",
                end_date=None,
                valid_during="August 2024 - present (ongoing)",
                confidence=1.0,
                importance=1.0,
                source="seed",
                attributes={}
            )
            
            if state_node.label:
                state_node.label_embedding = create_embedding(state_node.label)
            if state_node.description:
                state_node.description_embedding = create_embedding(state_node.description)
            
            session.add(state_node)
            session.commit()
            print(f"✅ Created State node (ID: {str(state_node.id)[:8]}...)")
        
        # Classify State in taxonomy (relationship_state)
        relationship_state_tax = session.query(Taxonomy).filter_by(label="relationship_state").first()
        
        if relationship_state_tax:
            tax_manager.link_node_to_taxonomy(
                node_id=str(state_node.id),
                taxonomy_id=relationship_state_tax.id,
                confidence=1.0,
                source="seed"
            )
            print(f"   📋 Classified state as: relationship_state")
        else:
            print(f"   ⚠️  'relationship_state' taxonomy not found")
        
        # --- Create edges ---
        existing_jukka_edge = session.query(Edge).filter_by(
            source_id=jukka_node.id, target_id=state_node.id, relationship_type="Participant"
        ).first()
        
        if not existing_jukka_edge:
            jukka_edge = Edge(
                id=uuid.uuid4(),
                source_id=jukka_node.id,
                target_id=state_node.id,
                relationship_type="is_assisted",
                relationship_descriptor="user being assisted",
                sentence="Jukka is the user being assisted in this relationship.",
                attributes={"role": "user", "role_type": "recipient"},
                confidence=1.0,
                importance=1.0,
                source="seed",
                original_message_timestamp=relationship_start
            )
            
            triplet = f"{jukka_node.label} Participant {state_node.label}"
            jukka_edge.label_embedding = create_embedding(triplet)
            if jukka_edge.sentence:
                jukka_edge.sentence_embedding = create_embedding(jukka_edge.sentence)
            
            session.add(jukka_edge)
            print(f"✅ Created edge: Jukka --[Participant]--> State")
        else:
            print("⚠️  Jukka participant edge already exists")
        
        existing_emi_edge = session.query(Edge).filter_by(
            source_id=emi_node.id, target_id=state_node.id, relationship_type="Participant"
        ).first()
        
        if not existing_emi_edge:
            emi_edge = Edge(
                id=uuid.uuid4(),
                source_id=emi_node.id,
                target_id=state_node.id,
                relationship_type="assists",
                relationship_descriptor="AI assistant providing help",
                sentence="Emi is the AI assistant providing assistance in this relationship.",
                attributes={"role": "assistant", "role_type": "provider"},
                confidence=1.0,
                importance=1.0,
                source="seed",
                original_message_timestamp=relationship_start
            )
            
            triplet = f"{emi_node.label} Participant {state_node.label}"
            emi_edge.label_embedding = create_embedding(triplet)
            if emi_edge.sentence:
                emi_edge.sentence_embedding = create_embedding(emi_edge.sentence)
            
            session.add(emi_edge)
            print(f"✅ Created edge: Emi --[Participant]--> State")
        else:
            print("⚠️  Emi participant edge already exists")
        
        session.commit()
        print("=" * 80)
        print("✅ CORE NODES SEEDING COMPLETE")
        print("=" * 80)
        print(f"📊 Summary:")
        print(f"   - 2 Entity nodes (Jukka, Emi)")
        print(f"   - 1 State node (Emi Assists Jukka)")
        print(f"   - 2 Edges (connecting participants to state)")
        print(f"   - Relationship start: August 2024 (ongoing)")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error seeding core nodes: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_core_nodes()

