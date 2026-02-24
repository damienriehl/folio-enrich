from __future__ import annotations

from app.services.folio.branch_config import get_llm_branch_names

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
