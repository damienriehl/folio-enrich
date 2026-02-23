"""Rich concept detail and entity graph building for FOLIO concepts.

Provides lookup_concept_detail() for full concept info (children, siblings,
translations, hierarchy path, examples) and build_entity_graph() for BFS
graph exploration.
"""

from __future__ import annotations

import logging

from app.models.graph_models import (
    ConceptDetail,
    EntityGraphResponse,
    GraphEdge,
    GraphNode,
    HierarchyPathEntry,
)
from app.services.folio.branch_config import get_branch_color

logger = logging.getLogger(__name__)


def _extract_iri_hash(iri: str) -> str:
    """Extract the hash portion from a full FOLIO IRI."""
    return iri.rsplit("/", 1)[-1]


def _get_branch_for_class(folio, iri_hash: str, branch_root_iris: dict[str, str], cache: dict[str, str]) -> str:
    """Walk parent chain to find which branch a class belongs to. Cached."""
    if iri_hash in cache:
        return cache[iri_hash]

    if iri_hash in branch_root_iris:
        cache[iri_hash] = branch_root_iris[iri_hash]
        return branch_root_iris[iri_hash]

    owl_class = folio[iri_hash]
    if not owl_class or not owl_class.sub_class_of:
        cache[iri_hash] = "Unknown"
        return "Unknown"

    visited: set[str] = {iri_hash}
    current_parents = owl_class.sub_class_of

    for _ in range(20):
        if not current_parents:
            break
        next_parents: list[str] = []
        for parent_iri in current_parents:
            parent_hash = _extract_iri_hash(parent_iri)
            if parent_hash in visited:
                continue
            visited.add(parent_hash)
            if parent_hash in branch_root_iris:
                branch_name = branch_root_iris[parent_hash]
                cache[iri_hash] = branch_name
                return branch_name
            parent_class = folio[parent_hash]
            if parent_class and parent_class.sub_class_of:
                next_parents.extend(parent_class.sub_class_of)
        current_parents = next_parents

    cache[iri_hash] = "Unknown"
    return "Unknown"


def _init_branch_roots(folio) -> dict[str, str]:
    """Build mapping of branch root IRI hashes to display names."""
    from folio import FOLIO_TYPE_IRIS
    from app.services.folio.branch_config import get_branch_display_name

    roots: dict[str, str] = {}
    for ft, iri_hash in FOLIO_TYPE_IRIS.items():
        display_name = get_branch_display_name(ft.name)
        roots[iri_hash] = display_name

    # Discover additional root classes
    owl_thing = "http://www.w3.org/2002/07/owl#Thing"
    for owl_class in folio.classes:
        iri_hash = _extract_iri_hash(owl_class.iri)
        if iri_hash in roots:
            continue
        if owl_class.sub_class_of and owl_class.sub_class_of == [owl_thing]:
            label = owl_class.label or iri_hash
            roots[iri_hash] = label

    return roots


def _build_hierarchy_path(folio, iri_hash: str, branch_root_iris: dict[str, str]) -> list[HierarchyPathEntry]:
    """Build hierarchy path from root branch down to this class."""
    path: list[HierarchyPathEntry] = []
    owl_class = folio[iri_hash]
    if not owl_class:
        return path

    current = owl_class
    visited: set[str] = set()
    while current and len(path) < 10:
        current_hash = _extract_iri_hash(current.iri)
        if current_hash in visited:
            break
        visited.add(current_hash)
        path.append(HierarchyPathEntry(
            label=current.label or current_hash,
            iri_hash=current_hash,
        ))
        if current_hash in branch_root_iris:
            break
        if current.sub_class_of:
            parent_hash = _extract_iri_hash(current.sub_class_of[0])
            current = folio[parent_hash]
        else:
            break

    path.reverse()
    return path


