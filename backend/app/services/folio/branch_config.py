"""Static map of FOLIO branch names to display names and hex colors.

Keys match FOLIOTypes enum names from folio-python library.
"""

from __future__ import annotations

BRANCH_CONFIG: dict[str, dict[str, str]] = {
    "ACTOR_PLAYER": {"name": "Actor / Player", "color": "#1e6fa0"},
    "AREA_OF_LAW": {"name": "Area of Law", "color": "#1a5276"},
    "ASSET_TYPE": {"name": "Asset Type", "color": "#6b5600"},
    "COMMUNICATION_MODALITY": {"name": "Communication Modality", "color": "#7b4d93"},
    "CURRENCY": {"name": "Currency", "color": "#7a5a00"},
    "DATA_FORMAT": {"name": "Data Format", "color": "#4a5568"},
    "DOCUMENT_ARTIFACT": {"name": "Document / Artifact", "color": "#9c4a10"},
    "ENGAGEMENT_TERMS": {"name": "Engagement Attributes", "color": "#10613a"},
    "EVENT": {"name": "Event", "color": "#b91c1c"},
    "FINANCIAL_CONCEPTS": {"name": "Financial Concepts and Metrics", "color": "#6e4b00"},
    "FOLIO_TYPE": {"name": "FOLIO Type", "color": "#6b5c00"},
    "FORUMS_VENUES": {"name": "Forums and Venues", "color": "#7b2d8e"},
    "GOVERNMENTAL_BODY": {"name": "Governmental Body", "color": "#1a6091"},
    "INDUSTRY": {"name": "Industry and Market", "color": "#065550"},
    "LANGUAGE": {"name": "Language", "color": "#7a3b10"},
    "LEGAL_AUTHORITIES": {"name": "Legal Authorities", "color": "#8b1a1a"},
    "LEGAL_ENTITY": {"name": "Legal Entity", "color": "#085e40"},
    "LEGAL_USE_CASES": {"name": "Legal Use Cases", "color": "#4a3570"},
    "LOCATION": {"name": "Location", "color": "#105560"},
    "MATTER_NARRATIVE": {"name": "Matter Narrative", "color": "#6d3580"},
    "MATTER_NARRATIVE_FORMAT": {"name": "Matter Narrative Format", "color": "#1a6894"},
    "OBJECTIVES": {"name": "Objectives", "color": "#b03020"},
    "SERVICE": {"name": "Service", "color": "#065e4e"},
    "STANDARDS_COMPATIBILITY": {"name": "Standards Compatibility", "color": "#4a5a6a"},
    "STATUS": {"name": "Status", "color": "#864a08"},
    "SYSTEM_IDENTIFIERS": {"name": "System Identifiers", "color": "#3d4d5a"},
}

EXCLUDED_BRANCHES: frozenset[str] = frozenset({
    "Standards Compatibility",
    "ZZZ - SANDBOX: UNDER CONSTRUCTION",
})

# Lookup by display name -> branch key
_NAME_TO_KEY = {v["name"]: k for k, v in BRANCH_CONFIG.items()}


def get_branch_color(branch_name: str) -> str:
    """Get the hex color for a branch display name."""
    key = _NAME_TO_KEY.get(branch_name)
    if key:
        return BRANCH_CONFIG[key]["color"]
    return "#4a5568"  # fallback dark gray


def get_branch_display_name(key: str) -> str:
    """Get the display name for a branch key (e.g. ACTOR_PLAYER -> 'Actor / Player')."""
    cfg = BRANCH_CONFIG.get(key)
    return cfg["name"] if cfg else key
