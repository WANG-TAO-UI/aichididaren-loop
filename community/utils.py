# -*- coding: utf-8 -*-
"""Small shared helpers for views and the API."""

import json
import re

from django.db.models import Q
from django.http import JsonResponse

from .models import Friendship, Plan, Tag

TAG_SPLIT_RE = re.compile(r"[,，、;；\s]+")


def parse_tag_names(raw, limit=5):
    """Split a tag string and return a deduplicated list, at most *limit*."""
    if not raw:
        return []
    names = []
    for item in TAG_SPLIT_RE.split(str(raw).strip()):
        name = item.strip()
        if not name:
            continue
        if len(name) > 30:
            name = name[:30]
        if name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def tags_for_names(names):
    tags = []
    for name in names:
        tag, _ = Tag.objects.get_or_create(name=name)
        tags.append(tag)
    return tags


def plan_queryset_for(user):
    """All plans the given user is allowed to see."""
    queryset = Plan.objects.select_related("owner").prefetch_related("tags")
    if not user or not user.is_authenticated:
        return queryset.filter(visibility="public")
    if user.is_staff:
        return queryset
    friend_ids = Friendship.friend_ids(user)
    return queryset.filter(
        Q(visibility="public")
        | Q(owner=user)
        | Q(visibility="friends", owner_id__in=friend_ids)
    )


def can_view_checkin(user, checkin):
    return checkin.plan.visible_to(user) and (
        checkin.user_id == checkin.plan.owner_id
    )


def can_cheer(user, checkin):
    """Friends may cheer each other's check-ins; owners cannot cheer themselves."""
    if not user or not user.is_authenticated:
        return False
    if user.pk == checkin.user_id:
        return False
    if user.is_staff:
        return True
    return Friendship.are_friends(user, checkin.user) and checkin.plan.visible_to(user)


def json_payload(request):
    """Parse a JSON body, returning (data, error_response)."""
    try:
        if request.body:
            data = json.loads(request.body.decode("utf-8"))
            if not isinstance(data, dict):
                return None, JsonResponse(
                    {"error": "请求体必须是 JSON 对象。"}, status=400
                )
            return data, None
        return {}, None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({"error": "JSON 格式不合法。"}, status=400)


def paginate_queryset(queryset, page, per_page=10, max_per_page=50):
    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(max_per_page, max(1, int(per_page or 10)))
    except (TypeError, ValueError):
        per_page = 10
    total = queryset.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start = (page - 1) * per_page
    return {
        "count": total,
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "results": list(queryset[start : start + per_page]),
    }
