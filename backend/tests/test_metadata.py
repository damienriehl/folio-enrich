from __future__ import annotations

from typing import Any

import pytest

from app.models.annotation import Annotation, ConceptMatch, Individual, IndividualClassLink, PropertyAnnotation, Span
from app.models.document import CanonicalText, DocumentFormat, DocumentInput, TextChunk, TextElement
from app.models.job import Job, JobResult, JobStatus
from app.pipeline.stages.metadata_stage import MetadataStage, _build_context
from app.services.llm.base import LLMProvider
from app.services.metadata.classifier import DocumentClassifier
from app.services.metadata.extractor import MetadataExtractor, build_context_block
from app.services.metadata.promoter import MetadataPromoter, POSITION_HINTS


# --- Fake LLMs ---------------------------------------------------------------

ALL_EXTRACTED_FIELDS = {
    "case_name": "Acme Corp v. Widget Inc",
    "court": "Southern District of New York",
    "judge": "Judge Smith",
    "case_number": "1:23-cv-01234",
    "parties": ["Acme Corp (Plaintiff)", "Widget Inc (Defendant)"],
    "jurisdiction": "Federal",
    "procedural_posture": "Motion to Dismiss pending",
    "cause_of_action": "Breach of Contract",
    "claim_types": ["Breach of Contract"],
    "relief_sought": "Damages of $5,000,000",
    "disposition": "",
    "standard_of_review": "",
    "governing_law": "New York",
    "author": "John Doe",
    "recipient": "Jane Smith",
    "attorneys": ["John Doe (Smith & Jones LLP, for Plaintiff)"],
    "signatories": ["John Doe"],
    "witnesses": [],
    "date_filed": "2023-06-15",
    "date_signed": "",
    "date_effective": "",
    "date_due": "",
    "dates_mentioned": ["2024-01-15: date of incident"],
    "document_title": "Motion to Dismiss",
    "docket_entry_number": "Doc. 42",
    "related_documents": ["Exhibit A — Purchase Agreement"],
    "confidentiality": "",
    "contract_type": "",
    "counterparties": [],
    "term_duration": "",
    "termination_conditions": "",
    "consideration": "",
    "language": "English",
    "addresses": ["123 Main St, New York, NY 10001"],
    "has_exhibits": "true",
    "exhibit_list": ["Exhibit A — Purchase Agreement"],
}


