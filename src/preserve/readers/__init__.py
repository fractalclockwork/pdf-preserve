"""Reader protocol."""

from __future__ import annotations

from typing import Protocol

from preserve.model import PageDoc
from preserve.pdfpages import PdfSource


class Reader(Protocol):
    name: str

    def read(self, pdf: PdfSource, pdf_index: int) -> PageDoc:
        """Read one PDF page into a PageDoc."""
