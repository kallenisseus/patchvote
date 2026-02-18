from __future__ import annotations

import re
from typing import Any, Dict

import requests
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from ...models import Game, Champion, Item, Trait, Augment


DD_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DD_DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/{file}"
DD_IMG_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/img/{group}/{full}"


SET_FROM_KEY_RE = re.compile(r"/Sets/TFTSet(\d+)/", re.IGNORECASE)
SET_FROM_IMAGE_RE = re.compile(r"\.TFT_Set(\d+)\.", re.IGNORECASE)
SET_FROM_ID_RE = re.compile(r"^TFT(\d+)_", re.IGNORECASE)

NAME_STARTS_WITH_LETTER_RE = re.compile(r"^[A-Za-z]")

CHAMPION_SKIP_ID_RE = re.compile(r"(TraitClone|Tutorial)", re.IGNORECASE)


def latest_dd_version(session: requests.Session) -> str:
    r = session.get(DD_VERSIONS_URL, timeout=30)
    r.raise_for_status()
    versions = r.json()
    if not versions:
        raise RuntimeError("versions.json returned empty list")
    return versions[0]


def infer_set(dd_key: str, ddragon_id: str, image_full: str) -> int:
    m = SET_FROM_KEY_RE.search(dd_key or "")
    if m:
        return int(m.group(1))
    m = SET_FROM_IMAGE_RE.search(image_full or "")
    if m:
        return int(m.group(1))
    m = SET_FROM_ID_RE.match(ddragon_id or "")
    if m:
        return int(m.group(1))
    return 0


def item_kind_and_subgroup(ddragon_id: str) -> tuple[str, str]:
    u = (ddragon_id or "").upper()

    if u.startswith("TFT_ITEM_ARTIFACT_"):
        return ("artifact", "")
    if u.startswith("TFT_ITEM_RADIANT_"):
        return ("radiant", "")

    # Set flavored items:
    if re.match(r"^TFT\d+_ITEM_", u):
        # Example: TFT16_Item_Bilgewater_*
        m = re.match(r"^TFT(\d+)_ITEM_([A-Z0-9]+)_", u)
        if m:
            subgroup = m.group(2).lower()  # bilgewater, etc
            return ("set", subgroup)
        return ("set", "")

    return ("core", "")


