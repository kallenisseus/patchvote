

# Register your models here.
from django.contrib import admin
from .models import Game, Patch, BalanceItem, Feedback

admin.site.register(Game)
admin.site.register(Patch)
admin.site.register(BalanceItem)
admin.site.register(Feedback)
