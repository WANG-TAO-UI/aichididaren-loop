# -*- coding: utf-8 -*-
"""REST API routes."""

from django.urls import path

from . import api

app_name = "api"

urlpatterns = [
    path("csrf/", api.api_csrf, name="csrf"),
    path("auth/login/", api.api_login, name="login"),
    path("auth/logout/", api.api_logout, name="logout"),
    path("me/", api.api_me, name="me"),
    path("plans/", api.api_plans, name="plans"),
    path("plans/<int:pk>/", api.api_plan_detail, name="plan-detail"),
    path("plans/<int:pk>/checkins/", api.api_plan_checkins, name="plan-checkins"),
    path("checkins/<int:pk>/", api.api_checkin_detail, name="checkin-detail"),
    path("checkins/<int:pk>/cheer/", api.api_checkin_cheer, name="checkin-cheer"),
    path("friends/", api.api_friends, name="friends"),
    path("friends/<int:pk>/accept/", api.api_friend_accept, name="friend-accept"),
    path("friends/<int:pk>/reject/", api.api_friend_reject, name="friend-reject"),
    path("friends/<int:pk>/", api.api_friend_delete, name="friend-delete"),
    path("tags/", api.api_tags, name="tags"),
    path("stats/", api.api_stats, name="stats"),
    path("docs/", api.api_docs_payload, name="docs"),
]
