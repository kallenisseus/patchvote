from __future__ import annotations

from django.db import models

from django.contrib.auth.models import User



from django.conf import settings
from django.db import models
from django.db.models import Q


# =========================================================
# Core game + patch
# =========================================================

class Game(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)

    short_name = models.CharField(max_length=16, blank=True)
    accent_hex = models.CharField(max_length=7, default="#6366F1")

    icon = models.ImageField(upload_to="game_icons/", blank=True, null=True)
    cover = models.ImageField(upload_to="game_covers/", blank=True, null=True)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class GameImage(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="game_images/")
    kind = models.CharField(
        max_length=20,
        default="screenshot",
        choices=[
            ("screenshot", "Screenshot"),
            ("banner", "Banner"),
            ("art", "Artwork"),
        ],
    )
    caption = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.game.slug} ({self.kind})"


class Patch(models.Model):
    """
    Canonical patch source (raw HTML/text stays here).
    """
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="patches")
    version = models.CharField(max_length=50)

    released_at = models.DateField(null=True, blank=True)
    source_url = models.URLField(blank=True)

    raw_text = models.TextField(blank=True)
    raw_html = models.TextField(blank=True, null=True)

    content_hash = models.CharField(max_length=64, blank=True)
    source_slug = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("game", "version")
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["game", "version"]),
        ]

    def __str__(self) -> str:
        return f"{self.game.slug} {self.version}"


# =========================================================
# Patch sections (preserve structure: Large/Small + headings)
# =========================================================

PATCH_SECTION_CATEGORIES = [
    ("overview", "Overview"),
    ("champions", "Champions"),
    ("items", "Items"),
    ("traits", "Traits"),
    ("augments", "Augments"),
    ("other", "Other"),
]
PATCH_SECTION_SIZES = [("all", "All"), ("large", "Large"), ("small", "Small")]


class PatchSection(models.Model):
    patch = models.ForeignKey(Patch, on_delete=models.CASCADE, related_name="sections")

    category = models.CharField(max_length=20, choices=PATCH_SECTION_CATEGORIES)
    size = models.CharField(max_length=10, choices=PATCH_SECTION_SIZES, default="all")

    h2 = models.CharField(max_length=200, blank=True)  # e.g. "LARGE CHANGES"
    h4 = models.CharField(max_length=200, blank=True)  # e.g. "UNITS: Tier 1"
    order = models.PositiveIntegerField(default=0)

    text = models.TextField(blank=True)
    lines_json = models.JSONField(default=list, blank=True)

    unit_tier = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["patch", "category", "size"]),
        ]

    def __str__(self) -> str:
        return f"{self.patch} [{self.category}/{self.size}] #{self.order}"


# =========================================================
# TFT Entities (champions/items/traits/augments)
# =========================================================

class Trait(models.Model):
    game = models.ForeignKey("Game", on_delete=models.CASCADE, related_name="traits")

    set_key = models.PositiveSmallIntegerField(default=0, db_index=True)

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    image_url = models.URLField(blank=True)

    # preserve Riot metadata
    ddragon_id = models.CharField(max_length=200, blank=True)
    ddragon_key = models.CharField(max_length=500, blank=True)
    ddragon_image_full = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "set_key", "slug"], name="uniq_trait_game_set_slug"),
        ]

    def __str__(self):
        return f"{self.game.slug} S{self.set_key} {self.name}"


class Augment(models.Model):
    game = models.ForeignKey("Game", on_delete=models.CASCADE, related_name="augments")

    set_key = models.PositiveSmallIntegerField(default=0, db_index=True)

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    tier = models.PositiveSmallIntegerField(null=True, blank=True)
    image_url = models.URLField(blank=True)

    # preserve Riot metadata
    ddragon_id = models.CharField(max_length=200, blank=True)
    ddragon_key = models.CharField(max_length=500, blank=True)
    ddragon_image_full = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "set_key", "slug"], name="uniq_augment_game_set_slug"),
        ]

    def __str__(self):
        return f"{self.game.slug} S{self.set_key} {self.name}"


class Champion(models.Model):
    game = models.ForeignKey("Game", on_delete=models.CASCADE, related_name="champions")

    # NEW
    set_key = models.PositiveSmallIntegerField(default=0, db_index=True)

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    cost = models.PositiveSmallIntegerField(null=True, blank=True)
    image_url = models.URLField(blank=True)

    # NEW (preserve Riot metadata)
    ddragon_id = models.CharField(max_length=120, blank=True)
    ddragon_key = models.CharField(max_length=500, blank=True)
    ddragon_image_full = models.CharField(max_length=200, blank=True)

    traits = models.ManyToManyField("Trait", blank=True, related_name="champions")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "set_key", "slug"], name="uniq_champion_game_set_slug"),
        ]



