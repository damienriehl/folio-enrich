from __future__ import annotations

from app.models.document import DocumentInput, TextElement
from app.services.ingestion.base import IngestorBase

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_LIST_TAGS = {"li"}
_TABLE_CELL_TAGS = {"td", "th"}


class HTMLIngestor(IngestorBase):
    def ingest(self, doc: DocumentInput) -> str:
        text, _ = self.ingest_with_elements(doc)
        return text

    def ingest_with_elements(self, doc: DocumentInput) -> tuple[str, list[TextElement]]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(doc.content, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "head"]):
            element.decompose()

        elements: list[TextElement] = []
        section_path: list[str] = []

        for tag in soup.find_all(True):
            tag_name = tag.name.lower() if tag.name else ""
            text_content = tag.get_text(strip=True)
            if not text_content:
                continue

            if tag_name in _HEADING_TAGS:
                level = int(tag_name[1])
                # Update section path: trim to this level, then add
                section_path = section_path[:level - 1]
                section_path.append(text_content)
                elements.append(TextElement(
                    text=text_content,
                    element_type="heading",
                    section_path=list(section_path),
                    level=level,
                ))
            elif tag_name in _LIST_TAGS:
                elements.append(TextElement(
                    text=text_content,
                    element_type="list_item",
                    section_path=list(section_path),
                ))
            elif tag_name in _TABLE_CELL_TAGS:
                elements.append(TextElement(
                    text=text_content,
                    element_type="table_cell",
                    section_path=list(section_path),
                ))
            elif tag_name == "p":
                elements.append(TextElement(
                    text=text_content,
                    element_type="paragraph",
                    section_path=list(section_path),
                ))

        # Also return the full text as before
        full_text = soup.get_text(separator="\n")
        lines = [line.strip() for line in full_text.splitlines()]
        clean_text = "\n".join(line for line in lines if line)
        return clean_text, elements