class Command(BaseCommand):
    help = "Seed TFT Champions + Items + Traits + Augments from Data Dragon (set-aware)."

    def add_arguments(self, parser):
        parser.add_argument("--ddragon", type=str, default="latest")
        parser.add_argument("--sets", type=str, default="15,16")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        game, _ = Game.objects.get_or_create(slug="tft", defaults={"name": "Teamfight Tactics"})

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        ddver = (opts["ddragon"] or "latest").strip()
        if ddver == "latest":
            ddver = latest_dd_version(session)

        sets_raw = (opts["sets"] or "").strip()
        allowed_sets = {int(x.strip()) for x in sets_raw.split(",") if x.strip().isdigit()}
        dry = bool(opts["dry_run"])

        self.stdout.write(f"✅ Using Data Dragon: {ddver}")
        self.stdout.write(f"✅ Allowed sets: {sorted(allowed_sets)}")

        self._seed_champions(session, game, ddver, allowed_sets, dry)
        self._seed_traits(session, game, ddver, allowed_sets, dry)
        self._seed_items(session, game, ddver, allowed_sets, dry)
        self._seed_augments(session, game, ddver, allowed_sets, dry)

        self.stdout.write(self.style.SUCCESS("✅ Done."))

    # -------------------------
    # Champions
    # -------------------------
    def _seed_champions(self, session, game, ddver: str, allowed_sets: set[int], dry: bool):
        payload = session.get(DD_DATA_URL.format(ver=ddver, file="tft-champion.json"), timeout=30).json()
        data: Dict[str, Any] = payload.get("data", {}) or {}

        add_ = upd_ = skip_ = 0

        for dd_key, c in data.items():
            ddragon_id = (c or {}).get("id", "") or ""
            name = (c or {}).get("name", "") or ""
            tier = (c or {}).get("tier", None)
            cost = (c or {}).get("cost", None)
            image_full = (((c or {}).get("image") or {}).get("full") or "")

            if not name or CHAMPION_SKIP_ID_RE.search(ddragon_id) or "TFTSetTutorial" in (dd_key or ""):
                continue

            # reject clones/oddities: require real cost (or tier fallback)
            if isinstance(cost, int) and cost > 0:
                cost_val = cost
            elif isinstance(tier, int) and tier > 0:
                cost_val = tier
            else:
                continue

            set_key = infer_set(dd_key, ddragon_id, image_full)
            if allowed_sets and set_key not in allowed_sets:
                continue

            image_url = DD_IMG_URL.format(ver=ddver, group="tft-champion", full=image_full) if image_full else ""
            slug = slugify(name)

            obj = Champion.objects.filter(game=game, set_key=set_key, slug=slug).first()
            if not obj:
                if not dry:
                    Champion.objects.create(
                        game=game,
                        set_key=set_key,
                        name=name,
                        slug=slug,
                        cost=cost_val,
                        image_url=image_url,
                        ddragon_id=ddragon_id,
                        ddragon_key=dd_key,
                        ddragon_image_full=image_full,
                    )
                add_ += 1
            else:
                changed = False
                for field, val in [
                    ("name", name),
                    ("cost", cost_val),
                    ("image_url", image_url),
                    ("ddragon_id", ddragon_id),
                    ("ddragon_key", dd_key),
                    ("ddragon_image_full", image_full),
                ]:
                    if val and getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    if not dry:
                        obj.save()
                    upd_ += 1
                else:
                    skip_ += 1

        self.stdout.write(f"🏆 Champions: added={add_}, updated={upd_}, skipped={skip_}")

    # -------------------------
    # Traits
    # -------------------------
    def _seed_traits(self, session, game, ddver: str, allowed_sets: set[int], dry: bool):
        payload = session.get(DD_DATA_URL.format(ver=ddver, file="tft-trait.json"), timeout=30).json()
        data: Dict[str, Any] = payload.get("data", {}) or {}

        add_ = upd_ = skip_ = 0

        for dd_key, t in data.items():
            ddragon_id = (t or {}).get("id", "") or ""
            name = (t or {}).get("name", "") or ""
            image_full = (((t or {}).get("image") or {}).get("full") or "")

            if not name:
                continue

            set_key = infer_set(dd_key, ddragon_id, image_full)
            if allowed_sets and set_key != 0 and set_key not in allowed_sets:
                continue

            image_url = DD_IMG_URL.format(ver=ddver, group="tft-trait", full=image_full) if image_full else ""
            slug = slugify(name)

            obj = Trait.objects.filter(game=game, set_key=set_key, slug=slug).first()
            if not obj:
                if not dry:
                    Trait.objects.create(
                        game=game,
                        set_key=set_key,
                        name=name,
                        slug=slug,
                        image_url=image_url,
                        ddragon_id=ddragon_id,
                        ddragon_key=dd_key,
                        ddragon_image_full=image_full,
                    )
                add_ += 1
            else:
                changed = False
                for field, val in [
                    ("name", name),
                    ("image_url", image_url),
                    ("ddragon_id", ddragon_id),
                    ("ddragon_key", dd_key),
                    ("ddragon_image_full", image_full),
                ]:
                    if val and getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    if not dry:
                        obj.save()
                    upd_ += 1
                else:
                    skip_ += 1

        self.stdout.write(f"🧬 Traits: added={add_}, updated={upd_}, skipped={skip_}")

    # -------------------------
    # Items
    # -------------------------
    def _seed_items(self, session, game, ddver: str, allowed_sets: set[int], dry: bool):
        payload = session.get(DD_DATA_URL.format(ver=ddver, file="tft-item.json"), timeout=30).json()
        data: Dict[str, Any] = payload.get("data", {}) or {}

        add_ = upd_ = skip_ = 0

        for dd_key, it in data.items():
            ddragon_id = (it or {}).get("id", "") or ""
            name = (it or {}).get("name", "") or ""
            image_full = (((it or {}).get("image") or {}).get("full") or "")

            # your filter: name must start with a letter
            if not name or not NAME_STARTS_WITH_LETTER_RE.match(name.strip()):
                continue

            # your filter: keep only item families we want
            if not (ddragon_id.startswith("TFT_Item_") or re.match(r"^TFT\d+_Item_", ddragon_id)):
                continue

            kind, subgroup = item_kind_and_subgroup(ddragon_id)
            set_key = infer_set(dd_key, ddragon_id, image_full)

            # allow global items (set_key=0) always; filter set-specific by allowed sets
            if allowed_sets and set_key != 0 and set_key not in allowed_sets:
                continue

            image_url = DD_IMG_URL.format(ver=ddver, group="tft-item", full=image_full) if image_full else ""
            slug = slugify(name)

            obj = Item.objects.filter(game=game, set_key=set_key, kind=kind, slug=slug).first()
            if not obj:
                if not dry:
                    Item.objects.create(
                        game=game,
                        set_key=set_key,
                        kind=kind,
                        subgroup=subgroup,
                        name=name,
                        slug=slug,
                        image_url=image_url,
                        ddragon_id=ddragon_id,
                        ddragon_key=dd_key,
                        ddragon_image_full=image_full,
                    )
                add_ += 1
            else:
                changed = False
                for field, val in [
                    ("name", name),
                    ("subgroup", subgroup),
                    ("image_url", image_url),
                    ("ddragon_id", ddragon_id),
                    ("ddragon_key", dd_key),
                    ("ddragon_image_full", image_full),
                ]:
                    if val and getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    if not dry:
                        obj.save()
                    upd_ += 1
                else:
                    skip_ += 1

        self.stdout.write(f"🧱 Items: added={add_}, updated={upd_}, skipped={skip_}")

    # -------------------------
    # Augments
    # -------------------------
    def _seed_augments(self, session, game, ddver: str, allowed_sets: set[int], dry: bool):
        payload = session.get(DD_DATA_URL.format(ver=ddver, file="tft-augments.json"), timeout=30).json()
        data: Dict[str, Any] = payload.get("data", {}) or {}

        add_ = upd_ = skip_ = 0

        for dd_key, a in data.items():
            ddragon_id = (a or {}).get("id", "") or ""
            name = (a or {}).get("name", "") or ""
            image_full = (((a or {}).get("image") or {}).get("full") or "")

            # lots of augments are valid; just require readable name
            if not name or not NAME_STARTS_WITH_LETTER_RE.match(name.strip()):
                continue

            set_key = infer_set(dd_key, ddragon_id, image_full)
            if allowed_sets and set_key != 0 and set_key not in allowed_sets:
                continue

            image_url = DD_IMG_URL.format(ver=ddver, group="tft-augment", full=image_full) if image_full else ""
            slug = slugify(name)

            obj = Augment.objects.filter(game=game, set_key=set_key, slug=slug).first()
            if not obj:
                if not dry:
                    Augment.objects.create(
                        game=game,
                        set_key=set_key,
                        name=name,
                        slug=slug,
                        image_url=image_url,
                        ddragon_id=ddragon_id,
                        ddragon_key=dd_key,
                        ddragon_image_full=image_full,
                    )
                add_ += 1
            else:
                changed = False
                for field, val in [
                    ("name", name),
                    ("image_url", image_url),
                    ("ddragon_id", ddragon_id),
                    ("ddragon_key", dd_key),
                    ("ddragon_image_full", image_full),
                ]:
                    if val and getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    if not dry:
                        obj.save()
                    upd_ += 1
                else:
                    skip_ += 1

        self.stdout.write(f"✨ Augments: added={add_}, updated={upd_}, skipped={skip_}")
