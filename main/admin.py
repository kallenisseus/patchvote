

from django.contrib import admin
from .models import (
    Game, GameImage, Patch, PatchSection,
    Champion, Trait, Item, Augment,
    EntityChange, Feedback,
    LinkedGameAccount, PatchSuggestion, PatchSuggestionVote
)

@admin.register(Patch)
class PatchAdmin(admin.ModelAdmin):
    list_display = ("game", "version", "updated_at")
    list_filter = ("game",)
    search_fields = ("version", "source_url")

@admin.register(PatchSection)
class PatchSectionAdmin(admin.ModelAdmin):
    list_display = ("patch", "category", "size", "h4", "order")
    list_filter = ("category", "size", "patch__game")
    search_fields = ("h2", "h4", "text")

admin.site.register(Champion)
admin.site.register(Trait)
admin.site.register(Item)
admin.site.register(Augment)
admin.site.register(EntityChange)
admin.site.register(Feedback)

admin.site.register(LinkedGameAccount)
admin.site.register(PatchSuggestion)
admin.site.register(PatchSuggestionVote)

class GameImageInline(admin.TabularInline):
    model = GameImage
    extra = 1

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ("name", "slug", "is_active", "sort_order")
    inlines = [GameImageInline]
