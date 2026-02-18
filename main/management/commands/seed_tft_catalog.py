from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from ...models import Game, Champion, Trait, Item, Augment


DD_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DD_DATA_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/{lang}/{file}"
DD_IMG_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/img/{group}/{full}"


# Riot TFT endpoints + icon folders (official docs)
FILES = {
    "champion": ("tft-champion.json", "tft-champion"),
    "item": ("tft-item.json", "tft-item"),
    "trait": ("tft-trait.json", "tft-trait"),
    "augment": ("tft-augments.json", "tft-augment"),
}


SET_FROM_IMAGE_RE = re.compile(r"\.TFT_Set(\d+)\.", re.IGNORECASE)
SET_FROM_ID_RE = re.compile(r"^TFT(\d+)_", re.IGNORECASE)
TUTORIAL_ID_RE = re.compile(r"^TFTTutorial_", re.IGNORECASE)


def _get_json(session: requests.Session, url: str) -> Dict[str, Any]:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def _latest_dd_version(session: requests.Session) -> str:
    # versions.json is the official Data Dragon version list
    versions = _get_json(session, DD_VERSIONS_URL)
    if not versions:
        raise RuntimeError("versions.json returned empty list")
    return versions[0]


def _infer_set_num(entry_id: str, image_full: str) -> Optional[int]:
    # Best signal is the image filename: e.g. TFT9_Irelia.TFT_Set9.png
    if image_full:
        m = SET_FROM_IMAGE_RE.search(image_full)
        if m:
            return int(m.group(1))

    # Fallback: ids like TFT6_Augment_SalvageBin
    if entry_id:
        m = SET_FROM_ID_RE.match(entry_id)
        if m:
            return int(m.group(1))

    return None


def _maybe_suffix_slug(base_slug: str, set_num: Optional[int], all_sets: bool) -> str:
    # If you seed multiple sets, names WILL collide (Ahri returns, traits repeat, etc).
    # Suffixing avoids DB collisions without forcing you to change your schema today.
    if all_sets and set_num:
        return f"{base_slug}-set{set_num}"
    return base_slug


@dataclass
class UpsertStats:
    added: int = 0
    updated: int = 0
    skipped: int = 0


