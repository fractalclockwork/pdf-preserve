"""Local reader: Docling layout, full-page OCR, formulas, tables, and picture crops.

The Internet Archive text layer is not reused. `force_full_page_ocr` makes
every page an image.
"""

from __future__ import annotations

import io
from typing import Any

from preserve.latexfmt import tabular
from preserve.model import BBox, Block, BlockKind, PageDoc
from preserve.pdfpages import PdfSource

_LABEL_KIND = {
    "title": BlockKind.heading,
    "section_header": BlockKind.heading,
    "page_header": BlockKind.header,
    "page_footer": BlockKind.footer,
    "footnote": BlockKind.footnote,
    "formula": BlockKind.equation,
    "caption": BlockKind.caption,
    "picture": BlockKind.figure,
    "table": BlockKind.table,
    "list_item": BlockKind.prose,
    "text": BlockKind.prose,
    "code": BlockKind.prose,
    "paragraph": BlockKind.prose,
}


class DoclingReader:
    name = "local"

    def __init__(self) -> None:
        self._converter: Any = None

    def read(self, pdf: PdfSource, pdf_index: int) -> PageDoc:
        converter = self._converter or self._build()
        self._converter = converter
        pdf_page = pdf_index + 1
        result = converter.convert(str(pdf.path), page_range=(pdf_page, pdf_page))
        document = result.document
        page = PageDoc(
            label=pdf.label_of(pdf_index),
            pdf_page=pdf_page,
            pdf_index=pdf_index,
            source=str(pdf.path),
            reader=self.name,
        )
        page_height = pdf.doc[pdf_index].rect.height
        for item, level in document.iterate_items():
            block = _block_from_item(item, level, document, pdf, pdf_index, page_height)
            if block is not None:
                page.blocks.append(block)
        _attach_following_captions(page)
        mean = _result_confidence(result)
        if mean is not None:
            for block in page.blocks:
                if block.confidence is None:
                    block.confidence = mean
        return page

    def _build(self) -> Any:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise SystemExit("Docling is not installed. Run this tool with uv from preserve/.") from exc

        options = PdfPipelineOptions()
        options.do_ocr = True
        options.do_table_structure = True
        options.do_formula_enrichment = True
        options.generate_picture_images = True
        options.images_scale = 2.0
        options.table_structure_options = TableStructureOptions(do_cell_matching=True)
        options.ocr_options = _ocr_options()
        _set_device_auto(options)
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )


def _ocr_options() -> Any:
    from docling.datamodel.pipeline_options import EasyOcrOptions, RapidOcrOptions

    for cls in (RapidOcrOptions, EasyOcrOptions):
        try:
            opts = cls()
        except Exception:
            continue
        if hasattr(opts, "force_full_page_ocr"):
            opts.force_full_page_ocr = True
        return opts
    raise SystemExit("Docling has no OCR options class")


def _set_device_auto(options: Any) -> None:
    try:
        from docling.datamodel.pipeline_options import AcceleratorOptions
    except ImportError:
        return
    try:
        options.accelerator_options = AcceleratorOptions(device="auto")
    except TypeError:
        return


def _label_name(item: Any) -> str:
    label = getattr(item, "label", "")
    return str(getattr(label, "value", label)).lower()


def _bbox(item: Any, page_height: float) -> BBox | None:
    prov = getattr(item, "prov", None) or []
    if not prov:
        return None
    raw = prov[0].bbox
    origin = str(getattr(raw, "coord_origin", "")).lower()
    x0, y0, x1, y1 = float(raw.l), float(raw.t), float(raw.r), float(raw.b)
    if "bottom" in origin:
        y0, y1 = page_height - y1, page_height - y0
    top, bottom = sorted((y0, y1))
    left, right = sorted((x0, x1))
    return BBox(left, top, right, bottom)


def _picture_png(item: Any, document: Any, pdf: PdfSource, pdf_index: int, bbox: BBox | None) -> bytes | None:
    getter = getattr(item, "get_image", None)
    if getter is not None:
        try:
            image = getter(document)
        except TypeError:
            image = getter()
        if image is not None:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            data = buffer.getvalue()
            if data:
                return data
    if bbox is None:
        return None
    try:
        return pdf.crop_png(pdf_index, bbox.as_tuple())
    except ValueError:
        return None


def _table_rows(item: Any) -> list[list[str]]:
    data = getattr(item, "data", None)
    grid = getattr(data, "grid", None) if data is not None else None
    if not grid:
        return []
    rows: list[list[str]] = []
    for row in grid:
        cells = []
        for cell in row:
            cells.append(str(getattr(cell, "text", cell) or ""))
        rows.append(cells)
    return rows


def _caption(item: Any) -> str:
    cap = getattr(item, "caption", None)
    if cap is None:
        return ""
    if isinstance(cap, str):
        return cap
    text = getattr(cap, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    texts = []
    for child in getattr(item, "captions", []) or []:
        child_text = getattr(child, "text", None)
        if isinstance(child_text, str):
            texts.append(child_text)
    return " ".join(texts).strip()


def _block_from_item(
    item: Any,
    level: int,
    document: Any,
    pdf: PdfSource,
    pdf_index: int,
    page_height: float,
) -> Block | None:
    name = _label_name(item)
    if name in {"document", "page", "group", "list", "section"}:
        return None
    kind = _LABEL_KIND.get(name, BlockKind.prose)
    text = str(getattr(item, "text", "") or "").strip()
    bbox = _bbox(item, page_height)
    if kind is BlockKind.table:
        rows = _table_rows(item)
        caption = _caption(item) or text
        return Block(kind=kind, text=caption, latex=tabular(rows), bbox=bbox)
    if kind is BlockKind.figure:
        png = _picture_png(item, document, pdf, pdf_index, bbox)
        return Block(kind=kind, text=_caption(item), image_png=png, bbox=bbox)
    if kind is BlockKind.equation:
        latex = text
        if latex.startswith(r"\(") and latex.endswith(r"\)"):
            latex = latex[2:-2].strip()
        return Block(kind=kind, latex=latex, bbox=bbox)
    if kind is BlockKind.heading:
        return Block(kind=kind, text=text, level=max(level, 1), bbox=bbox)
    if not text and kind is not BlockKind.figure:
        return None
    return Block(kind=kind, text=text, bbox=bbox)


def _attach_following_captions(page: PageDoc) -> None:
    kept: list[Block] = []
    index = 0
    blocks = page.blocks
    while index < len(blocks):
        block = blocks[index]
        nxt = blocks[index + 1] if index + 1 < len(blocks) else None
        if (
            block.kind is BlockKind.figure
            and not block.text.strip()
            and nxt is not None
            and nxt.kind is BlockKind.caption
        ):
            block.text = nxt.text
            kept.append(block)
            index += 2
            continue
        if block.kind is BlockKind.caption:
            block.kind = BlockKind.prose
        kept.append(block)
        index += 1
    page.blocks = kept


def _result_confidence(result: Any) -> float | None:
    report = getattr(result, "confidence", None)
    if report is None:
        return None
    for attr in ("mean_score", "mean_grade", "score"):
        value = getattr(report, attr, None)
        if isinstance(value, (int, float)):
            return float(value)
    pages = getattr(report, "pages", None)
    if isinstance(pages, dict):
        scores = []
        for page in pages.values():
            for attr in ("mean_score", "ocr_score", "score"):
                value = getattr(page, attr, None)
                if isinstance(value, (int, float)):
                    scores.append(float(value))
                    break
        if scores:
            return sum(scores) / len(scores)
    return None
