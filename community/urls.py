# -*- coding: utf-8 -*-
"""Web routes for the community app."""

from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    path("", views.home, name="home"),
    path("plans/", views.plan_list, name="plan_list"),
    path("plans/new/", views.plan_create, name="plan_create"),
    path("plans/<int:pk>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:pk>/edit/", views.plan_edit, name="plan_edit"),
    path("plans/<int:pk>/delete/", views.plan_delete, name="plan_delete"),
    path("plans/<int:pk>/checkin/", views.checkin_create, name="checkin_create"),
    path("checkins/<int:pk>/edit/", views.checkin_edit, name="checkin_edit"),
    path("checkins/<int:pk>/delete/", views.checkin_delete, name="checkin_delete"),
    path("my/plans/", views.my_plans, name="my_plans"),
    path("friends/", views.friends, name="friends"),
    path("friends/request/", views.friend_request, name="friend_request"),
    path("friends/<int:pk>/respond/", views.friend_respond, name="friend_respond"),
    path("friends/<int:user_id>/remove/", views.friend_remove, name="friend_remove"),
    path("u/<str:username>/", views.profile, name="profile"),
    path("manage/", views.dashboard, name="dashboard"),
    path("api-docs/", views.api_docs, name="api_docs"),
]
