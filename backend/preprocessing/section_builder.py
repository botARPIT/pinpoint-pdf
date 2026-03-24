"""
Section builder — assembles structured document representation with:
- Section hierarchy tree
- Layout map (per-page block positions and reading order)
- Page metadata (dimensions, counts, section mapping)
"""
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

from preprocessing.layout_parser import ParsedDocument, ParsedPage, TextBlock, FigureBlock
from preprocessing.table_extractor import ExtractedTable, table_to_dict

import structlog

logger = structlog.get_logger()


@dataclass
class SectionNode:
    """A node in the section hierarchy tree."""
    title: str
    level: int
    path: str
    page_start: int
    page_end: int
    children: List["SectionNode"] = field(default_factory=list)
    block_count: int = 0
    figure_count: int = 0
    table_count: int = 0


@dataclass
class StructuredOutput:
    """Complete structured output ready for S3 upload."""
    structured_text: List[dict]     # text blocks with section info
    layout_map: Dict[str, dict]     # per-page layout info
    page_metadata: dict             # global metadata
    section_tree: List[dict]        # hierarchical sections
    tables: List[dict]              # individual table dicts
    figures: List[dict]             # figure metadata (bytes stored separately)
    figure_bytes: Dict[str, bytes]  # figure_id → PNG bytes


def build_structured_output(
    parsed_doc: ParsedDocument,
    tables: List[ExtractedTable],
    include_diagnostics: bool = True,
) -> StructuredOutput:
    """
    Build complete structured output from parsed document and tables.

    Args:
        parsed_doc: Output from parse_pdf()
        tables: Output from extract_tables_pymupdf()
        include_diagnostics: Compute layout_map/page_metadata/section_tree.
            Disable for ingestion fast-path when these artifacts are unused.

    Returns:
        StructuredOutput with all components ready for S3
    """
    # --- Structured Text ---
    structured_text = []
    for page in parsed_doc.pages:
        for block in page.text_blocks:
            structured_text.append({
                "page": block.page,
                "section_path": block.section_path,
                "text": block.text,
                "bbox": [float(x) for x in block.bbox],
                "is_heading": block.is_heading,
                "font_size": round(block.font_size, 2),
                "font_name": block.font_name,
                "is_bold": block.is_bold,
            })

    layout_map: Dict[str, dict] = {}
    section_tree: List[SectionNode] = []
    page_metadata: dict = {}
    if include_diagnostics:
        # --- Layout Map (per-page) ---
        for page in parsed_doc.pages:
            page_key = f"page_{page.page_num}"

            # Block positions in reading order
            block_positions = []
            for i, block in enumerate(page.text_blocks):
                block_positions.append({
                    "order": i,
                    "type": "heading" if block.is_heading else "text",
                    "bbox": [float(x) for x in block.bbox],
                    "section": block.section_path,
                    "text_preview": block.text[:80],
                })

            # Figure positions
            figure_positions = []
            for fig in page.figures:
                figure_positions.append({
                    "figure_id": fig.figure_id,
                    "bbox": [float(x) for x in fig.bbox],
                    "width": fig.width,
                    "height": fig.height,
                })

            # Table positions on this page
            page_tables = [t for t in tables if t.page == page.page_num]
            table_positions = []
            for t in page_tables:
                table_positions.append({
                    "table_id": t.table_id,
                    "bbox": [float(x) for x in t.bbox],
                    "num_rows": t.num_rows,
                    "num_cols": t.num_cols,
                })

            layout_map[page_key] = {
                "page_num": page.page_num,
                "width": round(page.width, 2),
                "height": round(page.height, 2),
                "num_text_blocks": len(page.text_blocks),
                "num_headings": sum(1 for b in page.text_blocks if b.is_heading),
                "num_figures": len(page.figures),
                "num_tables": len(page_tables),
                "blocks": block_positions,
                "figures": figure_positions,
                "tables": table_positions,
            }

        # --- Section Tree ---
        section_tree = _build_section_tree(parsed_doc.pages, tables)

        # --- Page Metadata ---
        # Gather unique sections per page
        page_section_mapping = {}
        for page in parsed_doc.pages:
            sections = set()
            for block in page.text_blocks:
                if block.section_path:
                    sections.add(block.section_path)
            page_section_mapping[page.page_num] = sorted(sections)

        page_metadata = {
            "total_pages": len(parsed_doc.pages),
            "total_text_blocks": parsed_doc.total_text_blocks,
            "total_figures": parsed_doc.total_figures,
            "total_tables": len(tables),
            "page_sections": {
                str(k): v for k, v in page_section_mapping.items()
            },
            "pages": [
                {
                    "page_num": p.page_num,
                    "width": round(p.width, 2),
                    "height": round(p.height, 2),
                    "text_blocks": len(p.text_blocks),
                    "figures": len(p.figures),
                    "tables": sum(1 for t in tables if t.page == p.page_num),
                }
                for p in parsed_doc.pages
            ],
        }

    # --- Tables as individual dicts ---
    table_dicts = [table_to_dict(t) for t in tables]

    # --- Figures metadata + bytes ---
    figure_meta = []
    figure_bytes = {}
    for page in parsed_doc.pages:
        for fig in page.figures:
            figure_meta.append({
                "figure_id": fig.figure_id,
                "page": fig.page,
                "bbox": [float(x) for x in fig.bbox],
                "width": fig.width,
                "height": fig.height,
                "caption": fig.caption,
            })
            figure_bytes[fig.figure_id] = fig.image_bytes

    return StructuredOutput(
        structured_text=structured_text,
        layout_map=layout_map,
        page_metadata=page_metadata,
        section_tree=_section_nodes_to_dicts(section_tree),
        tables=table_dicts,
        figures=figure_meta,
        figure_bytes=figure_bytes,
    )


