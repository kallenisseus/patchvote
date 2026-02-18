
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import select_template
from .models import Game, Patch, LinkedGameAccount, PatchSuggestion
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from main.parsers.tft_patch_parser import parse_tft_patch

import re



from django.shortcuts import get_object_or_404, render
from django.db.models import Q

from .models import Game, Patch, Champion, Item


def _patch_set_key(patch: Patch) -> int:
    """
    Patch version like '16.1' => set_key 16
    """
    try:
        major = int((patch.version or "").split(".")[0])
        return major
    except Exception:
        return 0


def patch_champions(request, game_slug: str, version: str):
    game = get_object_or_404(Game, slug=game_slug)
    patch = get_object_or_404(Patch, game=game, version=version)

    set_key = _patch_set_key(patch)

    champs = (
        Champion.objects
        .filter(game=game, set_key=set_key)
        .order_by("cost", "name")
    )

    return render(request, "games/tft/patch_champions.html", {
        "game": game,
        "patch": patch,
        "set_key": set_key,
        "champions": champs,
    })


def patch_items(request, game_slug: str, version: str):
    game = get_object_or_404(Game, slug=game_slug)
    patch = get_object_or_404(Patch, game=game, version=version)

    set_key = _patch_set_key(patch)

    items = (
        Item.objects
        .filter(game=game)
        .filter(Q(set_key=0) | Q(set_key=set_key))  # global + set items
        .order_by("kind", "subgroup", "name")
    )

    # split into buckets for the template
    buckets = {
        "core": [],
        "radiant": [],
        "artifact": [],
        "set": [],
    }
    for it in items:
        buckets.get(it.kind, buckets["core"]).append(it)

    return render(request, "games/tft/patch_items.html", {
        "game": game,
        "patch": patch,
        "set_key": set_key,
        "buckets": buckets,
    })


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")  # 👈 THIS logs the user in
            return redirect("home")
    else:
        form = UserCreationForm()

    return render(request, "registration/signup.html", {"form": form})


def home(request):
    return render(request, "main/home.html")

def game_list(request):
    games = Game.objects.order_by("name")
    return render(request, "main/game_list.html", {"games": games})


def game_detail(request, slug):
    game = get_object_or_404(Game, slug=slug)

    patches = list(Patch.objects.filter(game=game))

    def vkey(p):
        m = re.match(r"^(\d+)\.(\d+)$", (p.version or "").strip())
        if not m:
            return (-1, -1)  # okända versioner hamnar längst ner
        return (int(m.group(1)), int(m.group(2)))

    patches.sort(key=vkey, reverse=True)

    template = select_template([
        f"games/{game.slug}/game_detail.html",
        "main/game_detail.html",
    ])

    return render(request, template.template.name, {
        "game": game,
        "patches": patches,   # <-- viktig
    })

def patch_detail(request, slug, version):
    game = get_object_or_404(Game, slug=slug)
    patch = get_object_or_404(Patch, game=game, version=version)

    sections = None
    if game.slug == "tft":
        sections = parse_tft_patch(
            raw_text=patch.raw_text or "",
            raw_html=patch.raw_html or None,
        )

    return render(request, "games/tft/patch_detail.html", {
        "game": game,
        "patch": patch,
        "sections": sections,  # <-- new
    })


@login_required
def profile(request):
    user = request.user

    linked_accounts = (
        LinkedGameAccount.objects
        .select_related("game")
        .filter(user=user)
        .order_by("game__name", "provider")
    )

    suggestions = (
        PatchSuggestion.objects
        .select_related("game")
        .filter(author=user)
        .order_by("-created_at")
    )

    return render(request, "account/profile.html", {
        "profile_user": user,
        "linked_accounts": linked_accounts,
        "suggestions": suggestions,
    })


