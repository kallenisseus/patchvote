from __future__ import annotations

from bs4 import BeautifulSoup
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional


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
    # Normalize whitespace a bit (keep newlines readable)
    lines = [ln.rstrip() for ln in (s or "").splitlines()]
    # drop empty lines at start/end
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _render_node_as_text(node) -> str:
    # Convert a node subtree to readable text (blockquote, ul, etc.)
    # Using separator="\n" keeps list items on their own line.
    return _clean_text(node.get_text("\n", strip=True))


def _major_group_from_h2(title: str) -> str:
    t = (title or "").strip().upper()
    if "LARGE CHANGES" in t:
        return "large"
    if "SMALL CHANGES" in t:
        return "small"
    # Everything else: treat as "all"
    return "all"


def _category_from_h4(title: str) -> str:
    """
    Map an h4 (change-detail-title) to our categories.
    """
    t = (title or "").strip().upper()

    if t.startswith("UNITS:"):
        return "champions"
    if t in {"TRAITS"}:
        return "traits"
    if t in {"AUGMENTS"}:
        return "augments"

    # Items (Riot uses these)
    if t in {"CORE ITEMS", "RADIANT ITEMS", "ARTIFACTS", "EMBLEMS"}:
        return "items"

    # Everything else falls into other (LEVELING, ENCOUNTERS, AURAS, etc.)
    return "other"


def _append_block(buckets: Dict[str, Bucket], cat: str, group: str, heading: str, body: str) -> None:
    body = _clean_text(body)
    if not body:
        return

    # Keep heading in the body for readability
    block = f"{heading}\n{body}".strip() if heading else body

    # Always store into ".all" as a superset, and also into large/small if applicable
    buckets[cat].all.append(block)
    if group == "large":
        buckets[cat].large.append(block)
    elif group == "small":
        buckets[cat].small.append(block)


def parse_tft_patch_html(raw_html: str) -> OrderedDict:
    """
    HTML-first parser.
    Input: the HTML string that includes <div id="patch-notes-container">...</div>
    Output keys:
      overview, champions, items, traits, augments, other

    Each value is a dict with keys: all, large, small (strings).
    Example:
      out["items"]["large"] = "...blocks..."
    """
    if not raw_html:
        return OrderedDict()

    soup = BeautifulSoup(raw_html, "html.parser")
    root = soup.select_one("#patch-notes-container") or soup

    buckets = _mk_buckets()

    # --- OVERVIEW: take the first blockquote.context + designers block if present
    intro = root.select_one("blockquote.blockquote.context")
    designers = root.select_one(".context-designers")

    overview_parts = []
    if intro:
        overview_parts.append(_render_node_as_text(intro))
    if designers:
        # Designers are usually spans with text
        overview_parts.append(_render_node_as_text(designers))

    if overview_parts:
        buckets["overview"].all.append(_clean_text("\n\n".join(overview_parts)))

    # --- Walk the document in order, tracking current H2 major section
    current_major_group = "all"
    current_h2_title = None

    # We iterate through root descendants, but only react to h2/h4 and content blocks
    # The Riot structure is: h2 -> content -> h4 -> blockquote/ul -> h4 -> ...
    for el in root.find_all(["h2", "h4", "blockquote", "ul"], recursive=True):
        if el.name == "h2":
            current_h2_title = _clean_text(el.get_text(" ", strip=True))
            current_major_group = _major_group_from_h2(current_h2_title)
            continue

        # We only categorize blocks under an h4 (subsection). Otherwise it goes to "other".
        if el.name == "h4":
            # store current "active" h4 in a variable by attaching it to soup temporarily
            el.attrs["_active_h4"] = "1"
            # also keep a pointer on root (simple hack) so other elements can find the last h4
            root.attrs["_last_h4_title"] = _clean_text(el.get_text(" ", strip=True))
            continue

        # content blocks: blockquote or ul
        if el.name in {"blockquote", "ul"}:
            # Ignore the intro blockquote we already used in overview if it's the same node
            if intro and el is intro:
                continue

            h4_title = root.attrs.get("_last_h4_title")  # last seen h4 title (string) or None
            cat = _category_from_h4(h4_title) if h4_title else "other"

            # heading shown to user: include the h4 title; optionally include H2 context too
            heading = h4_title or (current_h2_title or "")

            body = _render_node_as_text(el)
            _append_block(buckets, cat, current_major_group, heading, body)

    # --- Build final OrderedDict, with strings for each bucket/group
    out = OrderedDict()
    for key in ["overview", "champions", "items", "traits", "augments", "other"]:
        b = buckets[key]
        out[key] = {
            "all": _clean_text("\n\n".join(b.all)),
            "large": _clean_text("\n\n".join(b.large)),
            "small": _clean_text("\n\n".join(b.small)),
        }

    return out


def parse_tft_patch(raw_text: str = "", raw_html: Optional[str] = None) -> OrderedDict:
    """
    Public entrypoint:
    Prefer HTML if available; fall back to old text parsing if needed.
    """
    if raw_html:
        parsed = parse_tft_patch_html(raw_html)
        if parsed:
            return parsed

    # Fallback: keep your old simple text behavior (optional)
    if raw_text:
        return OrderedDict([
            ("overview", {"all": raw_text.strip(), "large": "", "small": ""}),
        ])

    return OrderedDict()
