# -*- coding: utf-8 -*-
"""Django admin registrations and branding."""

from django.contrib import admin

from .models import CheckIn, Cheer, Friendship, Plan, Tag

admin.site.site_header = "同频计划 · 课程项目后台"
admin.site.site_title = "同频计划后台"
admin.site.index_title = "数据维护"


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "category",
        "visibility",
        "status",
        "start_date",
        "end_date",
        "created_at",
    )
    list_filter = ("category", "visibility", "status")
    search_fields = ("title", "summary", "owner__username")
    filter_horizontal = ("tags",)
    date_hierarchy = "created_at"


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ("plan", "user", "date", "minutes", "mood", "created_at")
    list_filter = ("mood", "date")
    search_fields = ("plan__title", "user__username", "content")
    date_hierarchy = "date"


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("requester", "addressee", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("requester__username", "addressee__username")


@admin.register(Cheer)
class CheerAdmin(admin.ModelAdmin):
    list_display = ("from_user", "checkin", "content", "created_at")
    search_fields = ("from_user__username", "checkin__user__username", "content")
