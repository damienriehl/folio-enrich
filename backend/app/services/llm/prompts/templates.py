from __future__ import annotations

import logging

from app.services.folio.branch_config import get_llm_branch_names

logger = logging.getLogger(__name__)

FOLIO_BRANCHES: list[str] = get_llm_branch_names()

BRANCH_EXAMPLES: dict[str, str] = {
    "Actor / Player": (
        "e.g., plaintiffs, defendants, judges, counterparties, Agent, Assignor, "
        "Bail Bondsman, Bank, Common Carrier, Court Reporter, Debtor, Deponent, "
        "Employer, Expert, Franchisor, Garnishee, Guardian Ad Litem, Insurer, "
        "Landlord, Law Enforcement, Licensee, Liquidator"
    ),
    "Asset Type": "e.g., real property, intellectual property, securities, chattel",
    "Communication Modality": "e.g., email, telephone, in-person, video conference, written notice",
    "Currency": "e.g., USD, EUR, GBP, JPY, cryptocurrency",
    "Data Format": "e.g., PDF, DOCX, XML, JSON, EDI",
    "Document / Artifact": "e.g., contract, brief, memorandum, deposition transcript, exhibit",
    "Document Metadata": "e.g., author, recipient, editor, filed date, amendment",
    "Engagement Terms": "e.g., fee arrangement, retainer, billing rate, scope of work, hourly rate",
    "Event": "e.g., filing, hearing, trial, deposition, mediation, closing",
    "Financial Concepts and Metrics": "e.g., revenue, liability, damages amount, settlement value, interest rate",
    "Forums and Venues": "e.g., district court, arbitration panel, appellate court, tribunal",
    "Governmental Body": "e.g., SEC, EPA, FTC, Congress, state legislature",
    "Industry": "e.g., healthcare, finance, technology, energy, real estate",
    "Language": "e.g., English, Spanish, French, Mandarin",
    "Legal Authorities": "e.g., statutes, regulations, case law, constitutional provisions, treaties",
    "Legal Entity": "e.g., corporation, LLC, partnership, trust, nonprofit",
    "Legal Use Cases": "e.g., compliance review, due diligence, litigation hold, contract negotiation",
    "Location": "e.g., New York, Delaware, London, jurisdiction-specific places",
    "Matter Narrative": "e.g., case summary, matter description, procedural history",
    "Matter Narrative Format": "e.g., chronological, thematic, issue-based narrative structure",
    "Objectives": "e.g., breach of contract, damages, injunctive relief, specific performance",
    "Service": "e.g., legal research, document review, e-discovery, mediation services",
    "Status": "e.g., pending, active, closed, stayed, dismissed, settled",
    "System Identifiers": "e.g., docket number, case ID, matter number, PACER ID",
}

BRANCH_LIST = "\n".join(
    f"- {b} ({BRANCH_EXAMPLES[b]})" if b in BRANCH_EXAMPLES else f"- {b}"
    for b in FOLIO_BRANCHES
)


def build_branch_detail(max_concepts_per_branch: int = 8, max_total_chars: int = 8000) -> str:
    """Build enriched branch descriptions using actual FOLIO concept definitions and examples.

    Falls back to BRANCH_EXAMPLES if the FOLIO service is unavailable.
    """
    try:
        from app.services.folio.folio_service import FolioService
        from app.services.folio.branch_config import EXCLUDED_BRANCHES
        folio = FolioService.get_instance()
        folio_obj = folio._get_folio()
        branches_dict = folio_obj.get_folio_branches(max_depth=16)
    except Exception:
        logger.debug("FOLIO service unavailable for branch detail; using hardcoded examples")
        return BRANCH_LIST

    from app.services.folio.branch_config import get_branch_display_name

    lines: list[str] = []
    total_chars = 0

    for branch_name in FOLIO_BRANCHES:
        # Find this branch's concepts in the folio branches dict
        branch_concepts = []
        for ft_key, classes in branches_dict.items():
            key = ft_key.name if hasattr(ft_key, "name") else str(ft_key).split(".")[-1]
            display = get_branch_display_name(key)
            if display == branch_name:
                branch_concepts = classes
                break

        # Select concepts that have definitions, up to max_concepts_per_branch
        concept_entries: list[str] = []
        for cls in branch_concepts:
            if len(concept_entries) >= max_concepts_per_branch:
                break
            defn = getattr(cls, "definition", "") or ""
            if not defn:
                continue
            label = getattr(cls, "preferred_label", None) or getattr(cls, "label", "") or ""
            if not label:
                continue
            entry = f"  * {label} — {defn[:120]}"
            # Add examples if available
            examples = getattr(cls, "examples", []) or []
            if examples:
                entry += f" (e.g., {', '.join(examples[:3])})"
            # Add alt labels if available
            alt_labels = getattr(cls, "alternative_labels", []) or []
            if alt_labels:
                entry += f"\n    Also known as: {', '.join(alt_labels[:4])}"
            concept_entries.append(entry)

        if concept_entries:
            branch_line = f"- {branch_name}:\n" + "\n".join(concept_entries)
        elif branch_name in BRANCH_EXAMPLES:
            branch_line = f"- {branch_name} ({BRANCH_EXAMPLES[branch_name]})"
        else:
            branch_line = f"- {branch_name}"

        if total_chars + len(branch_line) > max_total_chars:
            # Fall back to compact format for remaining branches
            if branch_name in BRANCH_EXAMPLES:
                branch_line = f"- {branch_name} ({BRANCH_EXAMPLES[branch_name]})"
            else:
                branch_line = f"- {branch_name}"

        lines.append(branch_line)
        total_chars += len(branch_line)

    return "\n".join(lines)


def get_branch_detail() -> str:
    """Get branch detail, building lazily on first call."""
    global _BRANCH_DETAIL_CACHE
    if _BRANCH_DETAIL_CACHE is None:
        _BRANCH_DETAIL_CACHE = build_branch_detail()
    return _BRANCH_DETAIL_CACHE


_BRANCH_DETAIL_CACHE: str | None = None