def _get_all_parents(folio, iri_hash: str) -> list[HierarchyPathEntry]:
    """Return all immediate parents of a class (for polyhierarchy DAG display)."""
    owl_class = folio[iri_hash]
    if not owl_class or not owl_class.sub_class_of:
        return []

    owl_thing = "http://www.w3.org/2002/07/owl#Thing"
    parents: list[HierarchyPathEntry] = []
    for parent_iri in owl_class.sub_class_of:
        if parent_iri == owl_thing:
            continue
        parent_hash = _extract_iri_hash(parent_iri)
        parent_class = folio[parent_hash]
        if parent_class:
            parents.append(HierarchyPathEntry(
                label=parent_class.label or parent_hash,
                iri_hash=parent_hash,
            ))
    parents.sort(key=lambda e: e.label)
    return parents


def lookup_concept_detail(folio, iri_hash: str) -> ConceptDetail | None:
    """Look up a FOLIO concept with extended detail."""
    owl_class = folio[iri_hash]
    if not owl_class:
        return None

    branch_root_iris = _init_branch_roots(folio)
    branch_cache: dict[str, str] = {}
    branch_name = _get_branch_for_class(folio, iri_hash, branch_root_iris, branch_cache)

    # Children
    children: list[HierarchyPathEntry] = []
    if owl_class.parent_class_of:
        for child_iri in owl_class.parent_class_of:
            child_hash = _extract_iri_hash(child_iri)
            child_class = folio[child_hash]
            if child_class:
                children.append(HierarchyPathEntry(
                    label=child_class.label or child_hash,
                    iri_hash=child_hash,
                ))
    children.sort(key=lambda e: e.label)

    # Siblings
    siblings: list[HierarchyPathEntry] = []
    if owl_class.sub_class_of:
        parent_hash = _extract_iri_hash(owl_class.sub_class_of[0])
        parent_class = folio[parent_hash]
        if parent_class and parent_class.parent_class_of:
            for sibling_iri in parent_class.parent_class_of:
                sibling_hash = _extract_iri_hash(sibling_iri)
                if sibling_hash == iri_hash:
                    continue
                sibling_class = folio[sibling_hash]
                if sibling_class:
                    siblings.append(HierarchyPathEntry(
                        label=sibling_class.label or sibling_hash,
                        iri_hash=sibling_hash,
                    ))
    siblings.sort(key=lambda e: e.label)

    # Related (see_also)
    related: list[HierarchyPathEntry] = []
    if hasattr(owl_class, "see_also") and owl_class.see_also:
        for related_iri in owl_class.see_also:
            related_hash = _extract_iri_hash(related_iri)
            related_class = folio[related_hash]
            if related_class:
                related.append(HierarchyPathEntry(
                    label=related_class.label or related_hash,
                    iri_hash=related_hash,
                ))
    related.sort(key=lambda e: e.label)

    # Examples and translations
    examples = list(owl_class.examples) if hasattr(owl_class, "examples") and owl_class.examples else []
    translations = dict(owl_class.translations) if hasattr(owl_class, "translations") and owl_class.translations else {}

    return ConceptDetail(
        label=owl_class.label or iri_hash,
        iri=owl_class.iri,
        iri_hash=iri_hash,
        definition=owl_class.definition,
        synonyms=owl_class.alternative_labels or [],
        branch=branch_name,
        branch_color=get_branch_color(branch_name),
        hierarchy_path=_build_hierarchy_path(folio, iri_hash, branch_root_iris),
        all_parents=_get_all_parents(folio, iri_hash),
        children=children,
        siblings=siblings,
        related=related,
        examples=examples,
        translations=translations,
    )


