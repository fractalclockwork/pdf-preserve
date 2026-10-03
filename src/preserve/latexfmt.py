"""LaTeX table formatting and parsing shared by the writer and the scorer."""

from __future__ import annotations

import re


_ESCAPES = (
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
)


def escape_cell(text: str) -> str:
    """Escape LaTeX specials in a table cell, leaving `$...$` math alone."""
    text = text.replace("\n", " ").strip()
    parts = re.split(r"(\$[^$]*\$)", text)
    out: list[str] = []
    for part in parts:
        if len(part) >= 2 and part.startswith("$") and part.endswith("$"):
            out.append(part)
            continue
        for char, repl in _ESCAPES:
            part = part.replace(char, repl)
        out.append(part)
    return "".join(out)


def tabular(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    spec = "|" + "|".join("l" for _ in range(width)) + "|"
    lines = [r"\begin{tabular}{" + spec + "}", r"\hline"]
    for row in padded:
        cells = " & ".join(escape_cell(cell) for cell in row)
        lines.append(cells + r" \\")
        lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    return "\n".join(lines)


def _split_top(text: str, sep: str) -> list[str]:
    """Split on `sep` at brace depth zero. `sep` is `\\` or `&`."""
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\":
            if sep == r"\\" and text.startswith(r"\\", i) and depth == 0:
                parts.append(text[start:i])
                i += 2
                start = i
                continue
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        elif char == "&" and sep == "&" and depth == 0:
            parts.append(text[start:i])
            i += 1
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return parts


def parse_tabular(src: str) -> list[list[str]]:
    """Parse one tabular environment into a grid of cell strings."""
    match = re.search(r"\\begin\{tabular\}\{[^}]*\}(.*)\\end\{tabular\}", src, re.DOTALL)
    if not match:
        return []
    inner = match.group(1)
    inner = re.sub(r"\\hline", "", inner)
    rows: list[list[str]] = []
    for raw in _split_top(inner, r"\\"):
        if not raw.strip():
            continue
        cells = [re.sub(r"\s+", " ", cell).strip() for cell in _split_top(raw, "&")]
        if any(cells):
            rows.append(cells)
    return rows


def norm_cell(text: str) -> str:
    text = (
        text.replace(r"\&", "&")
        .replace(r"\%", "%")
        .replace(r"\#", "#")
        .replace(r"\_", "_")
    )
    return re.sub(r"\s+", " ", text).strip().casefold()


def cell_accuracy(gold_rows: list[list[str]], hyp_rows: list[list[str]]) -> tuple[int, int]:
    """Return (matching cells, gold cells) for one table pair, aligned from the top left."""
    gold_n = sum(len(row) for row in gold_rows)
    if gold_n == 0:
        return (0, 0)
    matched = 0
    for r, grow in enumerate(gold_rows):
        hrow = hyp_rows[r] if r < len(hyp_rows) else []
        for c, gcell in enumerate(grow):
            hcell = hrow[c] if c < len(hrow) else ""
            if norm_cell(gcell) == norm_cell(hcell):
                matched += 1
    return matched, gold_n
