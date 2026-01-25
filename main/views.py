
# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import select_template
from .models import Game, Patch, LinkedGameAccount, PatchSuggestion
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login


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
    template = select_template([
        f"games/{game.slug}/game_detail.html",  # game-specific
        "main/game_detail.html",                # fallback
    ])

    return render(request, template.template.name, {
        "game": game,
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


