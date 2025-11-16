from typing import Dict, List
from app.assistant.entity_management.entity_cards import get_entity_card_for_prompt_injection
from app.models.base import get_session
from app.assistant.utils.logging_config import get_logger
import re
logger = get_logger(__name__)

class SimpleEntityMatcher:
    def __init__(self):
        self.entity_map: Dict[str, str] = {}  # alias -> entity_name
        self.entity_cards: Dict[str, str] = {}  # entity_name -> card_content
        self._loaded = False
    
    def load_entities(self):
        """Load all entity names and aliases into memory"""
        if self._loaded:
            return
            
        logger.info("Loading entity names and aliases into memory...")
        
        try:
            session = get_session()
            
            # Get all entity cards
            from app.assistant.entity_management.entity_cards import EntityCard
            all_cards = session.query(EntityCard).all()
            
            for card in all_cards:
                entity_name = card.entity_name.lower()
                # Get formatted card content using the existing function
                card_content = get_entity_card_for_prompt_injection(session, card.entity_name)
                
                # Store the entity card content
                self.entity_cards[entity_name] = card_content
                
                # Map the main entity name
                self.entity_map[entity_name] = entity_name
                
                # Map aliases
                if card.aliases:
                    for alias in card.aliases:
                        alias_lower = alias.lower()
                        self.entity_map[alias_lower] = entity_name
                
                # Map original aliases
                if card.original_aliases:
                    for alias in card.original_aliases:
                        alias_lower = alias.lower()
                        self.entity_map[alias_lower] = entity_name
            
            session.close()
            
            logger.info(f"Loaded {len(self.entity_cards)} entities with {len(self.entity_map)} total aliases")
            self._loaded = True
            
        except Exception as e:
            logger.error(f"Error loading entities: {e}")
            raise


    def find_entities_in_text(self, text: str) -> List[str]:
        """
        Return canonical entity names detected in `text`.
        - Any token overlap creates a candidate.
        - If the alias has 2+ words, require a phrase match with boundaries.
        """

        if not self._loaded:
            self.load_entities()
        if not text:
            return []

        def norm(s: str) -> str:
            s = s.lower()
            s = re.sub(r'[^a-z0-9\s]', ' ', s)
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        normalized_text = norm(text)
        text_words = set(normalized_text.split())

        # Phase 1: gather candidates by any token overlap
        candidates = []  # (entity_name, normalized_alias, word_count)
        for alias, entity_name in self.entity_map.items():
            na = norm(alias)
            if not na:
                continue
            alias_words = set(na.split())
            if alias_words & text_words:
                candidates.append((entity_name, na, len(alias_words)))

        # Phase 2: confirm multi-word aliases with phrase match
        found = set()
        # Prefer longer aliases first
        for entity_name, na, wc in sorted(candidates, key=lambda t: (-t[2], -len(t[1]))):
            if wc >= 2:
                if re.search(rf'\b{re.escape(na)}\b', normalized_text):
                    found.add(entity_name)
            else:
                found.add(entity_name)

        return list(found)

    
    def get_entity_card_content(self, entity_name: str) -> str:
        """Get the card content for an entity name"""
        if not self._loaded:
            self.load_entities()
        
        return self.entity_cards.get(entity_name.lower(), "")
    
    def should_inject_entity(self, entity_name: str, context_type: str) -> bool:
        """
        Determine if an entity should be injected.
        For now, always return True if we have a card for it.
        """
        if not self._loaded:
            self.load_entities()
        
        return entity_name.lower() in self.entity_cards

# Global instance
simple_entity_matcher = SimpleEntityMatcher()
