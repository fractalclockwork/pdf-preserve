"""Score a conversion against hand-checked gold pages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from preserve.convert import convert
from preserve.latexfmt import cell_accuracy, norm_cell, parse_tabular
from preserve.model import parse_page_list

# A gold equation counts as matched when normalized LaTeX is this close.
EQUATION_CER = 0.2
# A gold figure counts as found when its caption is this close and a crop exists.
CAPTION_CER = 0.5
REGRESSION_TOLERANCE = 0.01

_SUMMARY_KEYS = ("prose_cer", "equation_match", "table_cell_accuracy", "figure_recall")
_LOWER_BETTER = {"prose_cer"}


@dataclass
class ParsedPage:
    prose: str
    equations: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    figures: list[tuple[str, str | None]] = field(default_factory=list)


def score(gold_dir: Path, reader: str = "local") -> dict:
    manifest_path = gold_dir / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    source = (gold_dir / manifest["source"]).resolve()
    specs = []
    gold_files = []
    for entry in manifest["pages"]:
        specs.extend(parse_page_list(str(entry["page"])))
        gold_files.append(gold_dir / entry["gold"])
    out_dir = gold_dir.parents[1] / "out" / "score" / gold_dir.name
    convert(source, out_dir, reader=reader, pages=specs)
    report = _compare(gold_files, out_dir / "pages")
    report["source"] = str(source)
    report["output"] = str(out_dir)
    _finish(gold_dir / "baseline.json", report)
    return report


def _compare(gold_files: list[Path], pages_dir: Path) -> dict:
    prose_edits = 0
    prose_chars = 0
    eq_hit = 0
    eq_total = 0
    cell_hit = 0
    cell_total = 0
    fig_hit = 0
    fig_total = 0
    pages = []
    for gold_path in gold_files:
        hyp_path = pages_dir / gold_path.name
        gold = parse_markdown(gold_path.read_text(encoding="utf-8"))
        hyp = parse_markdown(hyp_path.read_text(encoding="utf-8")) if hyp_path.exists() else ParsedPage(prose="")
        image_root = hyp_path.parent
        page_report = _page_score(gold, hyp, image_root)
        pages.append({"gold": gold_path.name, **page_report})
        prose_edits += page_report["prose_edits"]
        prose_chars += page_report["prose_chars"]
        eq_hit += page_report["equations_matched"]
        eq_total += page_report["equations"]
        cell_hit += page_report["cells_matched"]
        cell_total += page_report["cells"]
        fig_hit += page_report["figures_found"]
        fig_total += page_report["figures"]
    return {
        "prose_cer": _rate(prose_edits, prose_chars, empty=0.0),
        "equation_match": _rate(eq_hit, eq_total, empty=1.0),
        "table_cell_accuracy": _rate(cell_hit, cell_total, empty=1.0),
        "figure_recall": _rate(fig_hit, fig_total, empty=1.0),
        "pages": pages,
    }


def _rate(numer: int, denom: int, empty: float) -> float:
    if denom == 0:
        return empty
    return numer / denom


def _page_score(gold: ParsedPage, hyp: ParsedPage, image_root: Path) -> dict:
    edits = _edit_distance(hyp.prose, gold.prose)
    eq_hit, eq_total = _match_equations(gold.equations, hyp.equations)
    cell_hit, cell_total = _match_tables(gold.tables, hyp.tables)
    fig_hit, fig_total = _match_figures(gold.figures, hyp.figures, image_root)
    return {
        "prose_cer": _rate(edits, len(gold.prose), empty=0.0 if not hyp.prose else 1.0),
        "prose_edits": edits,
        "prose_chars": len(gold.prose),
        "equations_matched": eq_hit,
        "equations": eq_total,
        "cells_matched": cell_hit,
        "cells": cell_total,
        "figures_found": fig_hit,
        "figures": fig_total,
    }


def parse_markdown(text: str) -> ParsedPage:
    body = _strip_front_matter(text)
    equations = [norm_latex(chunk) for chunk in re.findall(r"\$\$(.+?)\$\$", body, re.DOTALL)]
    body = re.sub(r"\$\$.+?\$\$", " ", body, flags=re.DOTALL)
    tables = []
    for chunk in re.findall(r"\\begin\{tabular\}.*?\\end\{tabular\}", body, re.DOTALL):
        tables.append(parse_tabular(chunk))
    body = re.sub(r"\\begin\{tabular\}.*?\\end\{tabular\}", " ", body, flags=re.DOTALL)
    figures = []
    for alt, path in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", body):
        figures.append((alt.strip(), path.strip()))
    body = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", body)
    body = re.sub(r"\$([^$]+)\$", " ", body)
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.MULTILINE)
    prose = re.sub(r"\s+", " ", body).strip()
    return ParsedPage(prose=prose, equations=equations, tables=tables, figures=figures)


def _strip_front_matter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[end + 4 :]
    return text


def norm_latex(src: str) -> str:
    text = src.strip()
    text = re.sub(r"\\qquad.*", "", text)
    text = re.sub(r"\\(?:left|right|displaystyle)\b", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def _edit_distance(hyp: str, ref: str) -> int:
    if hyp == ref:
        return 0
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)
    prev = list(range(len(hyp) + 1))
    for i, rchar in enumerate(ref, start=1):
        cur = [i]
        for j, hchar in enumerate(hyp, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (rchar != hchar)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def cer(hyp: str, ref: str) -> float:
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(hyp, ref) / len(ref)


def _match_equations(gold: list[str], hyp: list[str]) -> tuple[int, int]:
    unused = set(range(len(hyp)))
    hit = 0
    for equation in gold:
        found = None
        for index in unused:
            if equation == hyp[index] or cer(hyp[index], equation) <= EQUATION_CER:
                found = index
                break
        if found is not None:
            unused.remove(found)
            hit += 1
    return hit, len(gold)


def _match_tables(gold: list[list[list[str]]], hyp: list[list[list[str]]]) -> tuple[int, int]:
    """Greedy one-to-one table match. Each gold table takes the unused hyp table
    with the most matching cells."""
    unused = set(range(len(hyp)))
    hit = 0
    total = 0
    for grows in gold:
        gold_n = sum(len(row) for row in grows)
        total += gold_n
        best_i = None
        best_hit = -1
        for index in unused:
            matched, _ = cell_accuracy(grows, hyp[index])
            if matched > best_hit:
                best_hit = matched
                best_i = index
        if best_i is not None:
            unused.remove(best_i)
            hit += best_hit
    return hit, total


def _match_figures(
    gold: list[tuple[str, str | None]],
    hyp: list[tuple[str, str | None]],
    image_root: Path,
) -> tuple[int, int]:
    unused = set(range(len(hyp)))
    hit = 0
    for alt, _path in gold:
        found = None
        for index in unused:
            hyp_alt, hyp_path = hyp[index]
            if hyp_path is None:
                continue
            image = (image_root / hyp_path).resolve()
            if not image.is_file() or image.stat().st_size == 0:
                continue
            if not alt.strip() or cer(norm_cell(hyp_alt), norm_cell(alt)) <= CAPTION_CER:
                found = index
                break
        if found is not None:
            unused.remove(found)
            hit += 1
    return hit, len(gold)


def regressed(old: dict, new: dict, tolerance: float = REGRESSION_TOLERANCE) -> list[str]:
    bad = []
    for key in _SUMMARY_KEYS:
        if key not in old or key not in new:
            continue
        if key in _LOWER_BETTER:
            if new[key] > old[key] + tolerance:
                bad.append(key)
        elif new[key] < old[key] - tolerance:
            bad.append(key)
    return bad


def _finish(baseline_path: Path, report: dict) -> None:
    summary = {key: report[key] for key in _SUMMARY_KEYS}
    print(_format_report(report))
    if not baseline_path.exists():
        baseline_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"recorded baseline {baseline_path}")
        return
    old = json.loads(baseline_path.read_text(encoding="utf-8"))
    bad = regressed(old, summary)
    if bad:
        raise SystemExit(f"regression against {baseline_path.name}: {', '.join(bad)}")
    print(f"no regression against {baseline_path.name}")


def _format_report(report: dict) -> str:
    lines = [
        f"prose_cer {report['prose_cer']:.3f}",
        f"equation_match {report['equation_match']:.3f}",
        f"table_cell_accuracy {report['table_cell_accuracy']:.3f}",
        f"figure_recall {report['figure_recall']:.3f}",
    ]
    for page in report["pages"]:
        lines.append(
            f"  {page['gold']}: cer {page['prose_cer']:.3f}"
            f" eq {page['equations_matched']}/{page['equations']}"
            f" cells {page['cells_matched']}/{page['cells']}"
            f" fig {page['figures_found']}/{page['figures']}"
        )
    return "\n".join(lines)