class Item(models.Model):
    game = models.ForeignKey("Game", on_delete=models.CASCADE, related_name="items")

    set_key = models.PositiveSmallIntegerField(default=0, db_index=True)

    # grouping
    KIND_CORE = "core"
    KIND_RADIANT = "radiant"
    KIND_ARTIFACT = "artifact"
    KIND_SET = "set"

    KIND_CHOICES = [
        (KIND_CORE, "Core"),
        (KIND_RADIANT, "Radiant"),
        (KIND_ARTIFACT, "Artifact"),
        (KIND_SET, "Set-specific"),
    ]

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_CORE, db_index=True)
    subgroup = models.CharField(max_length=50, blank=True, db_index=True)  # e.g. bilgewater

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    image_url = models.URLField(blank=True)

    # preserve Riot metadata
    ddragon_id = models.CharField(max_length=200, blank=True)
    ddragon_key = models.CharField(max_length=500, blank=True)
    ddragon_image_full = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "set_key", "kind", "slug"], name="uniq_item_game_set_kind_slug"),
        ]

    def __str__(self):
        return f"{self.game.slug} S{self.set_key} {self.kind} {self.name}"


# =========================================================
# Derived links: patch -> entity + snippet
# =========================================================

class EntityChange(models.Model):
    ENTITY_CHOICES = [
        ("champion", "Champion"),
        ("item", "Item"),
        ("trait", "Trait"),
        ("augment", "Augment"),
    ]

    patch = models.ForeignKey(Patch, on_delete=models.CASCADE, related_name="entity_changes")
    section = models.ForeignKey(PatchSection, on_delete=models.CASCADE, related_name="entity_changes")

    entity_type = models.CharField(max_length=10, choices=ENTITY_CHOICES)

    champion = models.ForeignKey(Champion, null=True, blank=True, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.CASCADE)
    trait = models.ForeignKey(Trait, null=True, blank=True, on_delete=models.CASCADE)
    augment = models.ForeignKey(Augment, null=True, blank=True, on_delete=models.CASCADE)

    snippet = models.TextField()
    size = models.CharField(max_length=10, choices=PATCH_SECTION_SIZES, default="all")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity_type", "patch"]),
            models.Index(fields=["patch", "size"]),
        ]
        constraints = [
            # Exactly one FK must be set
            models.CheckConstraint(
                name="entitychange_exactly_one_fk",
                check=(
                    (Q(champion__isnull=False) & Q(item__isnull=True) & Q(trait__isnull=True) & Q(augment__isnull=True)) |
                    (Q(champion__isnull=True) & Q(item__isnull=False) & Q(trait__isnull=True) & Q(augment__isnull=True)) |
                    (Q(champion__isnull=True) & Q(item__isnull=True) & Q(trait__isnull=False) & Q(augment__isnull=True)) |
                    (Q(champion__isnull=True) & Q(item__isnull=True) & Q(trait__isnull=True) & Q(augment__isnull=False))
                )
            )
        ]


# =========================================================
# Feedback / voting (rewired to TFT entities)
# =========================================================

class Feedback(models.Model):
    """
    A user vote about balance for a specific entity in a specific patch.
    """

    BUFF = "buff"
    NERF = "nerf"
    FINE = "fine"
    REWORK = "rework"

    CHOICES = [
        (BUFF, "Buff"),
        (NERF, "Nerf"),
        (FINE, "Fine"),
        (REWORK, "Rework"),
    ]

    patch = models.ForeignKey(Patch, on_delete=models.CASCADE, related_name="feedback")

    # Feedback model
    entity_type = models.CharField(
        choices=EntityChange.ENTITY_CHOICES,
        default="champion",   # ✅ prevents the prompt
    )


    champion = models.ForeignKey(Champion, null=True, blank=True, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, null=True, blank=True, on_delete=models.CASCADE)
    trait = models.ForeignKey(Trait, null=True, blank=True, on_delete=models.CASCADE)
    augment = models.ForeignKey(Augment, null=True, blank=True, on_delete=models.CASCADE)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Null = anonymous feedback",
    )

    vote = models.CharField(max_length=10, choices=CHOICES)

    skill_band = models.CharField(max_length=30, blank=True)
    mode = models.CharField(max_length=30, blank=True)
    reason_tags = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["patch", "entity_type"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="feedback_exactly_one_fk",
                check=(
                    (Q(champion__isnull=False) & Q(item__isnull=True) & Q(trait__isnull=True) & Q(augment__isnull=True)) |
                    (Q(champion__isnull=True) & Q(item__isnull=False) & Q(trait__isnull=True) & Q(augment__isnull=True)) |
                    (Q(champion__isnull=True) & Q(item__isnull=True) & Q(trait__isnull=False) & Q(augment__isnull=True)) |
                    (Q(champion__isnull=True) & Q(item__isnull=True) & Q(trait__isnull=True) & Q(augment__isnull=False))
                )
            )
        ]


# =========================================================
# Accounts / suggestions (kept)
# =========================================================

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.user)


class LinkedGameAccount(models.Model):
    PROVIDER_CHOICES = [
        ("riot", "Riot Games"),
        ("steam", "Steam"),
        ("blizzard", "Blizzard"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)

    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES)
    external_account_id = models.CharField(max_length=255)

    verified = models.BooleanField(default=False)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "game", "provider")

    def __str__(self) -> str:
        return f"{self.user} – {self.game} ({self.provider})"


class PatchSuggestion(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="suggestions")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    title = models.CharField(max_length=200)
    description = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title


class PatchSuggestionVote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    suggestion = models.ForeignKey(PatchSuggestion, on_delete=models.CASCADE, related_name="votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "suggestion")


def can_submit_suggestion(user, game) -> bool:
    return LinkedGameAccount.objects.filter(user=user, game=game, verified=True).exists()