def _build_section_tree(
    pages: List[ParsedPage],
    tables: List[ExtractedTable],
) -> List[SectionNode]:
    """Build a hierarchical section tree from headings."""
    root_sections: List[SectionNode] = []
    stack: List[SectionNode] = []

    # Collect all headings with their font sizes
    headings = []
    for page in pages:
        for block in page.text_blocks:
            if block.is_heading:
                headings.append(block)

    if not headings:
        # No headings — create a single root section
        total_blocks = sum(len(p.text_blocks) for p in pages)
        total_figs = sum(len(p.figures) for p in pages)
        root = SectionNode(
            title="Document",
            level=0,
            path="Document",
            page_start=0,
            page_end=len(pages) - 1 if pages else 0,
            block_count=total_blocks,
            figure_count=total_figs,
            table_count=len(tables),
        )
        return [root]

    # Sort heading font sizes to determine levels
    unique_sizes = sorted(set(h.font_size for h in headings), reverse=True)
    size_to_level = {size: i + 1 for i, size in enumerate(unique_sizes)}

    for heading in headings:
        level = size_to_level[heading.font_size]
        title = heading.text.strip().replace("\n", " ")[:80]

        node = SectionNode(
            title=title,
            level=level,
            path="",
            page_start=heading.page,
            page_end=heading.page,
        )

        # Pop stack until we find a parent with a lower level number (higher hierarchy)
        while stack and stack[-1].level >= level:
            stack.pop()

        if stack:
            parent = stack[-1]
            parent.children.append(node)
            node.path = f"{parent.path} > {title}"
        else:
            root_sections.append(node)
            node.path = title

        stack.append(node)

    return root_sections


def _section_nodes_to_dicts(nodes: List[SectionNode]) -> List[dict]:
    """Recursively convert SectionNode tree to dicts."""
    result = []
    for node in nodes:
        d = {
            "title": node.title,
            "level": node.level,
            "path": node.path,
            "page_start": node.page_start,
            "page_end": node.page_end,
            "block_count": node.block_count,
            "figure_count": node.figure_count,
            "table_count": node.table_count,
        }
        if node.children:
            d["children"] = _section_nodes_to_dicts(node.children)
        result.append(d)
    return result


# Legacy compatibility
def build_structured_doc(text_blocks, tables):
    """Legacy wrapper for backward compat."""
    from preprocessing.layout_parser import TextBlock as TB

    class FakeDoc:
        pass

    structured_text = []
    for block in text_blocks:
        structured_text.append({
            "page": block.page,
            "section_path": block.section_path,
            "text": block.text,
            "bbox": list(block.bbox),
            "is_heading": block.is_heading,
            "font_size": block.font_size,
        })

    layout_map = {}
    pages_set = set(block.page for block in text_blocks)
    for page_num in pages_set:
        page_blocks = [b for b in text_blocks if b.page == page_num]
        layout_map[f"page_{page_num}"] = {
            "num_blocks": len(page_blocks),
            "num_headings": sum(1 for b in page_blocks if b.is_heading),
        }

    tables_dict = []
    for table in tables:
        tables_dict.append({
            "page": table.page,
            "headers": table.headers,
            "rows": table.rows,
            "bbox": list(table.bbox) if isinstance(table.bbox, tuple) else table.bbox,
        })

    class Result:
        pass

    r = Result()
    r.structured_text = structured_text
    r.layout_map = layout_map
    r.tables = tables_dict
    r.page_metadata = {
        "total_pages": len(pages_set),
        "total_text_blocks": len(text_blocks),
        "total_tables": len(tables),
    }
    return r


def structured_doc_to_json(doc) -> dict:
    """Legacy wrapper."""
    return {
        "structured_text": doc.structured_text,
        "layout_map": doc.layout_map,
        "tables": doc.tables,
        "page_metadata": doc.page_metadata,
    }
