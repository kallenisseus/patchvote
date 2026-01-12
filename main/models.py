from django.db import models

class Game(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)

    def __str__(self):
        return self.name


class Patch(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="patches")
    version = models.CharField(max_length=50)
    released_at = models.DateField(null=True, blank=True)
    source_url = models.URLField(blank=True)
    raw_text = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together = ("game", "version")

    def __str__(self):
        return f"{self.game.slug} {self.version}"


class BalanceItem(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=50, default="character")

    class Meta:
        unique_together = ("game", "name")

    def __str__(self):
        return self.name


class Feedback(models.Model):
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
    item = models.ForeignKey(BalanceItem, on_delete=models.CASCADE, related_name="feedback")
    vote = models.CharField(max_length=10, choices=CHOICES)

    skill_band = models.CharField(max_length=30, blank=True)
    mode = models.CharField(max_length=30, blank=True)
    reason_tags = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
