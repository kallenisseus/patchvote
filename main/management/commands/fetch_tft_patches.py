from __future__ import annotations

import hashlib
import re
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

from ...models import Game, Patch, PatchSection
from ...parsers.tft_patch_parser import parse_tft_patch_blocks


BASE = "https://teamfighttactics.leagueoflegends.com/en-us/news/game-updates/"


def _version_key(v: str):
    a, b = v.split(".")
    return (int(a), int(b))


def _url_candidates(version: str) -> list[str]:
    """
    Riot använder minst två varianter:
      /teamfight-tactics-patch-16-4/
      /teamfight-tactics-patch-15-5-notes/
    Så vi provar båda.
    """
    maj, minor = version.split(".")
    maj_i = int(maj)
    min_i = int(minor)

    slugs = [
        f"teamfight-tactics-patch-{maj_i}-{min_i}",
        f"teamfight-tactics-patch-{maj_i}-{min_i}-notes",
    ]
    return [f"{BASE}{slug}/" for slug in slugs]


def _extract_patch_container(html: str):
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#patch-notes-container")
    if not container:
        container = soup.select_one('[data-testid="rich-text-html"]')
    return soup, container


class Command(BaseCommand):
    help = "Fetch TFT patches by trying patch pages directly (no index scraping)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--versions",
            type=str,
            default="",
            help="Comma-separated versions, e.g. 16.4,16.3,15.5. If omitted, brute-force a range.",
        )
        parser.add_argument("--major-min", type=int, default=14)
        parser.add_argument("--major-max", type=int, default=16)
        parser.add_argument("--minor-max", type=int, default=24)

    def handle(self, *args, **opts):
        game, _ = Game.objects.get_or_create(
            slug="tft",
            defaults={"name": "Teamfight Tactics"},
        )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        session = requests.Session()
        session.headers.update(headers)

        # -----------------------------
        # Decide which versions to try
        # -----------------------------
        versions_arg = (opts.get("versions") or "").strip()
        versions: list[str] = []

        if versions_arg:
            versions = [v.strip() for v in versions_arg.split(",") if v.strip()]
        else:
            major_min = int(opts["major_min"])
            major_max = int(opts["major_max"])
            minor_max = int(opts["minor_max"])

            # brute-force: try major_max.minor_max down to major_min.1
            for maj in range(major_max, major_min - 1, -1):
                for minor in range(minor_max, 0, -1):
                    versions.append(f"{maj}.{minor}")

        # remove duplicates + sort desc
        versions = sorted(set(versions), key=_version_key, reverse=True)

        self.stdout.write(f"🔎 Trying {len(versions)} version(s) directly…")

        added = 0
        updated = 0
        skipped = 0
        not_found = 0

        for version in versions:
            html = None
            url_used = None

            for url in _url_candidates(version):
                try:
                    r = session.get(url, timeout=20, allow_redirects=True)
                except requests.RequestException:
                    continue

                if r.status_code == 200 and r.text and len(r.text) > 800:
                    html = r.text
                    url_used = url
                    break

            if not html:
                not_found += 1
                continue

            soup, container = _extract_patch_container(html)

            if container:
                raw_html = str(container)
                raw_text = container.get_text("\n", strip=True)
            else:
                # fallback
                article = soup.find("article") or soup.find("main")
                raw_html = str(article) if article else ""
                raw_text = article.get_text("\n", strip=True) if article else ""

            if not raw_text or len(raw_text) < 200:
                self.stderr.write(f"⚠ Content too short for {version} ({url_used})")
                continue

            # hash payload
            hash_payload = (raw_text + "\n\n" + (raw_html or "")).encode("utf-8")
            content_hash = hashlib.sha256(hash_payload).hexdigest()

            patch, created = Patch.objects.get_or_create(
                game=game,
                version=version,
                defaults={
                    "raw_text": raw_text,
                    "raw_html": raw_html,
                    "content_hash": content_hash,
                    "source_url": url_used or "",
                    "source_slug": (url_used or "").rstrip("/").split("/")[-1],
                },
            )

            changed = False
            if created:
                added += 1
                changed = True
                self.stdout.write(f"✅ Added {version} ({url_used})")
            elif patch.content_hash != content_hash:
                patch.raw_text = raw_text
                patch.raw_html = raw_html
                patch.content_hash = content_hash
                patch.source_url = url_used or ""
                patch.source_slug = (url_used or "").rstrip("/").split("/")[-1]
                patch.save()
                updated += 1
                changed = True
                self.stdout.write(f"♻ Updated {version} ({url_used})")
            else:
                skipped += 1
                self.stdout.write(f"⏭ Skipped {version}")

            # -----------------------------
            # Save PatchSection rows
            # -----------------------------
            if changed:
                patch.sections.all().delete()

                blocks = parse_tft_patch_blocks(raw_html or "")
                if not blocks:
                    self.stderr.write(f"⚠ No blocks parsed for {version}")
                    continue

                PatchSection.objects.bulk_create(
                    [
                        PatchSection(
                            patch=patch,
                            category=b["category"],
                            size=b["size"],
                            h2=b["h2"],
                            h4=b["h4"],
                            order=b["order"],
                            text=b["text"],
                            lines_json=b["lines"],
                            unit_tier=b["unit_tier"],
                        )
                        for b in blocks
                    ]
                )
                self.stdout.write(f"🧩 Saved {len(blocks)} sections for {version}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🎉 Done! Added={added}, Updated={updated}, Skipped={skipped}, NotFound={not_found}"
            )
        )
