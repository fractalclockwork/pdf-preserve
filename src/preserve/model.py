"""Shared page model. Both readers fill this; one writer emits Markdown."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BlockKind(str, Enum):
    prose = "prose"
    heading = "heading"
    equation = "equation"
    table = "table"
    figure = "figure"
    caption = "caption"
    footnote = "footnote"
    header = "header"
    footer = "footer"


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass
class Block:
    kind: BlockKind
    text: str = ""
    latex: str = ""
    bbox: BBox | None = None
    image_png: bytes | None = None
    confidence: float | None = None
    level: int = 1

    def body_empty(self) -> bool:
        if self.kind is BlockKind.table:
            return not self.latex.strip()
        if self.kind is BlockKind.equation:
            return not self.latex.strip()
        if self.kind is BlockKind.figure:
            return self.image_png is None and not self.text.strip()
        return not self.text.strip() and not self.latex.strip()


# Mean OCR confidence at or below this marks a page as hard.
HARD_CONFIDENCE = 0.55


@dataclass
class PageDoc:
    label: str
    pdf_page: int
    pdf_index: int
    source: str
    blocks: list[Block] = field(default_factory=list)
    reader: str = "local"
    warnings: list[str] = field(default_factory=list)

    def mean_confidence(self) -> float | None:
        values = [block.confidence for block in self.blocks if block.confidence is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def is_hard(self, threshold: float = HARD_CONFIDENCE) -> bool:
        """A page the local reader should hand to the vision reader.

        Hard means low mean OCR confidence, a table or picture with an empty
        body, or a formula region that produced no LaTeX.
        """
        mean = self.mean_confidence()
        if mean is not None and mean <= threshold:
            return True
        for block in self.blocks:
            if block.kind is BlockKind.table and not block.latex.strip():
                return True
            if block.kind is BlockKind.figure and block.image_png is None:
                return True
            if block.kind is BlockKind.equation and not block.latex.strip():
                return True
        return False


@dataclass(frozen=True)
class PageSpec:
    """A requested page, by printed label or by 1-based PDF page."""

    label: str | None = None
    pdf_page: int | None = None

    def __post_init__(self) -> None:
        if self.label is None and self.pdf_page is None:
            raise ValueError("a page spec needs a label or a pdf page")


def parse_page_list(spec: str) -> list[PageSpec]:
    pages: list[PageSpec] = []
    for raw in spec.split(","):
        item = raw.strip()
        if not item:
            continue
        if item.startswith("pdf:"):
            pages.append(PageSpec(pdf_page=int(item[4:])))
        else:
            pages.append(PageSpec(label=item))
    if not pages:
        raise ValueError(f"no pages in {spec!r}")
    return pages
