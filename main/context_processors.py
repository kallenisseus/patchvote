from .models import Game

def current_game(request):
    """
    Inject current_game + active_game_slug based on URL pattern:
    /games/<slug>/...
    """
    path = request.path.strip("/").split("/")

    # Expected: ["games", "<slug>", ...]
    if len(path) >= 2 and path[0] == "games":
        slug = path[1]
        try:
            game = Game.objects.only("id", "name", "slug").get(slug=slug)
            return {
                "current_game": game,
                "active_game_slug": game.slug,
            }
        except Game.DoesNotExist:
            pass

    return {
        "current_game": None,
        "active_game_slug": None,
    }

def navbar_games(request):
    parts = request.path.strip("/").split("/")
    active_slug = None

    # /games/<slug>/...
    if len(parts) >= 2 and parts[0] == "games":
        active_slug = parts[1]

    games = Game.objects.filter(is_active=True).order_by("sort_order", "name")

    return {
        "navbar_games": games,
        "active_game_slug": active_slug,
    }
