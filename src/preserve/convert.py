"""Convert selected PDF pages to a directory of Markdown files."""

from __future__ import annotations

from pathlib import Path

from preserve.clean import drop_running_furniture
from preserve.model import PageDoc, PageSpec
from preserve.pdfpages import PdfSource, open_pdf
from preserve.readers.docling_reader import DoclingReader
from preserve.readers.vision import VisionReader, vision_configured
from preserve.writer import write_pages


def convert(
    pdf_path: Path,
    out_dir: Path,
    reader: str = "local",
    pages: list[PageSpec] | None = None,
    confidence: float = 0.55,
) -> list[PageDoc]:
    if reader not in {"local", "vision", "auto"}:
        raise SystemExit(f"unknown reader {reader!r}")
    vision = VisionReader.from_env()
    if reader == "vision" and vision is None:
        raise SystemExit(
            "the vision reader needs PRESERVE_VISION_BASE_URL and PRESERVE_VISION_MODEL"
        )
    local = DoclingReader() if reader in {"local", "auto"} else None
    docs: list[PageDoc] = []
    with open_pdf(pdf_path) as pdf:
        for index in pdf.resolve(pages):
            docs.append(_read_one(pdf, index, reader, local, vision, confidence))
    drop_running_furniture(docs)
    write_pages(docs, out_dir)
    return docs


def _read_one(
    pdf: PdfSource,
    index: int,
    reader: str,
    local: DoclingReader | None,
    vision: VisionReader | None,
    confidence: float,
) -> PageDoc:
    if reader == "vision":
        assert vision is not None
        return vision.read(pdf, index)
    assert local is not None
    page = local.read(pdf, index)
    if reader == "auto" and page.is_hard(confidence):
        if vision is None:
            page.warnings.append("hard page; vision reader is not configured")
            if not vision_configured():
                page.warnings.append("set PRESERVE_VISION_BASE_URL and PRESERVE_VISION_MODEL to escalate")
        else:
            escalated = vision.read(pdf, index)
            escalated.warnings.append("escalated from the local reader")
            return escalated
    return page
