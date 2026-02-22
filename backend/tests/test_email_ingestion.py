"""Tests for Email ingestion."""

import pytest

from app.models.document import DocumentFormat, DocumentInput


class TestEmailIngestion:
    def test_email_format_enum(self):
        assert DocumentFormat.EMAIL == "email"

    def test_eml_ingestor(self):
        from app.services.ingestion.email_ingestor import EmailIngestor

        eml_content = (
            "From: sender@example.com\r\n"
            "To: recipient@example.com\r\n"
            "Subject: Test Email\r\n"
            "Date: Mon, 1 Jan 2024 00:00:00 +0000\r\n"
            "\r\n"
            "This is the body of the test email.\r\n"
        )
        doc = DocumentInput(
            content=eml_content,
            format=DocumentFormat.EMAIL,
            filename="test.eml",
        )
        ingestor = EmailIngestor()
        text = ingestor.ingest(doc)
        assert "sender@example.com" in text
        assert "Test Email" in text
        assert "body of the test email" in text

    def test_email_registered_in_registry(self):
        from app.services.ingestion.registry import get_ingestor

        ingestor = get_ingestor(DocumentFormat.EMAIL)
        assert ingestor is not None

    def test_detect_format_eml(self):
        from app.services.ingestion.registry import detect_format

        assert detect_format("message.eml", "") == DocumentFormat.EMAIL

    def test_detect_format_msg(self):
        from app.services.ingestion.registry import detect_format

        assert detect_format("message.msg", "") == DocumentFormat.EMAIL
