"""Open a scanned PDF and address pages by their printed labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from preserve.model import PageSpec


@dataclass
class PdfSource:
    path: Path
    doc: pymupdf.Document

    def close(self) -> None:
        self.doc.close()

    def __enter__(self) -> PdfSource:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def label_of(self, pdf_index: int) -> str:
        label = self.doc[pdf_index].get_label() or ""
        if label.strip():
            return label.strip()
        return f"pdf-{pdf_index + 1}"

    def index_for(self, spec: PageSpec) -> int:
        if spec.pdf_page is not None:
            index = spec.pdf_page - 1
            if not 0 <= index < self.doc.page_count:
                raise ValueError(f"pdf page {spec.pdf_page} is outside 1..{self.doc.page_count}")
            return index
        assert spec.label is not None
        matches = [
            i for i in range(self.doc.page_count) if (self.doc[i].get_label() or "").strip() == spec.label
        ]
        if not matches:
            raise ValueError(f"no page labeled {spec.label!r}")
        return matches[0]

    def resolve(self, specs: list[PageSpec] | None) -> list[int]:
        if not specs:
            return list(range(self.doc.page_count))
        return [self.index_for(spec) for spec in specs]

    def render_png(self, pdf_index: int, zoom: float = 2.0) -> bytes:
        matrix = pymupdf.Matrix(zoom, zoom)
        return self.doc[pdf_index].get_pixmap(matrix=matrix, colorspace=pymupdf.csRGB, alpha=False).tobytes("png")

    def crop_png(self, pdf_index: int, rect: tuple[float, float, float, float], zoom: float = 2.0) -> bytes:
        """Crop a region. `rect` is top-left origin, in PDF points, matching PyMuPDF."""
        clip = pymupdf.Rect(*rect)
        page = self.doc[pdf_index]
        clip = clip & page.rect
        if clip.is_empty or clip.width < 2 or clip.height < 2:
            raise ValueError("crop rectangle is empty")
        matrix = pymupdf.Matrix(zoom, zoom)
        return page.get_pixmap(matrix=matrix, clip=clip, colorspace=pymupdf.csRGB, alpha=False).tobytes("png")


def open_pdf(path: Path) -> PdfSource:
    return PdfSource(path=path, doc=pymupdf.open(path))