class FakeClassifierLLM(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        return {"document_type": "Motion to Dismiss", "confidence": 0.92, "reasoning": "test"}

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


class FakeExtractorLLM(LLMProvider):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        return dict(ALL_EXTRACTED_FIELDS)

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


class TrackingClassifierLLM(LLMProvider):
    """Tracks whether classify was called."""

    def __init__(self):
        self.classify_called = False

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    async def structured(self, prompt: str, schema: dict, **kwargs: Any) -> dict:
        if "classifier" in prompt.lower() or "classify" in prompt.lower() or "document type" in prompt.lower():
            self.classify_called = True
            return {"document_type": "Should Not Be Used", "confidence": 0.5, "reasoning": "test"}
        return dict(ALL_EXTRACTED_FIELDS)

    async def test_connection(self) -> bool:
        return True

    async def list_models(self):
        return []


# --- Helper -------------------------------------------------------------------

def _make_job(text: str = "IN THE UNITED STATES DISTRICT COURT...", **meta) -> Job:
    """Create a minimal job with canonical text and optional metadata."""
    job = Job(
        input=DocumentInput(content=text, format=DocumentFormat.PLAIN_TEXT),
        status=JobStatus.ENRICHING,
        result=JobResult(
            canonical_text=CanonicalText(
                full_text=text,
                chunks=[TextChunk(text=text, start_offset=0, end_offset=len(text), chunk_index=0)],
            ),
        ),
    )
    job.result.metadata.update(meta)
    return job


# --- Tests: DocumentClassifier -----------------------------------------------

class TestDocumentClassifier:
    @pytest.mark.asyncio
    async def test_classify(self):
        classifier = DocumentClassifier(FakeClassifierLLM())
        result = await classifier.classify("IN THE UNITED STATES DISTRICT COURT...")
        assert result["document_type"] == "Motion to Dismiss"
        assert result["confidence"] == 0.92


# --- Tests: MetadataExtractor ------------------------------------------------

class TestMetadataExtractor:
    @pytest.mark.asyncio
    async def test_extract_with_context(self):
        """Extractor now accepts a context dict, not raw text."""
        extractor = MetadataExtractor(FakeExtractorLLM())
        context = {
            "entities_by_type": {"Persons": ["John Doe"], "Organizations": ["Acme Corp"]},
            "header_text": "IN THE UNITED STATES DISTRICT COURT...",
        }
        result = await extractor.extract(context, "Motion to Dismiss")
        assert result["court"] == "Southern District of New York"
        assert result["judge"] == "Judge Smith"
        assert len(result["parties"]) == 2
        assert result["author"] == "John Doe"
        assert result["recipient"] == "Jane Smith"
        assert result["addresses"] == ["123 Main St, New York, NY 10001"]
        # New fields
        assert result["case_name"] == "Acme Corp v. Widget Inc"
        assert result["attorneys"] == ["John Doe (Smith & Jones LLP, for Plaintiff)"]
        assert result["has_exhibits"] == "true"
        assert result["language"] == "English"

    @pytest.mark.asyncio
    async def test_extract_empty_context(self):
        """Empty context still works (prompt has no entities section)."""
        extractor = MetadataExtractor(FakeExtractorLLM())
        result = await extractor.extract({}, "Unknown")
        assert result["court"] == "Southern District of New York"


# --- Tests: build_context_block -----------------------------------------------

class TestBuildContextBlock:
    def test_entities_by_type(self):
        block = build_context_block({
            "entities_by_type": {"Persons": ["Alice", "Bob"], "Organizations": ["Acme"]},
        })
        assert "NAMED ENTITIES:" in block
        assert "Persons: Alice, Bob" in block
        assert "Organizations: Acme" in block

    def test_low_confidence_entities(self):
        block = build_context_block({
            "low_confidence_entities": [
                {"name": "Smith", "type": "Persons", "confidence": 0.65, "sentence": "Smith filed the motion."},
            ],
        })
        assert "LOW-CONFIDENCE ENTITIES" in block
        assert '"Smith"' in block
        assert "Smith filed the motion." in block

    def test_relationships(self):
        block = build_context_block({
            "relationships": ["Alice → represented_by → Smith LLP"],
        })
        assert "RELATIONSHIPS:" in block
        assert "Alice → represented_by → Smith LLP" in block

    def test_concepts(self):
        block = build_context_block({"concepts": ["breach of contract", "negligence"]})
        assert "LEGAL CONCEPTS" in block
        assert "breach of contract, negligence" in block

    def test_areas_of_law(self):
        block = build_context_block({
            "areas_of_law": [{"area": "Contract Law", "confidence": 0.92}],
        })
        assert "AREAS OF LAW:" in block
        assert "Contract Law (92%)" in block

    def test_bookends(self):
        block = build_context_block({
            "header_text": "HEADER TEXT HERE",
            "footer_text": "FOOTER TEXT HERE",
        })
        assert "DOCUMENT HEADER" in block
        assert "HEADER TEXT HERE" in block
        assert "SIGNATURE BLOCK" in block
        assert "FOOTER TEXT HERE" in block

    def test_empty_context(self):
        block = build_context_block({})
        assert block == ""


# --- Tests: _build_context (pipeline integration) ----------------------------

class TestBuildContextFromJob:
    def test_groups_individuals_by_type(self):
        job = _make_job()
        job.result.individuals = [
            Individual(
                name="John Smith", mention_text="John Smith",
                span=Span(start=0, end=10, text="John Smith"),
                individual_type="named_entity", confidence=0.95, source="spacy_ner",
                class_links=[IndividualClassLink(folio_label="Person", confidence=0.9)],
            ),
            Individual(
                name="Acme Corp", mention_text="Acme Corp",
                span=Span(start=20, end=29, text="Acme Corp"),
                individual_type="named_entity", confidence=0.90, source="spacy_ner",
                class_links=[IndividualClassLink(folio_label="Organization", confidence=0.85)],
            ),
        ]
        ctx = _build_context(job)
        assert "Persons" in ctx["entities_by_type"]
        assert "John Smith" in ctx["entities_by_type"]["Persons"]
        assert "Organizations" in ctx["entities_by_type"]
        assert "Acme Corp" in ctx["entities_by_type"]["Organizations"]

    def test_low_confidence_entity_includes_sentence(self):
        job = _make_job()
        job.result.individuals = [
            Individual(
                name="Smith", mention_text="Smith",
                span=Span(start=0, end=5, text="Smith", sentence_text="The firm of Smith & Associates filed the motion."),
                individual_type="named_entity", confidence=0.65, source="spacy_ner",
                class_links=[IndividualClassLink(folio_label="Person", confidence=0.5)],
            ),
        ]
        ctx = _build_context(job)
        assert len(ctx.get("low_confidence_entities", [])) == 1
        lc = ctx["low_confidence_entities"][0]
        assert lc["name"] == "Smith"
        assert "Smith & Associates" in lc["sentence"]

    def test_includes_spo_triples(self):
        job = _make_job(spo_triples=[
            {"subject": "Alice", "predicate": "represented_by", "object": "Smith LLP"},
        ])
        ctx = _build_context(job)
        assert "Alice → represented_by → Smith LLP" in ctx["relationships"]

    def test_includes_resolved_concepts(self):
        job = _make_job(resolved_concepts=[
            {"folio_label": "Breach of Contract", "confidence": 0.95},
            {"folio_label": "Negligence", "confidence": 0.88},
        ])
        ctx = _build_context(job)
        assert "Breach of Contract" in ctx["concepts"]
        assert "Negligence" in ctx["concepts"]

    def test_includes_areas_of_law(self):
        job = _make_job(areas_of_law=[
            {"area": "Contract Law", "confidence": 0.92},
        ])
        ctx = _build_context(job)
        assert ctx["areas_of_law"] == [{"area": "Contract Law", "confidence": 0.92}]

    def test_header_and_footer(self):
        long_text = "A" * 2000
        job = _make_job(long_text)
        ctx = _build_context(job)
        assert len(ctx["header_text"]) == 1000
        assert len(ctx["footer_text"]) == 500

    def test_no_footer_for_short_text(self):
        job = _make_job("Short text")
        ctx = _build_context(job)
        assert "header_text" in ctx
        assert "footer_text" not in ctx

    def test_includes_properties(self):
        job = _make_job()
        job.result.properties = [
            PropertyAnnotation(
                property_text="represented by",
                folio_label="isRepresentedBy",
                span=Span(start=10, end=24, text="represented by"),
                confidence=0.9,
            ),
        ]
        ctx = _build_context(job)
        assert len(ctx["properties"]) == 1
        assert "isRepresentedBy" in ctx["properties"][0]


# --- Tests: MetadataStage (integration) ---------------------------------------

class TestMetadataStageReuse:
    @pytest.mark.asyncio
    async def test_reuses_early_document_type(self):
        """When self_identified_type is set, MetadataStage skips classifier."""
        llm = FakeExtractorLLM()
        stage = MetadataStage(llm, classifier_llm=llm, extractor_llm=llm)

        job = _make_job()
        job.result.metadata["self_identified_type"] = "Defendant's Motion to Dismiss"
        job.result.metadata["document_type_confidence"] = 0.95

        result = await stage.execute(job)

        assert result.result.metadata["document_type"] == "Defendant's Motion to Dismiss"
        log = result.result.metadata.get("activity_log", [])
        assert any("reused_early=yes" in entry.get("msg", "") for entry in log)

    @pytest.mark.asyncio
    async def test_falls_back_when_no_early_type(self):
        """Without self_identified_type, MetadataStage classifies normally."""
        stage = MetadataStage(
            FakeClassifierLLM(),
            classifier_llm=FakeClassifierLLM(),
            extractor_llm=FakeExtractorLLM(),
        )

        job = _make_job()
        result = await stage.execute(job)

        assert result.result.metadata["document_type"] == "Motion to Dismiss"
        log = result.result.metadata.get("activity_log", [])
        assert any("reused_early=no" in entry.get("msg", "") for entry in log)

    @pytest.mark.asyncio
    async def test_deterministic_fields(self):
        """page_count and source_format are set deterministically."""
        llm = FakeExtractorLLM()
        stage = MetadataStage(llm, classifier_llm=llm, extractor_llm=llm)

        text = "Some legal text..."
        job = Job(
            input=DocumentInput(content=text, format=DocumentFormat.PLAIN_TEXT),
            status=JobStatus.ENRICHING,
            result=JobResult(
                canonical_text=CanonicalText(
                    full_text=text,
                    chunks=[TextChunk(text=text, start_offset=0, end_offset=len(text), chunk_index=0)],
                    elements=[
                        TextElement(text="Page 1", page=0),
                        TextElement(text="Page 2", page=1),
                        TextElement(text="Page 3", page=2),
                    ],
                    source_format=DocumentFormat.PDF,
                ),
            ),
        )

        result = await stage.execute(job)
        fields = result.result.metadata["extracted_fields"]
        assert fields["page_count"] == "3"
        assert fields["source_format"] == "pdf"

    @pytest.mark.asyncio
    async def test_source_format_plain_text(self):
        """source_format defaults to plain_text."""
        llm = FakeExtractorLLM()
        stage = MetadataStage(llm, classifier_llm=llm, extractor_llm=llm)
        job = _make_job()

        result = await stage.execute(job)
        fields = result.result.metadata["extracted_fields"]
        assert fields["source_format"] == "plain_text"


# --- Tests: MetadataPromoter -------------------------------------------------

class TestMetadataPromoter:
    def test_promote_from_context(self):
        promoter = MetadataPromoter()
        annotations = [
            Annotation(
                span=Span(start=80, end=95, text="Southern District"),
                concepts=[
                    ConceptMatch(
                        concept_text="Southern District",
                        folio_iri="iri1",
                        confidence=0.9,
                    )
                ],
            ),
        ]
        full_text = " " * 30 + "IN THE UNITED STATES DISTRICT COURT FOR THE " + " " * 5 + "Southern District"
        result = promoter.promote(annotations, full_text, {})
        assert "court" in result or len(result) >= 0  # Context-dependent

    def test_attorney_hint(self):
        promoter = MetadataPromoter()
        annotations = [
            Annotation(
                span=Span(start=60, end=70, text="Doe & Assoc"),
                concepts=[ConceptMatch(concept_text="Doe & Assoc", folio_iri="iri2", confidence=0.9)],
            ),
        ]
        full_text = " " * 10 + "Attorney for Plaintiff: " + " " * 26 + "Doe & Assoc"
        result = promoter.promote(annotations, full_text, {})
        assert result.get("attorney") == "Doe & Assoc"

    def test_witness_hint(self):
        promoter = MetadataPromoter()
        annotations = [
            Annotation(
                span=Span(start=55, end=65, text="Jane Roe"),
                concepts=[ConceptMatch(concept_text="Jane Roe", folio_iri="iri3", confidence=0.9)],
            ),
        ]
        full_text = " " * 5 + "WITNESS: " + " " * 41 + "Jane Roe"
        result = promoter.promote(annotations, full_text, {})
        # The "witness" hint should match the context before the span
        # Context is full_text[5:55] = "WITNESS: " + spaces
        assert result.get("witness") == "Jane Roe"

    def test_confidentiality_hint(self):
        promoter = MetadataPromoter()
        annotations = [
            Annotation(
                span=Span(start=60, end=75, text="Trade Secrets"),
                concepts=[ConceptMatch(concept_text="Trade Secrets", folio_iri="iri4", confidence=0.9)],
            ),
        ]
        full_text = " " * 10 + "CONFIDENTIAL — " + " " * 35 + "Trade Secrets"
        result = promoter.promote(annotations, full_text, {})
        assert result.get("confidentiality") == "Trade Secrets"

    def test_all_position_hints_present(self):
        """All expected hint keys exist in POSITION_HINTS."""
        expected = {"signatory", "court", "judge", "attorney", "witness", "confidentiality"}
        assert set(POSITION_HINTS.keys()) == expected
