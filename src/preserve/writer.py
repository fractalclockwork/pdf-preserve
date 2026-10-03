"""Write PageDoc files as Markdown with LaTeX math and tables."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from preserve.model import BlockKind, PageDoc


def _safe_label(label: str) -> str:
    cleaned = re.sub(r"[^\w.+-]+", "-", label.strip())
    return cleaned.strip("-") or "page"


def _alt(text: str) -> str:
    return text.replace("[", "(").replace("]", ")").replace("\n", " ").strip()


def write_pages(pages: list[PageDoc], out_dir: Path) -> list[Path]:
    pages_dir = out_dir / "pages"
    images_dir = out_dir / "images"
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest = []
    for page in pages:
        path = pages_dir / f"{_safe_label(page.label)}.md"
        path.write_text(_render(page, images_dir), encoding="utf-8")
        written.append(path)
        manifest.append(
            {
                "label": page.label,
                "pdf_page": page.pdf_page,
                "reader": page.reader,
                "file": str(path.relative_to(out_dir)),
                "warnings": page.warnings,
            }
        )
    (out_dir / "manifest.json").write_text(json.dumps({"pages": manifest}, indent=2) + "\n", encoding="utf-8")
    return written


def _render(page: PageDoc, images_dir: Path) -> str:
    meta = {
        "source": page.source,
        "pdf_page": page.pdf_page,
        "label": page.label,
        "reader": page.reader,
    }
    body = ["---", yaml.safe_dump(meta, sort_keys=False).strip(), "---", ""]
    figure_n = 0
    for block in page.blocks:
        if block.kind in {BlockKind.header, BlockKind.footer}:
            continue
        if block.kind is BlockKind.heading:
            level = min(max(block.level, 1), 4)
            body.append(f"{'#' * level} {block.text}")
            body.append("")
        elif block.kind is BlockKind.equation:
            latex = block.latex.strip()
            if latex.startswith("$$") and latex.endswith("$$") and len(latex) >= 4:
                latex = latex[2:-2].strip()
            if latex.startswith(r"\[") and latex.endswith(r"\]"):
                latex = latex[2:-2].strip()
            body.append(f"$$\n{latex}\n$$")
            body.append("")
        elif block.kind is BlockKind.table:
            if block.text:
                body.append(block.text)
                body.append("")
            body.append(block.latex.strip())
            body.append("")
        elif block.kind is BlockKind.figure:
            figure_n += 1
            name = f"{_safe_label(page.label)}-fig{figure_n}.png"
            if block.image_png:
                (images_dir / name).write_bytes(block.image_png)
            rel = f"../images/{name}"
            body.append(f"![{_alt(block.text)}]({rel})")
            body.append("")
        elif block.kind is BlockKind.footnote:
            body.append(block.text)
            body.append("")
        else:
            if block.text:
                body.append(block.text)
                body.append("")
    return "\n".join(body).rstrip() + "\n"
