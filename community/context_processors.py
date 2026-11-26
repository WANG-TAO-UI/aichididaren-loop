# -*- coding: utf-8 -*-
"""Template context shared by every page."""

from .models import Friendship


def site_context(request):
    context = {
        "SITE_NAME": "同频计划",
        "SITE_TAGLINE": "制定计划 · 每日打卡 · 好友互督",
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        context["pending_friend_count"] = Friendship.objects.filter(
            addressee=user, status="pending"
        ).count()
    return context
