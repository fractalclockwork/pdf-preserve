"""Command line for convert and score."""

from __future__ import annotations

import argparse
from pathlib import Path

from preserve.model import parse_page_list


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="preserve", description="Transcribe a scanned PDF into Markdown.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    convert_p = sub.add_parser("convert", help="write per-page Markdown for a scanned PDF")
    convert_p.add_argument("pdf", type=Path)
    convert_p.add_argument("out_dir", type=Path)
    convert_p.add_argument("--reader", choices=("local", "vision", "auto"), default="local")
    convert_p.add_argument("--pages", help="comma-separated labels, or pdf:N for a page with no label")
    convert_p.add_argument("--confidence", type=float, default=0.55, help="mean OCR confidence at or below this escalates in auto mode")

    score_p = sub.add_parser("score", help="convert the gold manifest and compare")
    score_p.add_argument("gold_dir", type=Path)
    score_p.add_argument("--reader", choices=("local", "vision", "auto"), default="local")

    args = parser.parse_args(argv)
    if args.cmd == "convert":
        from preserve.convert import convert

        pages = parse_page_list(args.pages) if args.pages else None
        docs = convert(args.pdf, args.out_dir, reader=args.reader, pages=pages, confidence=args.confidence)
        for doc in docs:
            warn = f" ({'; '.join(doc.warnings)})" if doc.warnings else ""
            print(f"{doc.label}\tpdf {doc.pdf_page}\t{doc.reader}\t{len(doc.blocks)} blocks{warn}")
        return
    from preserve.score import score

    score(args.gold_dir, reader=args.reader)


if __name__ == "__main__":
    main()
