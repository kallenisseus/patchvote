import hashlib
import re
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand

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

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

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

            # Best target for patch notes
            container = soup.select_one("#patch-notes-container")
            if not container:
                # fallback: Riot rich text container
                container = soup.select_one('[data-testid="rich-text-html"]')

            raw_html = None
            raw_text = None

            if container:
                raw_html = str(container)
                raw_text = container.get_text("\n", strip=True)
            else:
                # last fallback
                article = soup.find("article") or soup.find("main")
                raw_html = str(article) if article else None
                raw_text = article.get_text("\n", strip=True) if article else ""

            if not raw_text or len(raw_text) < 200:
                self.stderr.write(f"⚠ Content too short for {version}")
                continue

            # Hash what we actually store
            hash_payload = (raw_text + "\n\n" + (raw_html or "")).encode("utf-8")
            content_hash = hashlib.sha256(hash_payload).hexdigest()

            patch, created = Patch.objects.get_or_create(
                game=game,
                version=version,
                defaults={
                    "raw_text": raw_text,
                    "raw_html": raw_html,
                    "content_hash": content_hash,
                    "source_url": article_url,
                },
            )

            if created:
                added += 1
                self.stdout.write(f"✅ Added {version}")
            elif patch.content_hash != content_hash:
                patch.raw_text = raw_text
                patch.raw_html = raw_html
                patch.content_hash = content_hash
                patch.source_url = article_url
                patch.save()
                updated += 1
                self.stdout.write(f"♻ Updated {version}")
            else:
                self.stdout.write(f"⏭ Skipped {version}")

        self.stdout.write(self.style.SUCCESS(
            f"\n🎉 Done! Added={added}, Updated={updated}, Total={len(patches)}"
        ))
