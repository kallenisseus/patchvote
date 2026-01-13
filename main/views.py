
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Game, Patch
def home(request):
    return render(request, "main/home.html")

def game_list(request):
    games = Game.objects.order_by("name")
    return render(request, "main/game_list.html", {"games": games})


def game_detail(request, slug):
    game = get_object_or_404(Game, slug=slug)

    patches = Patch.objects.filter(game=game).order_by(
        "-released_at", "-version"
    )

    return render(request, "main/game_detail.html", {
        "game": game,
        "patches": patches,
    })


def patch_detail(request, slug, version):
    game = get_object_or_404(Game, slug=slug)
    patch = get_object_or_404(Patch, game=game, version=version)
    return render(request, "main/patch_detail.html", {
        "game": game,
        "patch": patch,
    })


@login_required
def profile(request):
    return render(request, "main/profile.html")
