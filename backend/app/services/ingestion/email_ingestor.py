from __future__ import annotations

import email
import email.policy

from app.models.document import DocumentInput
from app.services.ingestion.base import IngestorBase


class EmailIngestor(IngestorBase):
    """Extract plain text from EML and MSG email files."""

    def ingest(self, doc: DocumentInput) -> str:
        content = doc.content
        filename = (doc.filename or "").lower()

        if filename.endswith(".msg"):
            return self._ingest_msg(content)
        else:
            # Default: EML format (RFC 2822)
            return self._ingest_eml(content)

    def _ingest_eml(self, content: str) -> str:
        """Parse EML using stdlib email module."""
        # Content may be base64-encoded raw bytes or the EML text directly
        try:
            import base64
            raw = base64.b64decode(content)
            content = raw.decode("utf-8", errors="replace")
        except Exception:
            pass

        msg = email.message_from_string(content, policy=email.policy.default)
        parts = []

        # Add headers
        for header in ("From", "To", "Subject", "Date"):
            value = msg.get(header, "")
            if value:
                parts.append(f"{header}: {value}")

        if parts:
            parts.append("")  # blank line separator

        # Extract body text
        body = msg.get_body(preferencelist=("plain", "html"))
        if body is not None:
            body_content = body.get_content()
            if body.get_content_type() == "text/html":
                # Strip HTML tags for plain text
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(body_content, "html.parser")
                    body_content = soup.get_text(separator="\n")
                except ImportError:
                    import re
                    body_content = re.sub(r"<[^>]+>", "", body_content)
            parts.append(body_content)

        return "\n".join(parts)

    def _ingest_msg(self, content: str) -> str:
        """Parse MSG files using extract-msg."""
        import base64
        import tempfile
        from pathlib import Path

        import extract_msg

        # MSG files are binary — decode from base64
        msg_bytes = base64.b64decode(content)
        with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tmp:
            tmp.write(msg_bytes)
            tmp_path = tmp.name

        try:
            msg = extract_msg.Message(tmp_path)
            parts = []
            if msg.sender:
                parts.append(f"From: {msg.sender}")
            if msg.to:
                parts.append(f"To: {msg.to}")
            if msg.subject:
                parts.append(f"Subject: {msg.subject}")
            if msg.date:
                parts.append(f"Date: {msg.date}")
            if parts:
                parts.append("")
            if msg.body:
                parts.append(msg.body)
            msg.close()
            return "\n".join(parts)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
