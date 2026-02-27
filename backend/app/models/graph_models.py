"""Pydantic models for the Entity Graph API."""

from __future__ import annotations

from pydantic import BaseModel


class GraphNode(BaseModel):
    """A node in the entity graph."""

    id: str  # iri_hash
    label: str
    iri: str
    definition: str | None = None
    branch: str
    branch_color: str
    is_focus: bool = False
    is_branch_root: bool = False
    depth: int = 0  # negative = ancestor, positive = descendant


class GraphEdge(BaseModel):
    """An edge in the entity graph."""

    id: str  # "{source}->{target}:{type}"
    source: str  # iri_hash
    target: str  # iri_hash
    edge_type: str  # "subClassOf" | "seeAlso"
    label: str | None = None


class EntityGraphResponse(BaseModel):
    """Complete graph response."""

    focus_iri_hash: str
    focus_label: str
    focus_branch: str = ""
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False
    total_concept_count: int = 0


class HierarchyPathEntry(BaseModel):
    """An entry in a concept's hierarchy path."""

    label: str
    iri_hash: str


class ConceptDetail(BaseModel):
    """Extended concept detail with children, siblings, related, translations."""

    label: str
    iri: str
    iri_hash: str
    definition: str | None = None
    synonyms: list[str] = []
    branch: str = ""
    branch_color: str = ""
    hierarchy_path: list[HierarchyPathEntry] = []
    hierarchy_paths: list[list[HierarchyPathEntry]] = []
    all_parents: list[HierarchyPathEntry] = []
    children: list[HierarchyPathEntry] = []
    siblings: list[HierarchyPathEntry] = []
    related: list[HierarchyPathEntry] = []
    examples: list[str] = []
    translations: dict[str, str] = {}
