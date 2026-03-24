"""
Layout-aware PDF parser using PyMuPDF.
Extracts text blocks, figures (images), and reading order from PDF pages.
Merges spans into paragraphs, detects headings, and extracts embedded images.
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import structlog

logger = structlog.get_logger()


@dataclass
class TextBlock:
    """A merged paragraph-level text block."""
    page: int
    text: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    is_heading: bool
    font_size: float
    font_name: str = ""
    is_bold: bool = False
    section_path: str = ""


@dataclass
class FigureBlock:
    """An extracted figure/image from the PDF."""
    page: int
    figure_id: str              # e.g. "fig_0_1"
    bbox: Tuple[float, float, float, float]
    image_bytes: bytes          # PNG bytes
    width: int
    height: int
    caption: str = ""           # nearby text if detected


@dataclass
class ParsedPage:
    """All extracted content from a single PDF page."""
    page_num: int
    width: float
    height: float
    text_blocks: List[TextBlock] = field(default_factory=list)
    figures: List[FigureBlock] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Complete parsed document."""
    pages: List[ParsedPage] = field(default_factory=list)
    total_text_blocks: int = 0
    total_figures: int = 0


def _merge_block_spans(block: dict, page_num: int) -> Optional[TextBlock]:
    """
    Merge all spans in a PyMuPDF text block into a single TextBlock.
    Groups lines together to form paragraph-level blocks.
    """
    lines_text = []
    font_sizes = []
    font_names = []
    bold_count = 0
    total_spans = 0

    for line in block.get("lines", []):
        span_texts = []
        for span in line.get("spans", []):
            text = span.get("text", "").strip()
            if not text:
                continue
            span_texts.append(text)
            font_sizes.append(span.get("size", 12.0))
            font_names.append(span.get("font", ""))
            flags = span.get("flags", 0)
            if flags & (1 << 4):  # bit 4 = bold
                bold_count += 1
            total_spans += 1

        if span_texts:
            lines_text.append(" ".join(span_texts))

    if not lines_text:
        return None

    full_text = "\n".join(lines_text)
    avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
    primary_font = max(set(font_names), key=font_names.count) if font_names else ""
    is_bold = bold_count > total_spans / 2

    bbox = block.get("bbox", (0, 0, 0, 0))

    return TextBlock(
        page=page_num,
        text=full_text,
        bbox=tuple(bbox),
        is_heading=False,  # determined later
        font_size=avg_font_size,
        font_name=primary_font,
        is_bold=is_bold,
    )


def _extract_figures(page: fitz.Page, page_num: int) -> List[FigureBlock]:
    """Extract embedded images from a PDF page as PNG bytes."""
    figures = []
    image_list = page.get_images(full=True)

    for idx, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = page.parent.extract_image(xref)
            if not base_image or not base_image.get("image"):
                continue

            image_bytes = base_image["image"]
            img_ext = base_image.get("ext", "png")
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)

            # Skip tiny images (icons, bullets, etc.)
            if width < 50 or height < 50:
                continue

            # Convert to PNG if not already
            if img_ext != "png":
                pix = fitz.Pixmap(page.parent, xref)
                if pix.n > 4:  # CMYK → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                image_bytes = pix.tobytes("png")
                pix = None  # free memory

            # Try to find the image bbox on the page
            bbox = (0, 0, float(width), float(height))
            for img_rect in page.get_image_rects(xref):
                bbox = (
                    float(img_rect.x0), float(img_rect.y0),
                    float(img_rect.x1), float(img_rect.y1),
                )
                break

            figure_id = f"fig_{page_num}_{idx + 1}"

            figures.append(FigureBlock(
                page=page_num,
                figure_id=figure_id,
                bbox=bbox,
                image_bytes=image_bytes,
                width=width,
                height=height,
            ))

        except Exception as e:
            logger.warning(
                "Failed to extract image",
                page=page_num, xref=xref, error=str(e)
            )
            continue

    return figures


