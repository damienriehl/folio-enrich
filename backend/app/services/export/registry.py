from __future__ import annotations

from app.services.export.base import ExporterBase
from app.services.export.csv_exporter import CSVExporter
from app.services.export.json_exporter import JSONExporter
from app.services.export.jsonl_exporter import JSONLExporter
from app.services.export.jsonld_exporter import JSONLDExporter
from app.services.export.xml_exporter import XMLExporter
from app.services.export.brat_exporter import BratExporter
from app.services.export.elasticsearch_exporter import ElasticsearchExporter
from app.services.export.html_exporter import HTMLExporter
from app.services.export.neo4j_exporter import Neo4jExporter
from app.services.export.parquet_exporter import ParquetExporter
from app.services.export.rag_exporter import RAGExporter
from app.services.export.rdf_exporter import RDFExporter
from app.services.export.excel_exporter import ExcelExporter

_EXPORTERS: dict[str, type[ExporterBase]] = {}


def register_exporter(cls: type[ExporterBase]) -> type[ExporterBase]:
    instance = cls()
    _EXPORTERS[instance.format_name] = cls
    return cls


def get_exporter(format_name: str) -> ExporterBase:
    cls = _EXPORTERS.get(format_name)
    if cls is None:
        raise ValueError(
            f"Unknown export format: {format_name}. Available: {list(_EXPORTERS.keys())}"
        )
    return cls()


def list_formats() -> list[str]:
    return list(_EXPORTERS.keys())


# Register default exporters
register_exporter(JSONExporter)
register_exporter(JSONLDExporter)
register_exporter(XMLExporter)
register_exporter(CSVExporter)
register_exporter(JSONLExporter)
register_exporter(ParquetExporter)
register_exporter(ElasticsearchExporter)
register_exporter(Neo4jExporter)
register_exporter(RAGExporter)
register_exporter(RDFExporter)
register_exporter(BratExporter)
register_exporter(HTMLExporter)
register_exporter(ExcelExporter)
