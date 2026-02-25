from __future__ import annotations

import html

from app.models.job import Job
from app.services.export.base import ExporterBase


class HTMLExporter(ExporterBase):
    @property
    def format_name(self) -> str:
        return "html"

    @property
    def content_type(self) -> str:
        return "text/html"

    def export(self, job: Job) -> str:
        if job.result.canonical_text is None:
            return "<html><body><p>No content</p></body></html>"

        full_text = job.result.canonical_text.full_text

        # Combine annotations and individuals, sorted by start position (reverse for safe insertion)
        sorted_anns = sorted(job.result.annotations, key=lambda a: a.span.start, reverse=True)
        sorted_inds = sorted(job.result.individuals, key=lambda i: i.span.start, reverse=True)

        # Build annotated HTML by inserting spans
        result = list(html.escape(full_text))

        for ann in sorted_anns:
            if not ann.concepts:
                continue
            concept = ann.concepts[0]
            branch_str = concept.branches[0] if concept.branches else ""
            branch_part = f" ({branch_str})" if branch_str else ""
            tooltip = html.escape(
                f"{concept.folio_label or concept.concept_text}"
                f"{branch_part}"
                f" - {concept.folio_definition or 'No definition'}"
            )
            iri = html.escape(concept.folio_iri or "#")
            iri_link = f"{iri}/html" if iri != "#" else "#"

            # Confidence-based styling
            conf = concept.confidence
            if conf >= 0.90:
                border_color = "#228B22"  # green
            elif conf >= 0.60:
                border_color = "#FFD700"  # gold
            elif conf >= 0.45:
                border_color = "#FF8C00"  # orange
            else:
                border_color = "#D3D3D3"  # gray

            # Branch color for background tint
            branch_color = concept.branch_color or "#2196F3"

            close_tag = "</a></span>"
            open_tag = (
                f'<span class="folio-annotation" '
                f'style="border-bottom-color: {border_color}; background-color: {branch_color}18;" '
                f'data-iri="{iri}" '
                f'data-branch="{html.escape(branch_str)}" '
                f'data-confidence="{concept.confidence:.2f}">'
                f'<a href="{iri_link}" title="{tooltip}" class="folio-link">'
            )

            # Insert tags at correct positions in the escaped text
            end_pos = ann.span.end
            start_pos = ann.span.start
            result.insert(end_pos, close_tag)
            result.insert(start_pos, open_tag)

        # Insert individual spans (top border style)
        for ind in sorted_inds:
            class_label = ind.class_links[0].folio_label if ind.class_links else ind.individual_type
            tooltip = html.escape(f"{ind.name} ({class_label})")
            conf = ind.confidence
            border_color = "#009688" if ind.individual_type == "legal_citation" else "#FF9800"

            close_tag = "</span>"
            open_tag = (
                f'<span class="folio-individual" '
                f'style="border-top: 2px solid {border_color}; background-color: {border_color}12;" '
                f'data-type="individual" '
                f'data-individual-type="{html.escape(ind.individual_type)}" '
                f'title="{tooltip}">'
            )
            end_pos = ind.span.end
            start_pos = ind.span.start
            result.insert(end_pos, close_tag)
            result.insert(start_pos, open_tag)

        # Insert property spans (purple wavy underline)
        sorted_props = sorted(job.result.properties, key=lambda p: p.span.start, reverse=True)
        for prop in sorted_props:
            label = prop.folio_label or prop.property_text
            tooltip = html.escape(f"{label} — {prop.folio_definition or 'OWL ObjectProperty'}")

            close_tag = "</span>"
            open_tag = (
                f'<span class="folio-property" '
                f'style="text-decoration: underline wavy #9C27B0; text-underline-offset: 3px;" '
                f'data-type="property" '
                f'data-iri="{html.escape(prop.folio_iri or "#")}" '
                f'title="{tooltip}">'
            )
            end_pos = prop.span.end
            start_pos = prop.span.start
            result.insert(end_pos, close_tag)
            result.insert(start_pos, open_tag)

        body = "".join(result)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>FOLIO Enrich - Annotated Document</title>
<style>
.folio-annotation {{ background-color: #e8f4fd; border-bottom: 2px solid #2196F3; cursor: pointer; }}
.folio-annotation:hover {{ background-color: #bbdefb; }}
.folio-individual {{ border-top: 2px solid #009688; cursor: pointer; }}
.folio-individual:hover {{ background-color: rgba(0,150,136,0.15); }}
.folio-property {{ text-decoration: underline wavy #9C27B0; cursor: pointer; }}
.folio-property:hover {{ background-color: rgba(156,39,176,0.15); }}
.folio-link {{ color: inherit; text-decoration: none; }}
body {{ font-family: 'Georgia', serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
</style>
</head>
<body>
<pre style="white-space: pre-wrap; font-family: inherit;">{body}</pre>
</body>
</html>"""
