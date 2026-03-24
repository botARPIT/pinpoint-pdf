"""
Table extraction from PDF using PyMuPDF's built-in table finder.
Exports each table as a structured dict with headers, rows, and bbox.
"""
from dataclasses import dataclass
from typing import List, Optional

import fitz  # PyMuPDF
import structlog

logger = structlog.get_logger()


@dataclass
class ExtractedTable:
    """A single extracted table."""
    page: int
    table_id: str            # e.g. "table_0_1"
    headers: Optional[List[str]]
    rows: List[List[str]]
    bbox: tuple              # (x0, y0, x1, y1)
    num_rows: int
    num_cols: int


def extract_tables_pymupdf(pdf_bytes: bytes) -> List[ExtractedTable]:
    """
    Extract tables from PDF using PyMuPDF's find_tables().

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        List of ExtractedTable objects
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        tables = extract_tables_from_document(doc)
    finally:
        doc.close()

    logger.info("Tables extracted", total=len(tables))
    return tables


def extract_tables_from_document(doc: fitz.Document) -> List[ExtractedTable]:
    """Extract tables from an already-open PyMuPDF document."""
    tables = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        try:
            found_tables = page.find_tables()
        except Exception as e:
            logger.warning("Table detection failed", page=page_num, error=str(e))
            continue

        for idx, table in enumerate(found_tables.tables):
            try:
                # Extract cell data
                table_data = table.extract()
                if not table_data or len(table_data) < 1:
                    continue

                # Clean cell values
                def clean_cell(val):
                    if val is None:
                        return ""
                    return str(val).strip()

                # First row as headers
                headers = [clean_cell(c) for c in table_data[0]]
                rows = [
                    [clean_cell(c) for c in row]
                    for row in table_data[1:]
                ]

                # Get bbox
                bbox = (
                    float(table.bbox[0]),
                    float(table.bbox[1]),
                    float(table.bbox[2]),
                    float(table.bbox[3]),
                )

                num_cols = len(headers) if headers else 0
                num_rows = len(rows)

                table_id = f"table_{page_num}_{idx + 1}"

                tables.append(ExtractedTable(
                    page=page_num,
                    table_id=table_id,
                    headers=headers,
                    rows=rows,
                    bbox=bbox,
                    num_rows=num_rows,
                    num_cols=num_cols,
                ))

            except Exception as e:
                logger.warning(
                    "Failed to extract table",
                    page=page_num, idx=idx, error=str(e)
                )
                continue

    return tables


def table_to_dict(table: ExtractedTable) -> dict:
    """Convert ExtractedTable to a JSON-serializable dict."""
    return {
        "table_id": table.table_id,
        "page": table.page,
        "headers": table.headers,
        "rows": table.rows,
        "bbox": list(table.bbox),
        "num_rows": table.num_rows,
        "num_cols": table.num_cols,
    }


# Backward compat alias
def extract_tables(pdf_bytes) -> list:
    """Legacy wrapper for backward compatibility."""
    from dataclasses import dataclass as dc

    @dc
    class LegacyTable:
        page: int
        headers: Optional[List[str]]
        rows: List[List[str]]
        bbox: tuple

    if hasattr(pdf_bytes, 'read'):
        pdf_bytes = pdf_bytes.read()

    tables = extract_tables_pymupdf(pdf_bytes)
    return [
        LegacyTable(
            page=t.page,
            headers=t.headers,
            rows=t.rows,
            bbox=t.bbox,
        )
        for t in tables
    ]