def build_entity_graph(
    folio,
    iri_hash: str,
    ancestors_depth: int = 2,
    descendants_depth: int = 2,
    max_nodes: int = 200,
    include_see_also: bool = True,
    max_see_also_per_node: int = 5,
) -> EntityGraphResponse | None:
    """Build a multi-hop graph around a FOLIO concept via BFS."""
    owl_class = folio[iri_hash]
    if not owl_class:
        return None

    branch_root_iris = _init_branch_roots(folio)
    branch_cache: dict[str, str] = {}
    owl_thing = "http://www.w3.org/2002/07/owl#Thing"
    visited: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    edge_ids: set[str] = set()
    total_discovered_ref = [0]

    def _make_node(h: str, depth: int) -> GraphNode | None:
        if h in visited:
            return visited[h]
        oc = folio[h]
        if not oc:
            return None
        total_discovered_ref[0] += 1
        if len(visited) >= max_nodes:
            return None
        branch_name = _get_branch_for_class(folio, h, branch_root_iris, branch_cache)
        node = GraphNode(
            id=h,
            label=oc.label or h,
            iri=oc.iri,
            definition=oc.definition,
            branch=branch_name,
            branch_color=get_branch_color(branch_name),
            is_focus=(h == iri_hash),
            is_branch_root=(h in branch_root_iris),
            depth=depth,
        )
        visited[h] = node
        return node

    def _add_edge(source: str, target: str, edge_type: str, label: str | None = None) -> None:
        eid = f"{source}->{target}:{edge_type}"
        if eid in edge_ids:
            return
        edge_ids.add(eid)
        edges.append(GraphEdge(id=eid, source=source, target=target, edge_type=edge_type, label=label))

    # Create focus node
    focus_node = _make_node(iri_hash, 0)
    if not focus_node:
        return None

    # BFS upward (ancestors)
    ancestor_queue: list[tuple[str, int]] = [(iri_hash, 0)]
    ancestor_visited: set[str] = {iri_hash}
    while ancestor_queue:
        current_hash, current_depth = ancestor_queue.pop(0)
        if current_depth >= ancestors_depth:
            continue
        current_oc = folio[current_hash]
        if not current_oc or not current_oc.sub_class_of:
            continue
        for parent_iri in current_oc.sub_class_of:
            if parent_iri == owl_thing:
                continue
            parent_hash = _extract_iri_hash(parent_iri)
            parent_node = _make_node(parent_hash, -(current_depth + 1))
            if parent_node is None:
                continue
            _add_edge(parent_hash, current_hash, "subClassOf")
            if parent_hash not in ancestor_visited:
                ancestor_visited.add(parent_hash)
                ancestor_queue.append((parent_hash, current_depth + 1))

    # BFS downward (descendants)
    descendant_queue: list[tuple[str, int]] = [(iri_hash, 0)]
    descendant_visited: set[str] = {iri_hash}
    while descendant_queue:
        current_hash, current_depth = descendant_queue.pop(0)
        if current_depth >= descendants_depth:
            continue
        current_oc = folio[current_hash]
        if not current_oc or not current_oc.parent_class_of:
            continue
        for child_iri in current_oc.parent_class_of:
            child_hash = _extract_iri_hash(child_iri)
            child_node = _make_node(child_hash, current_depth + 1)
            if child_node is None:
                continue
            _add_edge(current_hash, child_hash, "subClassOf")
            if child_hash not in descendant_visited:
                descendant_visited.add(child_hash)
                descendant_queue.append((child_hash, current_depth + 1))

    # Collect seeAlso cross-links
    see_also_nodes: list[str] = []
    if include_see_also:
        for node_hash in list(visited.keys()):
            oc = folio[node_hash]
            if not oc or not hasattr(oc, "see_also") or not oc.see_also:
                continue
            sa_count = 0
            for related_iri in oc.see_also:
                if sa_count >= max_see_also_per_node:
                    break
                related_hash = _extract_iri_hash(related_iri)
                was_new = related_hash not in visited
                if was_new:
                    related_node = _make_node(related_hash, 0)
                    if related_node is None:
                        continue
                    see_also_nodes.append(related_hash)
                if node_hash < related_hash:
                    _add_edge(node_hash, related_hash, "seeAlso", "rdfs:seeAlso")
                else:
                    _add_edge(related_hash, node_hash, "seeAlso", "rdfs:seeAlso")
                sa_count += 1

    truncated = total_discovered_ref[0] > len(visited)

    return EntityGraphResponse(
        focus_iri_hash=iri_hash,
        focus_label=owl_class.label or iri_hash,
        focus_branch=_get_branch_for_class(folio, iri_hash, branch_root_iris, branch_cache),
        nodes=list(visited.values()),
        edges=edges,
        truncated=truncated,
        total_concept_count=total_discovered_ref[0],
    )
