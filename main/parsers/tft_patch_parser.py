from __future__ import annotations

import re
from bs4 import BeautifulSoup
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, TypedDict


# -----------------------------
# Public "block" shape (for DB)
# -----------------------------

class PatchBlock(TypedDict):
    category: str          # overview/champions/items/traits/augments/other
    size: str              # all/large/small
    h2: str                # e.g. "LARGE CHANGES"
    h4: str                # e.g. "UNITS: Tier 1"
    order: int             # stable ordering
    text: str              # readable body
    lines: List[str]       # bullet lines (if ul)
    unit_tier: Optional[int]  # extracted from "UNITS: Tier 1" etc


@dataclass
class Bucket:
    # each of these is a list of "blocks" (strings)
    all: List[str]
    large: List[str]
    small: List[str]


def _mk_buckets() -> Dict[str, Bucket]:
    return {
        "overview": Bucket(all=[], large=[], small=[]),
        "champions": Bucket(all=[], large=[], small=[]),
        "items": Bucket(all=[], large=[], small=[]),
        "traits": Bucket(all=[], large=[], small=[]),
        "augments": Bucket(all=[], large=[], small=[]),
        "other": Bucket(all=[], large=[], small=[]),
    }


def _clean_text(s: str) -> str:
    lines = [ln.rstrip() for ln in (s or "").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _render_node_as_text(node) -> str:
    return _clean_text(node.get_text("\n", strip=True))


def _major_group_from_h2(title: str) -> str:
    t = (title or "").strip().upper()
    if "LARGE CHANGES" in t:
        return "large"
    if "SMALL CHANGES" in t:
        return "small"
    return "all"


def _category_from_h4(title: str) -> str:
    t = (title or "").strip().upper()

    if t.startswith("UNITS:"):
        return "champions"
    if t in {"TRAITS"}:
        return "traits"
    if t in {"AUGMENTS"}:
        return "augments"

    if t in {"CORE ITEMS", "RADIANT ITEMS", "ARTIFACTS", "EMBLEMS"}:
        return "items"

    return "other"


def _extract_unit_tier(h4_title: str) -> Optional[int]:
    """
    Extracts tier from strings like:
      "UNITS: Tier 1" / "UNITS: TIER 2" / "UNITS: Tier 3"
    """
    if not h4_title:
        return None
    m = re.search(r"\bTIER\s*(\d+)\b", h4_title.strip().upper())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _append_bucket_block(
    buckets: Dict[str, Bucket],
    cat: str,
    size: str,
    heading: str,
    body: str,
) -> None:
    body = _clean_text(body)
    if not body:
        return

    block = f"{heading}\n{body}".strip() if heading else body
    buckets[cat].all.append(block)
    if size == "large":
        buckets[cat].large.append(block)
    elif size == "small":
        buckets[cat].small.append(block)


# =========================================================
# NEW: Structured blocks for saving PatchSection rows
# =========================================================
def parse_tft_patch_blocks(raw_html: str) -> List[PatchBlock]:
    """
    Returns a list of structured blocks, preserving:
      - Large/Small (from H2)
      - Subheading (H4, e.g. "UNITS: Tier 1")
      - Order in document
      - Bullet lines (UL -> LI list)
      - Optional unit_tier (from H4)

    This is what you save into PatchSection.
    """
    if not raw_html:
        return []

    soup = BeautifulSoup(raw_html, "html.parser")
    root = soup.select_one("#patch-notes-container") or soup

    blocks: List[PatchBlock] = []
    order = 0

    # Overview: intro + designers (we store as a single overview block)
    intro = root.select_one("blockquote.blockquote.context")
    designers = root.select_one(".context-designers")

    overview_parts: List[str] = []
    if intro:
        overview_parts.append(_render_node_as_text(intro))
    if designers:
        overview_parts.append(_render_node_as_text(designers))

    if overview_parts:
        blocks.append({
            "category": "overview",
            "size": "all",
            "h2": "",
            "h4": "",
            "order": order,
            "text": _clean_text("\n\n".join(overview_parts)),
            "lines": [],
            "unit_tier": None,
        })
        order += 1

    current_h2 = ""
    current_size = "all"
    current_h4 = ""

    # Walk important nodes in order
    for el in root.find_all(["h2", "h4", "blockquote", "ul"], recursive=True):
        if el.name == "h2":
            current_h2 = _clean_text(el.get_text(" ", strip=True))
            current_size = _major_group_from_h2(current_h2)
            continue

        if el.name == "h4":
            current_h4 = _clean_text(el.get_text(" ", strip=True))
            continue

        # Skip the overview intro blockquote we already handled above
        if el.name == "blockquote" and intro and el is intro:
            continue

        cat = _category_from_h4(current_h4) if current_h4 else "other"
        unit_tier = _extract_unit_tier(current_h4) if cat == "champions" else None

        if el.name == "ul":
            lines = [
                _clean_text(li.get_text(" ", strip=True))
                for li in el.find_all("li", recursive=True)
            ]
            lines = [ln for ln in lines if ln]

            text = _clean_text("\n".join(lines))  # readable
            if not text:
                continue

            blocks.append({
                "category": cat,
                "size": current_size,
                "h2": current_h2,
                "h4": current_h4,
                "order": order,
                "text": text,
                "lines": lines,
                "unit_tier": unit_tier,
            })
            order += 1
            continue

        if el.name == "blockquote":
            text = _render_node_as_text(el)
            if not text:
                continue

            blocks.append({
                "category": cat,
                "size": current_size,
                "h2": current_h2,
                "h4": current_h4,
                "order": order,
                "text": text,
                "lines": [],
                "unit_tier": unit_tier,
            })
            order += 1
            continue

    return blocks


# =========================================================
# OLD: Keep your existing dict output for templates
# =========================================================
def parse_tft_patch_html(raw_html: str) -> OrderedDict:
    """
    Backwards compatible output for your templates:
      out["items"]["large"] = "...string..."
    """
    blocks = parse_tft_patch_blocks(raw_html)
    if not blocks:
        return OrderedDict()

    buckets = _mk_buckets()

    for b in blocks:
        cat = b["category"]
        size = b["size"]
        heading = b["h4"] or b["h2"] or ""
        _append_bucket_block(buckets, cat, size, heading, b["text"])

    out = OrderedDict()
    for key in ["overview", "champions", "items", "traits", "augments", "other"]:
        bk = buckets[key]
        out[key] = {
            "all": _clean_text("\n\n".join(bk.all)),
            "large": _clean_text("\n\n".join(bk.large)),
            "small": _clean_text("\n\n".join(bk.small)),
        }
    return out


def parse_tft_patch(raw_text: str = "", raw_html: Optional[str] = None) -> OrderedDict:
    """
    Public entrypoint used by templates/views today.
    Prefer HTML; fallback to text.
    """
    if raw_html:
        parsed = parse_tft_patch_html(raw_html)
        if parsed:
            return parsed

    if raw_text:
        return OrderedDict([
            ("overview", {"all": raw_text.strip(), "large": "", "small": ""}),
        ])

    return OrderedDict()
