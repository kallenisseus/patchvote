

# Register your models here.
from django.contrib import admin
from .models import Game, Patch, BalanceItem, Feedback, GameImage

admin.site.register(Patch)
admin.site.register(BalanceItem)
admin.site.register(Feedback)


class GameImageInline(admin.TabularInline):
    model = GameImage
    extra = 1

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ("name", "slug", "is_active", "sort_order")
    inlines = [GameImageInline]