import hashlib
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
import re

from main.models import Game, Patch


PATCH_NOTES_INDEX = "https://www.leagueoflegends.com/en-us/news/tags/teamfight-tactics-patch-notes/"
GAME_UPDATES_BASE = "https://teamfighttactics.leagueoflegends.com/en-us/news/game-updates/"


class Command(BaseCommand):
    help = "Fetch ALL TFT patch notes (discover via patch-notes, fetch via game-updates)"

    def handle(self, *args, **kwargs):
        game, _ = Game.objects.get_or_create(
            slug="tft",
            defaults={"name": "Teamfight Tactics"},
        )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }

        # -----------------------------
        # STEP 1: DISCOVER PATCHES
        # -----------------------------
        res = requests.get(PATCH_NOTES_INDEX, headers=headers, timeout=15)
        if res.status_code != 200:
            self.stderr.write("❌ Failed to fetch patch-notes index")
            return

        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.find_all("a", href=True)

        patches = {}  # version -> slug

        for link in links:
            href = link["href"]

            if "teamfight-tactics-patch-" not in href:
                continue

            slug = href.rstrip("/").split("/")[-1]

            # normalize
            clean = slug.replace("teamfight-tactics-patch-", "")
            clean = clean.replace("-notes", "")
            clean = re.sub(r"-\d{4}$", "", clean)

            version = clean.replace("-", ".")

            if not re.match(r"^\d+\.\d+$", version):
                continue

            patches[version] = slug

        if not patches:
            self.stderr.write("❌ No patches discovered")
            return

        self.stdout.write(f"🔍 Discovered {len(patches)} patches")

        # -----------------------------
        # STEP 2: FETCH PATCH CONTENT
        # -----------------------------
        added = 0
        updated = 0

        for version in sorted(
            patches.keys(),
            key=lambda v: [int(x) for x in v.split(".")],
            reverse=True,
        ):
            slug = patches[version]

            # try without -notes first, then fallback
            urls = [
                f"{GAME_UPDATES_BASE}{slug.replace('-notes', '')}/",
                f"{GAME_UPDATES_BASE}{slug}/",
            ]

            article_html = None
            article_url = None

            for url in urls:
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    article_html = r.text
                    article_url = url
                    break

            if not article_html:
                self.stderr.write(f"⚠ Could not fetch patch {version}")
                continue

            soup = BeautifulSoup(article_html, "html.parser")
            article = soup.find("article") or soup.find("main")

            if not article:
                self.stderr.write(f"⚠ No article content for {version}")
                continue

            text = article.get_text("\n", strip=True)
            if len(text) < 200:
                self.stderr.write(f"⚠ Content too short for {version}")
                continue

            content_hash = hashlib.sha256(text.encode()).hexdigest()

            patch, created = Patch.objects.get_or_create(
                game=game,
                version=version,
                defaults={
                    "raw_text": text,
                    "content_hash": content_hash,
                    "source_url": article_url,
                },
            )

            if created:
                added += 1
                self.stdout.write(f"✅ Added {version}")
            elif patch.content_hash != content_hash:
                patch.raw_text = text
                patch.content_hash = content_hash
                patch.source_url = article_url
                patch.save()
                updated += 1
                self.stdout.write(f"♻ Updated {version}")
            else:
                self.stdout.write(f"⏭ Skipped {version}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🎉 Done! Added={added}, Updated={updated}, Total={len(patches)}"
            )
        )
