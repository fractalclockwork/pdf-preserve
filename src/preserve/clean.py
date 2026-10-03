"""Page cleanup that does not depend on a particular book."""

from __future__ import annotations

import re
from collections import Counter

from preserve.model import Block, BlockKind, PageDoc

_FURNITURE = {BlockKind.header, BlockKind.footer}


def dehyphenate(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"([A-Za-z])-\n\s*([a-z])", r"\1\2", text)
    return text


def flatten(text: str) -> str:
    text = dehyphenate(text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r" +", " ", text).strip()


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def drop_running_furniture(pages: list[PageDoc]) -> None:
    """Drop layout headers and footers, and edge lines that repeat across pages."""
    edge: Counter[str] = Counter()
    for page in pages:
        visible = [block for block in page.blocks if block.kind not in _FURNITURE and block.text.strip()]
        if not visible:
            continue
        for block in (visible[0], visible[-1]):
            key = _key(block.text)
            if key and len(key) <= 80:
                edge[key] += 1
    repeated = {key for key, count in edge.items() if count >= 2 and count / len(pages) >= 0.3}
    for page in pages:
        kept: list[Block] = []
        for index, block in enumerate(page.blocks):
            if block.kind in _FURNITURE:
                continue
            at_edge = index == 0 or index == len(page.blocks) - 1
            if at_edge and _key(block.text) in repeated and block.kind in {BlockKind.prose, BlockKind.heading}:
                continue
            if block.kind in {BlockKind.prose, BlockKind.heading, BlockKind.footnote, BlockKind.caption}:
                block.text = flatten(block.text)
            kept.append(block)
        page.blocks = [block for block in kept if not (block.kind is not BlockKind.figure and block.body_empty())]
