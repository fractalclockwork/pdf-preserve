"""Checks for the writer, the scorer, and page cleanup. No PDF and no Docling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from preserve.clean import drop_running_furniture
from preserve.latexfmt import cell_accuracy, parse_tabular, tabular
from preserve.model import Block, BlockKind, PageDoc, parse_page_list
from preserve.score import cer, norm_latex, parse_markdown, regressed
from preserve.writer import write_pages


class PageListTest(unittest.TestCase):
    def test_labels_and_pdf_page(self) -> None:
        specs = parse_page_list("xi, 1, pdf:503")
        self.assertEqual(specs[0].label, "xi")
        self.assertEqual(specs[1].label, "1")
        self.assertEqual(specs[2].pdf_page, 503)


class HardPageTest(unittest.TestCase):
    def test_empty_formula_is_hard(self) -> None:
        page = PageDoc(label="1", pdf_page=1, pdf_index=0, source="x")
        page.blocks.append(Block(kind=BlockKind.equation, latex=""))
        self.assertTrue(page.is_hard())

    def test_low_confidence_is_hard(self) -> None:
        page = PageDoc(label="1", pdf_page=1, pdf_index=0, source="x")
        page.blocks.append(Block(kind=BlockKind.prose, text="hello", confidence=0.2))
        self.assertTrue(page.is_hard())

    def test_confident_prose_is_not_hard(self) -> None:
        page = PageDoc(label="1", pdf_page=1, pdf_index=0, source="x")
        page.blocks.append(Block(kind=BlockKind.prose, text="hello", confidence=0.9))
        self.assertFalse(page.is_hard())


class WriterScoreTest(unittest.TestCase):
    def test_round_trip_metrics(self) -> None:
        page = PageDoc(label="6", pdf_page=24, pdf_index=23, source="scan.pdf", reader="local")
        page.blocks = [
            Block(kind=BlockKind.header, text="6 Digital Computer Design Fundamentals"),
            Block(kind=BlockKind.heading, text="Table 1-3", level=2),
            Block(kind=BlockKind.equation, latex=r"N = b_{-1}2^{-1}"),
            Block(kind=BlockKind.table, text="Steps", latex=tabular([["a", "divide"], ["b", "again"]])),
            Block(kind=BlockKind.figure, text="FIG. 4-1 Veitch diagram", image_png=b"\x89PNG\r\n"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_pages([page], out)
            text = (out / "pages" / "6.md").read_text(encoding="utf-8")
            parsed = parse_markdown(text)
            self.assertIn("Table 1-3", parsed.prose)
            self.assertNotIn("Digital Computer", parsed.prose)
            self.assertEqual(parsed.equations, [norm_latex(r"N = b_{-1}2^{-1}")])
            self.assertEqual(parsed.tables[0][0][0], "a")
            self.assertTrue((out / "images" / "6-fig1.png").is_file())
            again = parse_markdown(text)
            edits = cer(again.prose, parsed.prose)
            self.assertEqual(edits, 0.0)

    def test_cell_accuracy_ignores_escape(self) -> None:
        gold = [["a & b", "c"]]
        hyp = parse_tabular(tabular(gold))
        matched, total = cell_accuracy(gold, hyp)
        self.assertEqual((matched, total), (2, 2))

    def test_regression(self) -> None:
        old = {
            "prose_cer": 0.40,
            "equation_match": 0.50,
            "table_cell_accuracy": 0.50,
            "figure_recall": 1.0,
        }
        self.assertEqual(regressed(old, old), [])
        worse = dict(old, prose_cer=0.50)
        self.assertEqual(regressed(old, worse), ["prose_cer"])
        better = dict(old, equation_match=0.80)
        self.assertEqual(regressed(old, better), [])


class FurnitureTest(unittest.TestCase):
    def test_repeated_edge_line_is_dropped(self) -> None:
        pages = []
        for label in ("2", "4", "8"):
            page = PageDoc(label=label, pdf_page=1, pdf_index=0, source="s")
            page.blocks = [
                Block(kind=BlockKind.prose, text="Digital Computer Design Fundamentals"),
                Block(kind=BlockKind.prose, text=f"body {label}"),
            ]
            pages.append(page)
        drop_running_furniture(pages)
        for page in pages:
            self.assertEqual(len(page.blocks), 1)
            self.assertTrue(page.blocks[0].text.startswith("body"))


class BaselineFileTest(unittest.TestCase):
    def test_first_write_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.json"
            path.write_text(json.dumps({"prose_cer": 0.1}) + "\n", encoding="utf-8")
            self.assertIn("prose_cer", json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