class Command(BaseCommand):
    help = "Seed TFT catalog (champions/items/traits/augments) from Riot TFT Data Dragon."

    def add_arguments(self, parser):
        parser.add_argument("--ddragon", type=str, default="latest", help="Data Dragon version, e.g. 16.4.1 (or 'latest').")
        parser.add_argument("--lang", type=str, default="en_US", help="Locale, e.g. en_US.")
        parser.add_argument("--set", type=int, default=0, help="Optional set number filter, e.g. 16. 0 = auto-pick highest.")
        parser.add_argument("--all-sets", action="store_true", help="Seed all active sets (will suffix slugs to avoid collisions).")
        parser.add_argument("--include-tutorial", action="store_true", help="Include tutorial entries (normally skipped).")
        parser.add_argument("--dry-run", action="store_true", help="Print what would happen but do not write DB.")

    def handle(self, *args, **opts):
        game, _ = Game.objects.get_or_create(slug="tft", defaults={"name": "Teamfight Tactics"})

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                )
            }
        )

        ddver = (opts["ddragon"] or "latest").strip()
        lang = (opts["lang"] or "en_US").strip()
        all_sets = bool(opts["all_sets"])
        include_tutorial = bool(opts["include_tutorial"])
        dry_run = bool(opts["dry_run"])

        if ddver == "latest":
            ddver = _latest_dd_version(session)

        self.stdout.write(f"✅ Using Data Dragon version: {ddver}")
        self.stdout.write(f"✅ Using locale: {lang}")

        # --- Load champions first so we can auto-detect set number (if desired)
        champ_file, champ_group = FILES["champion"]
        champ_url = DD_DATA_URL.format(ver=ddver, lang=lang, file=champ_file)
        champ_payload = _get_json(session, champ_url)
        champ_data: Dict[str, Any] = champ_payload.get("data", {}) or {}

        if not champ_data:
            self.stderr.write("❌ No champion data found in tft-champion.json")
            return

        # Detect available sets in this patch
        found_sets = []
        for _, v in champ_data.items():
            entry_id = (v or {}).get("id", "")
            img_full = (((v or {}).get("image") or {}).get("full") or "")
            set_num = _infer_set_num(entry_id, img_full)
            if set_num:
                found_sets.append(set_num)

        found_sets = sorted(set(found_sets))
        self.stdout.write(f"ℹ️ Sets detected in this Data Dragon version: {found_sets or '[none detected]'}")

        set_filter = int(opts["set"] or 0)
        if not all_sets:
            if set_filter == 0 and found_sets:
                set_filter = max(found_sets)  # auto-pick highest set
            if set_filter:
                self.stdout.write(f"✅ Seeding only Set {set_filter} (use --all-sets to seed everything)")
            else:
                self.stdout.write("✅ Seeding without set filter (no set detected)")

        # Seed order: traits -> champions -> items -> augments
        stats_traits = self._seed_traits(session, game, ddver, lang, set_filter, all_sets, dry_run)
        stats_champs = self._seed_champions(session, game, ddver, lang, set_filter, all_sets, include_tutorial, dry_run)
        stats_items = self._seed_items(session, game, ddver, lang, all_sets, dry_run)
        stats_aug = self._seed_augments(session, game, ddver, lang, set_filter, all_sets, dry_run)

        self.stdout.write(self.style.SUCCESS(
            "\n🎉 Done!\n"
            f"Traits:   added={stats_traits.added} updated={stats_traits.updated} skipped={stats_traits.skipped}\n"
            f"Champs:   added={stats_champs.added} updated={stats_champs.updated} skipped={stats_champs.skipped}\n"
            f"Items:    added={stats_items.added} updated={stats_items.updated} skipped={stats_items.skipped}\n"
            f"Augments: added={stats_aug.added} updated={stats_aug.updated} skipped={stats_aug.skipped}\n"
        ))

    def _seed_traits(self, session, game, ddver, lang, set_filter: int, all_sets: bool, dry_run: bool) -> UpsertStats:
        stats = UpsertStats()
        file, group = FILES["trait"]
        url = DD_DATA_URL.format(ver=ddver, lang=lang, file=file)
        payload = _get_json(session, url)
        data: Dict[str, Any] = payload.get("data", {}) or {}

        for _, v in data.items():
            entry_id = (v or {}).get("id", "")
            name = (v or {}).get("name", "") or ""
            img_full = (((v or {}).get("image") or {}).get("full") or "")
            if not name:
                continue

            set_num = _infer_set_num(entry_id, img_full)
            if (not all_sets) and set_filter and set_num and set_num != set_filter:
                continue

            s = _maybe_suffix_slug(slugify(name), set_num, all_sets)
            image_url = DD_IMG_URL.format(ver=ddver, group=group, full=img_full) if img_full else ""

            obj = Trait.objects.filter(game=game, slug=s).first()
            if not obj:
                if dry_run:
                    stats.added += 1
                else:
                    Trait.objects.create(game=game, slug=s, name=name, image_url=image_url)
                    stats.added += 1
            else:
                changed = False
                if obj.name != name:
                    obj.name = name
                    changed = True
                if image_url and obj.image_url != image_url:
                    obj.image_url = image_url
                    changed = True

                if changed:
                    if not dry_run:
                        obj.save()
                    stats.updated += 1
                else:
                    stats.skipped += 1

        return stats

    def _seed_champions(self, session, game, ddver, lang, set_filter: int, all_sets: bool, include_tutorial: bool, dry_run: bool) -> UpsertStats:
        stats = UpsertStats()
        file, group = FILES["champion"]
        url = DD_DATA_URL.format(ver=ddver, lang=lang, file=file)
        payload = _get_json(session, url)
        data: Dict[str, Any] = payload.get("data", {}) or {}

        for _, v in data.items():
            entry_id = (v or {}).get("id", "")
            name = (v or {}).get("name", "") or ""
            tier = (v or {}).get("tier", None)
            cost = (v or {}).get("cost", None)  # sometimes present in tutorial-ish entries
            img_full = (((v or {}).get("image") or {}).get("full") or "")

            if not name:
                continue

            if (not include_tutorial) and (TUTORIAL_ID_RE.match(entry_id) or (cost == 0 and (tier or 0) == 0)):
                continue

            set_num = _infer_set_num(entry_id, img_full)
            if (not all_sets) and set_filter and set_num and set_num != set_filter:
                continue

            # cost fallback: if "cost" is absent or 0, use tier (Riot calls it "tier" in TFT dd)
            final_cost = None
            if isinstance(cost, int) and cost > 0:
                final_cost = cost
            elif isinstance(tier, int) and tier > 0:
                final_cost = tier

            s = _maybe_suffix_slug(slugify(name), set_num, all_sets)
            image_url = DD_IMG_URL.format(ver=ddver, group=group, full=img_full) if img_full else ""

            obj = Champion.objects.filter(game=game, slug=s).first()
            if not obj:
                if dry_run:
                    stats.added += 1
                else:
                    Champion.objects.create(game=game, slug=s, name=name, cost=final_cost, image_url=image_url)
                    stats.added += 1
            else:
                changed = False
                if obj.name != name:
                    obj.name = name
                    changed = True
                if final_cost is not None and obj.cost != final_cost:
                    obj.cost = final_cost
                    changed = True
                if image_url and obj.image_url != image_url:
                    obj.image_url = image_url
                    changed = True

                if changed:
                    if not dry_run:
                        obj.save()
                    stats.updated += 1
                else:
                    stats.skipped += 1

        return stats

    def _seed_items(self, session, game, ddver, lang, all_sets: bool, dry_run: bool) -> UpsertStats:
        # Items are a broad category and not always set-specific; we usually keep them all. :contentReference[oaicite:2]{index=2}
        stats = UpsertStats()
        file, group = FILES["item"]
        url = DD_DATA_URL.format(ver=ddver, lang=lang, file=file)
        payload = _get_json(session, url)
        data: Dict[str, Any] = payload.get("data", {}) or {}

        for _, v in data.items():
            name = (v or {}).get("name", "") or ""
            img_full = (((v or {}).get("image") or {}).get("full") or "")
            if not name:
                continue

            # item names can collide less often; keep simple slug
            s = slugify(name)
            image_url = DD_IMG_URL.format(ver=ddver, group=group, full=img_full) if img_full else ""

            obj = Item.objects.filter(game=game, slug=s).first()
            if not obj:
                if dry_run:
                    stats.added += 1
                else:
                    Item.objects.create(game=game, slug=s, name=name, image_url=image_url)
                    stats.added += 1
            else:
                changed = False
                if obj.name != name:
                    obj.name = name
                    changed = True
                if image_url and obj.image_url != image_url:
                    obj.image_url = image_url
                    changed = True

                if changed:
                    if not dry_run:
                        obj.save()
                    stats.updated += 1
                else:
                    stats.skipped += 1

        return stats

    def _seed_augments(self, session, game, ddver, lang, set_filter: int, all_sets: bool, dry_run: bool) -> UpsertStats:
        stats = UpsertStats()
        file, group = FILES["augment"]
        url = DD_DATA_URL.format(ver=ddver, lang=lang, file=file)
        payload = _get_json(session, url)

        # tft-augments.json has extra keys at the top; the main list is in "data". :contentReference[oaicite:3]{index=3}
        data: Dict[str, Any] = payload.get("data", {}) or {}

        for _, v in data.items():
            entry_id = (v or {}).get("id", "")
            name = (v or {}).get("name", "") or ""
            img_full = (((v or {}).get("image") or {}).get("full") or "")

            if not name:
                continue

            set_num = _infer_set_num(entry_id, img_full)
            if (not all_sets) and set_filter and set_num and set_num != set_filter:
                continue

            s = _maybe_suffix_slug(slugify(name), set_num, all_sets)
            image_url = DD_IMG_URL.format(ver=ddver, group=group, full=img_full) if img_full else ""

            obj = Augment.objects.filter(game=game, slug=s).first()
            if not obj:
                if dry_run:
                    stats.added += 1
                else:
                    Augment.objects.create(game=game, slug=s, name=name, image_url=image_url)
                    stats.added += 1
            else:
                changed = False
                if obj.name != name:
                    obj.name = name
                    changed = True
                if image_url and obj.image_url != image_url:
                    obj.image_url = image_url
                    changed = True

                if changed:
                    if not dry_run:
                        obj.save()
                    stats.updated += 1
                else:
                    stats.skipped += 1

        return stats