def parse_pdf(
    pdf_bytes: Optional[bytes] = None,
    doc: Optional[fitz.Document] = None,
) -> ParsedDocument:
    """
    Parse PDF with layout awareness.

    Extracts:
    - Text blocks (merged spans → paragraphs) sorted in reading order
    - Figures/images as PNG bytes
    - Heading detection via font size analysis

    Args:
        pdf_bytes: Raw PDF file bytes (required when doc is not provided)
        doc: Optional pre-opened PyMuPDF document to avoid re-opening work

    Returns:
        ParsedDocument with pages containing text blocks and figures
    """
    close_doc = False
    if doc is None:
        if pdf_bytes is None:
            raise ValueError("Either pdf_bytes or doc must be provided")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        close_doc = True

    parsed_pages = []
    all_font_sizes = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_rect = page.rect
        text_dict = page.get_text("dict")

        page_text_blocks = []

        # Extract text blocks (type 0)
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            merged = _merge_block_spans(block, page_num)
            if merged:
                page_text_blocks.append(merged)
                all_font_sizes.append(merged.font_size)

        # Sort by reading order: top-to-bottom, left-to-right
        # Use y-midpoint with tolerance band for column detection
        if page_text_blocks:
            line_height = (
                sum(b.bbox[3] - b.bbox[1] for b in page_text_blocks)
                / len(page_text_blocks)
            )
            tolerance = line_height * 0.5

            def reading_order_key(block):
                y_mid = (block.bbox[1] + block.bbox[3]) / 2
                # Quantize y to tolerance bands for column handling
                y_band = int(y_mid / tolerance) if tolerance > 0 else y_mid
                x_start = block.bbox[0]
                return (y_band, x_start)

            page_text_blocks.sort(key=reading_order_key)

        # Extract figures
        page_figures = _extract_figures(page, page_num)

        parsed_pages.append(ParsedPage(
            page_num=page_num,
            width=float(page_rect.width),
            height=float(page_rect.height),
            text_blocks=page_text_blocks,
            figures=page_figures,
        ))

    if close_doc:
        doc.close()

    # Heading detection: font size > median * 1.3 OR bold with larger font
    if all_font_sizes:
        median_font_size = sorted(all_font_sizes)[len(all_font_sizes) // 2]
        heading_threshold = median_font_size * 1.3

        for page in parsed_pages:
            for block in page.text_blocks:
                if block.font_size >= heading_threshold or (
                    block.is_bold and block.font_size > median_font_size
                ):
                    block.is_heading = True

    # Assign section paths via heading hierarchy
    _assign_section_paths(parsed_pages)

    total_text = sum(len(p.text_blocks) for p in parsed_pages)
    total_figs = sum(len(p.figures) for p in parsed_pages)
    logger.info(
        "PDF parsed",
        pages=len(parsed_pages),
        text_blocks=total_text,
        figures=total_figs,
    )

    return ParsedDocument(
        pages=parsed_pages,
        total_text_blocks=total_text,
        total_figures=total_figs,
    )


def _assign_section_paths(pages: List[ParsedPage]):
    """
    Walk all text blocks across pages and assign hierarchical section paths
    based on heading detection and font sizes.
    """
    section_stack: List[Tuple[float, str]] = []  # (font_size, title)
    section_counter = 0

    for page in pages:
        for block in page.text_blocks:
            if block.is_heading:
                section_counter += 1
                title = block.text.strip().replace("\n", " ")[:60]

                # Pop sections of equal or smaller font size (move up the tree)
                while (
                    section_stack
                    and section_stack[-1][0] <= block.font_size
                ):
                    section_stack.pop()

                section_stack.append((block.font_size, title))

            # Build path from stack
            if section_stack:
                block.section_path = " > ".join(
                    s[1] for s in section_stack
                )
            else:
                block.section_path = "Introduction"


# Keep backward compatibility alias
def parse_layout(pdf_bytes: bytes) -> list:
    """Legacy wrapper — returns flat list of TextBlock for backward compat."""
    result = parse_pdf(pdf_bytes=pdf_bytes)
    blocks = []
    for page in result.pages:
        blocks.extend(page.text_blocks)
    return blocks
