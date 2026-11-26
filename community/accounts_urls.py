# -*- coding: utf-8 -*-
"""Account routes mounted at /accounts/."""

from django.urls import path

from . import accounts_views

app_name = "accounts"

urlpatterns = [
    path("login/", accounts_views.login_view, name="login"),
    path("register/", accounts_views.register_view, name="register"),
    path("logout/", accounts_views.logout_view, name="logout"),
]
