
from typing import Dict, Tuple, Optional

# domain_type -> range_type for each predicate
PREDICATE_DOMAIN_RANGE: Dict[str, Tuple[str, str]] = {
    "works_for": ("Person", "Organization"),
    "works_in": ("Person", "Place"),
    "manages": ("Person", "Person"),
    "member_of": ("Person", "Group"),
    "part_of": ("Entity", "Entity"),
    "owns": ("Agent", "Thing"),
    "located_in": ("Entity", "Place"),
    "parent_of": ("Person", "Person"),
    "married_to": ("Person", "Person"),
    "sibling_of": ("Person", "Person"),
    "has_skill": ("Person", "Skill"),
    "has_goal": ("Agent", "Goal"),
    "participated_in": ("Agent", "Event"),
    "about_topic": ("Content", "Topic"),
    "causes": ("Event", "Event"),
}

# known variant remaps for fast-path normalization
PREDICATE_VARIANTS: Dict[str, str] = {
    "employed_by": "works_for",
    "works_at": "works_for",
    "employee_of": "works_for",
    "based_in": "located_in",
    "resides_in": "located_in",
    "lives_in": "located_in",
    "headquartered_in": "located_in",
    "manager_of": "manages",
    "supervises": "manages",
    "reports_to": "manages",  # inverse is virtual
    "owner_of": "owns",
    "owned_by": "owns",       # inverse is virtual
    "belongs_to_group": "member_of",
    "component_of": "part_of",
    "subset_of": "part_of",
}

def get_allowed_domain_range(pred: str) -> Optional[Tuple[str, str]]:
    return PREDICATE_DOMAIN_RANGE.get(pred)

def remap_variant(pred: str) -> Optional[str]:
    return PREDICATE_VARIANTS.get(pred)
