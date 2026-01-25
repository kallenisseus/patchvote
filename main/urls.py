from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("games/", views.game_list, name="game_list"),
    path("games/<slug:slug>/", views.game_detail, name="game_detail"),
    path("profile/", views.profile, name="profile"),
    path("games/<slug:slug>/patches/<str:version>/",views.patch_detail,name="patch_detail",),
    path("accounts/signup/", views.signup, name="signup"),
]


