from django.db import models

from django.contrib.auth.models import User

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

    def __str__(self):
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

    def __str__(self):
        return f"{self.game.slug} ({self.kind})"
    
    

class Patch(models.Model):
    """
    Represents an official patch released for a game.

    - Created automatically via scraping or API
    - Immutable once created (should not be user-edited)
    """
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="patches")
    version = models.CharField(max_length=50)

    released_at = models.DateField(null=True, blank=True)
    source_url = models.URLField(blank=True)

    # Raw patch notes text (scraped)
    raw_text = models.TextField(blank=True)

    # Used to detect patch changes / duplicates
    content_hash = models.CharField(max_length=64, blank=True)
    source_slug = models.CharField(max_length=200, blank=True)

    raw_html = models.TextField(blank=True, null=True)

    class Meta:
        # A game can only have one patch per version
        unique_together = ("game", "version")

    def __str__(self):
        return f"{self.game.slug} {self.version}"
    

class BalanceItem(models.Model):
    """
    Represents something that can be balanced:
    - Champion
    - Trait
    - Weapon
    - Item
    """
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    kind = models.CharField(
        max_length=50,
        default="character",
        help_text="e.g. character, trait, item"
    )

    class Meta:
        unique_together = ("game", "name")

    def __str__(self):
        return self.name


class Feedback(models.Model):
    """
    Represents a single piece of balance feedback.

    Example:
    - Patch 14.1
    - Champion: Ahri
    - Vote: Nerf
    - Skill band: Diamond+
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

    patch = models.ForeignKey(
        Patch,
        on_delete=models.CASCADE,
        related_name="feedback"
    )

    item = models.ForeignKey(
        BalanceItem,
        on_delete=models.CASCADE,
        related_name="feedback"
    )

    # Optional: tie feedback to a user (verified or anonymous)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Null = anonymous feedback"
    )

    vote = models.CharField(max_length=10, choices=CHOICES)

    # Contextual metadata (used for filtering/analytics)
    skill_band = models.CharField(max_length=30, blank=True)
    mode = models.CharField(max_length=30, blank=True)
    reason_tags = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)



class UserProfile(models.Model):
    """
    Platform-level user profile.

    - Not tied to any specific game
    - Used for moderation, trust, and permissions
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Platform trust flag (manual or automated)
    is_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username



class LinkedGameAccount(models.Model):
    """
    Represents a user's linked external game account.

    Examples:
    - Riot account for TFT
    - Steam account for CS2

    Verification is PER GAME, PER PROVIDER.
    """

    PROVIDER_CHOICES = [
        ("riot", "Riot Games"),
        ("steam", "Steam"),
        ("blizzard", "Blizzard"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)

    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES)
    external_account_id = models.CharField(max_length=255)

    # True once provider verification succeeds
    verified = models.BooleanField(default=False)

    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One account per user per game per provider
        unique_together = ("user", "game", "provider")

    def __str__(self):
        return f"{self.user} – {self.game} ({self.provider})"



class PatchSuggestion(models.Model):
    """
    High-level balance suggestion submitted by users.

    Examples:
    - "Nerf Ahri mana scaling"
    - "Rework Econ traits"

    These may later inspire official patches.
    """

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="suggestions"
    )

    author = models.ForeignKey(User, on_delete=models.CASCADE)

    title = models.CharField(max_length=200)
    description = models.TextField()

    # Moderation state
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title



class PatchSuggestionVote(models.Model):
    """
    Represents a single user's vote on a patch suggestion.

    - One vote per user per suggestion
    - Used for ranking & prioritization
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    suggestion = models.ForeignKey(
        PatchSuggestion,
        on_delete=models.CASCADE,
        related_name="votes"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "suggestion")



def can_submit_suggestion(user, game):
    """
    User may submit suggestions ONLY if:
    - Logged in
    - Has a verified linked account for that game
    """
    return LinkedGameAccount.objects.filter(
        user=user,
        game=game,
        verified=True
    ).exists()
