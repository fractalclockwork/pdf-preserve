"""Optional vision reader. Off unless a base URL and a model are set.

Environment:
  PRESERVE_VISION_BASE_URL   OpenAI-compatible API root, or a full /chat/completions URL
  PRESERVE_VISION_MODEL      model id
  PRESERVE_VISION_API_KEY    optional bearer token
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from preserve.latexfmt import tabular
from preserve.model import Block, BlockKind, PageDoc
from preserve.pdfpages import PdfSource

_KINDS = {kind.value: kind for kind in BlockKind}
_PROMPT = """Read this scanned page into JSON. Preserve the reading order.
Return only JSON of the form {"blocks":[...]}.
Each block has "kind" (prose, heading, equation, table, figure, caption, footnote, header, footer).
Equations use "latex" with no surrounding dollars.
Tables use "rows", a list of lists of cell strings. Math inside a cell stays in $...$.
Figures use "caption".
Headings use "text" and "level" (1-4).
Other kinds use "text".
Do not add a running header or a page number as prose.
"""


def vision_configured() -> bool:
    return bool(os.environ.get("PRESERVE_VISION_BASE_URL") and os.environ.get("PRESERVE_VISION_MODEL"))


class VisionReader:
    name = "vision"

    def __init__(self, base_url: str, model: str, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    @classmethod
    def from_env(cls) -> VisionReader | None:
        base = os.environ.get("PRESERVE_VISION_BASE_URL")
        model = os.environ.get("PRESERVE_VISION_MODEL")
        if not base or not model:
            return None
        return cls(base, model, os.environ.get("PRESERVE_VISION_API_KEY"))

    def read(self, pdf: PdfSource, pdf_index: int) -> PageDoc:
        png = pdf.render_png(pdf_index)
        payload = self._request(png)
        page = PageDoc(
            label=pdf.label_of(pdf_index),
            pdf_page=pdf_index + 1,
            pdf_index=pdf_index,
            source=str(pdf.path),
            reader=self.name,
        )
        for raw in payload.get("blocks", []):
            block = _block_from_json(raw, pdf, pdf_index)
            if block is not None:
                page.blocks.append(block)
        return page

    def _endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    def _request(self, png: bytes) -> dict:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + base64.standard_b64encode(png).decode()},
                        },
                    ],
                }
            ],
        }
        data = json.dumps(body).encode()
        request = urllib.request.Request(self._endpoint(), data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = json.loads(response.read().decode())
        except urllib.error.URLError as exc:
            raise SystemExit(f"vision reader request failed: {exc}") from exc
        content = raw["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return _parse_json(str(content))


def _parse_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise SystemExit("vision reader returned JSON that is not an object")
    return parsed


def _block_from_json(raw: object, pdf: PdfSource, pdf_index: int) -> Block | None:
    if not isinstance(raw, dict):
        return None
    kind = _KINDS.get(str(raw.get("kind", "prose")))
    if kind is None:
        return None
    text = str(raw.get("text") or raw.get("caption") or "").strip()
    if kind is BlockKind.equation:
        return Block(kind=kind, latex=str(raw.get("latex") or "").strip())
    if kind is BlockKind.table:
        rows = raw.get("rows") or []
        grid = [[str(cell) for cell in row] for row in rows if isinstance(row, list)]
        return Block(kind=kind, text=text, latex=tabular(grid))
    if kind is BlockKind.figure:
        png = _crop_normalized(pdf, pdf_index, raw.get("bbox"))
        if png is None:
            png = pdf.render_png(pdf_index)
        return Block(kind=kind, text=text, image_png=png)
    if kind is BlockKind.heading:
        level = raw.get("level", 1)
        try:
            level_n = int(level)
        except (TypeError, ValueError):
            level_n = 1
        return Block(kind=kind, text=text, level=level_n)
    if not text:
        return None
    return Block(kind=kind, text=text)


def _crop_normalized(pdf: PdfSource, pdf_index: int, bbox: object) -> bytes | None:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    rect = pdf.doc[pdf_index].rect
    if max(x0, y0, x1, y1) <= 1.5:
        x0, x1 = x0 * rect.width, x1 * rect.width
        y0, y1 = y0 * rect.height, y1 * rect.height
    try:
        return pdf.crop_png(pdf_index, (x0, y0, x1, y1))
    except ValueError:
        return None
