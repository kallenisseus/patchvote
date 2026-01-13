from .models import Game

def navbar_games(request):
    return {"NAV_GAMES": Game.objects.order_by("name")}
