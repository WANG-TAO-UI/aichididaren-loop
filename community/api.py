# -*- coding: utf-8 -*-
"""Session-authenticated REST API under /api/v1/."""

import json
from datetime import date, timedelta
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import CheckIn, Cheer, Friendship, Plan, Tag
from .utils import (
    can_cheer,
    json_payload,
    paginate_queryset,
    plan_queryset_for,
    tags_for_names,
)


def api_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "请先登录后再调用该接口。"}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper


def _user_dict(user):
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "date_joined": user.date_joined.isoformat(),
    }


def _plan_dict(plan):
    cover = ""
    if plan.cover:
        try:
            cover = plan.cover.url
        except ValueError:
            cover = ""
    return {
        "id": plan.pk,
        "title": plan.title,
        "summary": plan.summary,
        "description": plan.description,
        "category": plan.category,
        "category_label": plan.category_label,
        "tags": [{"id": tag.pk, "name": tag.name} for tag in plan.tags.all()],
        "cover": cover,
        "owner": _user_dict(plan.owner),
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat(),
        "daily_target": plan.daily_target,
        "visibility": plan.visibility,
        "visibility_label": plan.get_visibility_display(),
        "status": plan.status,
        "status_label": plan.get_status_display(),
        "duration_days": plan.duration_days,
        "checked_days": plan.checked_days,
        "total_minutes": plan.total_minutes,
        "progress_percent": plan.progress_percent,
        "current_streak": plan.current_streak,
        "cheer_total": plan.cheer_total,
        "created_at": plan.created_at.isoformat(),
        "url": plan.get_absolute_url(),
    }


def _checkin_dict(checkin, request=None):
    image = ""
    if checkin.image:
        try:
            image = checkin.image.url
        except ValueError:
            image = ""
    cheered = False
    if request and request.user.is_authenticated:
        cheered = checkin.cheers.filter(from_user=request.user).exists()
    return {
        "id": checkin.pk,
        "plan_id": checkin.plan_id,
        "plan_title": checkin.plan.title,
        "user": _user_dict(checkin.user),
        "date": checkin.date.isoformat(),
        "minutes": checkin.minutes,
        "content": checkin.content,
        "mood": checkin.mood,
        "mood_label": checkin.mood_label,
        "image": image,
        "cheer_count": checkin.cheers.count(),
        "cheered_by_me": cheered,
        "created_at": checkin.created_at.isoformat(),
    }


def _friendship_dict(friendship):
    return {
        "id": friendship.pk,
        "requester": _user_dict(friendship.requester),
        "addressee": _user_dict(friendship.addressee),
        "status": friendship.status,
        "status_label": friendship.get_status_display(),
        "created_at": friendship.created_at.isoformat(),
    }


def _parse_date(value, default=None):
    if value in (None, ""):
        return default
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@ensure_csrf_cookie
def api_csrf(request):
    return JsonResponse({"csrf_token": get_token(request)})


@require_POST
@ensure_csrf_cookie
def api_login(request):
    data, error = json_payload(request)
    if error:
        return error
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return JsonResponse({"error": "用户名和密码都不能为空。"}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"error": "用户名或密码不正确。"}, status=400)
    if not user.is_active:
        return JsonResponse({"error": "该账号已被停用。"}, status=403)
    login(request, user)
    return JsonResponse(
        {"message": "登录成功。", "user": _user_dict(user), "csrf_token": get_token(request)}
    )


@require_POST
@api_login_required
def api_logout(request):
    logout(request)
    return JsonResponse({"message": "已退出登录。"})


@api_login_required
def api_me(request):
    return JsonResponse(
        {
            "user": _user_dict(request.user),
            "plan_count": Plan.objects.filter(owner=request.user).count(),
            "checkin_count": CheckIn.objects.filter(user=request.user).count(),
            "friend_count": len(Friendship.friend_ids(request.user)),
            "pending_friend_count": Friendship.objects.filter(
                addressee=request.user, status="pending"
            ).count(),
        }
    )


@require_http_methods(["GET", "POST"])
def api_plans(request):
    if request.method == "GET":
        queryset = plan_queryset_for(request.user)
        query = request.GET.get("q", "").strip()
        tag_id = request.GET.get("tag", "").strip()
        category = request.GET.get("category", "").strip()
        sort = request.GET.get("sort", "latest").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(owner__username__icontains=query)
            )
        if tag_id.isdigit():
            queryset = queryset.filter(tags__pk=int(tag_id))
        if category in dict(Plan.CATEGORY_CHOICES):
            queryset = queryset.filter(category=category)
        queryset = queryset.annotate(
            checkin_count=Count("checkins", distinct=True),
            cheer_count=Count("checkins__cheers", distinct=True),
        )
        if sort == "hot":
            queryset = queryset.order_by("-checkin_count", "-created_at")
        elif sort == "cheers":
            queryset = queryset.order_by("-cheer_count", "-created_at")
        elif sort == "ending":
            queryset = queryset.filter(end_date__gte=timezone.localdate()).order_by("end_date")
        else:
            queryset = queryset.order_by("-created_at")
        payload = paginate_queryset(
            queryset,
            request.GET.get("page"),
            request.GET.get("per_page", 10),
        )
        payload["results"] = [_plan_dict(plan) for plan in payload["results"]]
        return JsonResponse(payload)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "请先登录后再创建计划。"}, status=401)
    data, error = json_payload(request)
    if error:
        return error
    start_date = _parse_date(data.get("start_date"), timezone.localdate())
    if start_date is None:
        return JsonResponse({"error": "start_date 格式应为 YYYY-MM-DD。"}, status=400)
    end_date = _parse_date(data.get("end_date"), start_date + timedelta(days=20))
    if end_date is None:
        return JsonResponse({"error": "end_date 格式应为 YYYY-MM-DD。"}, status=400)
    try:
        daily_target = int(data.get("daily_target", 60))
    except (TypeError, ValueError):
        return JsonResponse({"error": "daily_target 必须是整数。"}, status=400)
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        return JsonResponse({"error": "tags 必须是字符串数组。"}, status=400)
    if len(tags) > 5:
        return JsonResponse({"error": "标签最多 5 个。"}, status=400)

    plan = Plan(
        owner=request.user,
        title=(data.get("title") or "").strip(),
        summary=(data.get("summary") or "").strip(),
        description=(data.get("description") or "").strip(),
        category=data.get("category", "other"),
        start_date=start_date,
        end_date=end_date,
        daily_target=daily_target,
        visibility=data.get("visibility", "public"),
        status=data.get("status", "active"),
    )
    try:
        plan.full_clean()
    except ValidationError as exc:
        return JsonResponse(
            {"error": "参数校验失败。", "details": exc.message_dict}, status=400
        )
    plan.save()
    plan.tags.set(tags_for_names([str(tag).strip() for tag in tags if str(tag).strip()]))
    return JsonResponse(_plan_dict(plan), status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def api_plan_detail(request, pk):
    plan = Plan.objects.filter(pk=pk).select_related("owner").prefetch_related("tags").first()
    if not plan:
        return JsonResponse({"error": "计划不存在。"}, status=404)
    if not plan.visible_to(request.user):
        return JsonResponse({"error": "没有权限查看这个计划。"}, status=403)

    if request.method == "GET":
        return JsonResponse(_plan_dict(plan))

    if not request.user.is_authenticated:
        return JsonResponse({"error": "请先登录。"}, status=401)
    if not (request.user.is_staff or plan.owner_id == request.user.pk):
        return JsonResponse({"error": "只有计划发起人可以修改或删除。"}, status=403)

    if request.method == "DELETE":
        plan.delete()
        return JsonResponse({"message": "计划已删除。"}, status=204)

    data, error = json_payload(request)
    if error:
        return error
    if "title" in data:
        plan.title = (data.get("title") or "").strip()
    if "summary" in data:
        plan.summary = (data.get("summary") or "").strip()
    if "description" in data:
        plan.description = (data.get("description") or "").strip()
    if "category" in data:
        plan.category = data["category"]
    if "visibility" in data:
        plan.visibility = data["visibility"]
    if "status" in data:
        plan.status = data["status"]
    if "daily_target" in data:
        try:
            plan.daily_target = int(data["daily_target"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "daily_target 必须是整数。"}, status=400)
    if "start_date" in data:
        parsed = _parse_date(data["start_date"])
        if parsed is None:
            return JsonResponse({"error": "start_date 格式应为 YYYY-MM-DD。"}, status=400)
        plan.start_date = parsed
    if "end_date" in data:
        parsed = _parse_date(data["end_date"])
        if parsed is None:
            return JsonResponse({"error": "end_date 格式应为 YYYY-MM-DD。"}, status=400)
        plan.end_date = parsed
    if "tags" in data:
        if not isinstance(data["tags"], list) or len(data["tags"]) > 5:
            return JsonResponse({"error": "tags 必须是数组且最多 5 个。"}, status=400)
    try:
        plan.full_clean()
    except ValidationError as exc:
        return JsonResponse(
            {"error": "参数校验失败。", "details": exc.message_dict}, status=400
        )
    plan.save()
    if "tags" in data:
        plan.tags.set(
            tags_for_names([str(tag).strip() for tag in data["tags"] if str(tag).strip()])
        )
    return JsonResponse(_plan_dict(plan))


@require_http_methods(["GET", "POST"])
def api_plan_checkins(request, pk):
    plan = Plan.objects.filter(pk=pk).select_related("owner").first()
    if not plan:
        return JsonResponse({"error": "计划不存在。"}, status=404)
    if not plan.visible_to(request.user):
        return JsonResponse({"error": "没有权限查看这个计划。"}, status=403)

    if request.method == "GET":
        queryset = plan.checkins.select_related("user").order_by("-date", "-created_at")
        payload = paginate_queryset(
            queryset, request.GET.get("page"), request.GET.get("per_page", 10)
        )
        payload["results"] = [_checkin_dict(item, request) for item in payload["results"]]
        return JsonResponse(payload)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "请先登录。"}, status=401)
    if plan.owner_id != request.user.pk:
        return JsonResponse({"error": "只有计划发起人可以打卡。"}, status=403)
    if plan.status != "active":
        return JsonResponse({"error": "这个计划已经结束或已放弃，不能新增打卡。"}, status=400)
    data, error = json_payload(request)
    if error:
        return error
    checkin_date = _parse_date(data.get("date"), timezone.localdate())
    if checkin_date is None:
        return JsonResponse({"error": "date 格式应为 YYYY-MM-DD。"}, status=400)
    if checkin_date > timezone.localdate():
        return JsonResponse({"error": "不能给未来的日期打卡。"}, status=400)
    if not (plan.start_date <= checkin_date <= plan.end_date):
        return JsonResponse({"error": "date 必须在计划起止日期内。"}, status=400)
    if CheckIn.objects.filter(plan=plan, date=checkin_date).exists():
        return JsonResponse({"error": "这个计划当天已经打卡了。"}, status=409)
    try:
        minutes = int(data.get("minutes", 60))
    except (TypeError, ValueError):
        return JsonResponse({"error": "minutes 必须是整数。"}, status=400)
    checkin = CheckIn(
        plan=plan,
        user=request.user,
        date=checkin_date,
        minutes=minutes,
        content=(data.get("content") or "").strip(),
        mood=data.get("mood", "good"),
    )
    try:
        checkin.full_clean()
        checkin.save()
    except ValidationError as exc:
        return JsonResponse(
            {"error": "参数校验失败。", "details": exc.message_dict}, status=400
        )
    except IntegrityError:
        return JsonResponse({"error": "这个计划当天已经打卡了。"}, status=409)
    return JsonResponse(_checkin_dict(checkin, request), status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def api_checkin_detail(request, pk):
    checkin = CheckIn.objects.filter(pk=pk).select_related("plan", "user").first()
    if not checkin:
        return JsonResponse({"error": "打卡记录不存在。"}, status=404)
    if not checkin.plan.visible_to(request.user):
        return JsonResponse({"error": "没有权限查看这条打卡。"}, status=403)

    if request.method == "GET":
        return JsonResponse(_checkin_dict(checkin, request))

    if not request.user.is_authenticated:
        return JsonResponse({"error": "请先登录。"}, status=401)
    if not (request.user.is_staff or checkin.user_id == request.user.pk):
        return JsonResponse({"error": "只有打卡人可以修改或删除。"}, status=403)

    if request.method == "DELETE":
        checkin.delete()
        return JsonResponse({"message": "打卡记录已删除。"}, status=204)

    data, error = json_payload(request)
    if error:
        return error
    if "date" in data:
        parsed = _parse_date(data["date"])
        if parsed is None:
            return JsonResponse({"error": "date 格式应为 YYYY-MM-DD。"}, status=400)
        if parsed > timezone.localdate():
            return JsonResponse({"error": "不能给未来的日期打卡。"}, status=400)
        if not (checkin.plan.start_date <= parsed <= checkin.plan.end_date):
            return JsonResponse({"error": "date 必须在计划起止日期内。"}, status=400)
        if (
            CheckIn.objects.filter(plan=checkin.plan, date=parsed)
            .exclude(pk=checkin.pk)
            .exists()
        ):
            return JsonResponse({"error": "该日期已有打卡记录。"}, status=409)
        checkin.date = parsed
    if "minutes" in data:
        try:
            checkin.minutes = int(data["minutes"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "minutes 必须是整数。"}, status=400)
    if "content" in data:
        checkin.content = (data.get("content") or "").strip()
    if "mood" in data:
        checkin.mood = data["mood"]
    try:
        checkin.full_clean()
        checkin.save()
    except ValidationError as exc:
        return JsonResponse(
            {"error": "参数校验失败。", "details": exc.message_dict}, status=400
        )
    except IntegrityError:
        return JsonResponse({"error": "该日期已有打卡记录。"}, status=409)
    return JsonResponse(_checkin_dict(checkin, request))


@require_http_methods(["POST", "DELETE"])
def api_checkin_cheer(request, pk):
    checkin = CheckIn.objects.filter(pk=pk).select_related("plan", "user").first()
    if not checkin:
        return JsonResponse({"error": "打卡记录不存在。"}, status=404)
    if not checkin.plan.visible_to(request.user):
        return JsonResponse({"error": "没有权限查看这条打卡。"}, status=403)
    if not request.user.is_authenticated:
        return JsonResponse({"error": "请先登录。"}, status=401)

    if request.method == "DELETE":
        Cheer.objects.filter(checkin=checkin, from_user=request.user).delete()
        return JsonResponse({"message": "已取消鼓励。"}, status=204)

    if not can_cheer(request.user, checkin):
        return JsonResponse({"error": "只有互督好友可以鼓励，且不能给自己留言。"}, status=403)
    if Cheer.objects.filter(checkin=checkin, from_user=request.user).exists():
        return JsonResponse({"error": "你已经鼓励过这条打卡了。"}, status=409)
    data, error = json_payload(request)
    if error:
        return error
    content = (data.get("content") or "").strip()[:120] or "继续加油！"
    Cheer.objects.create(checkin=checkin, from_user=request.user, content=content)
    return JsonResponse(
        {"message": "鼓励已送达。", "cheer_count": checkin.cheers.count()}, status=201
    )


@require_http_methods(["GET", "POST"])
@api_login_required
def api_friends(request):
    if request.method == "GET":
        accepted = Friendship.objects.filter(status="accepted").filter(
            Q(requester=request.user) | Q(addressee=request.user)
        ).select_related("requester", "addressee")
        received = Friendship.objects.filter(
            addressee=request.user, status="pending"
        ).select_related("requester", "addressee")
        sent = Friendship.objects.filter(
            requester=request.user, status="pending"
        ).select_related("requester", "addressee")
        return JsonResponse(
            {
                "friends": [_friendship_dict(item) for item in accepted],
                "pending_received": [_friendship_dict(item) for item in received],
                "pending_sent": [_friendship_dict(item) for item in sent],
            }
        )

    data, error = json_payload(request)
    if error:
        return error
    username = (data.get("username") or "").strip()
    target = User.objects.filter(username__iexact=username, is_active=True).first()
    if not target:
        return JsonResponse({"error": "没有找到这个用户。"}, status=404)
    if target.pk == request.user.pk:
        return JsonResponse({"error": "不能添加自己为好友。"}, status=400)
    if Friendship.are_friends(request.user, target):
        return JsonResponse({"error": "你们已经是互督好友了。"}, status=409)
    pending = Friendship.pending_between(request.user, target)
    if pending:
        return JsonResponse({"error": "已有待处理的好友请求。"}, status=409)
    friendship = Friendship.objects.create(requester=request.user, addressee=target)
    return JsonResponse(_friendship_dict(friendship), status=201)


@require_POST
@api_login_required
def api_friend_accept(request, pk):
    friendship = Friendship.objects.filter(pk=pk).select_related(
        "requester", "addressee"
    ).first()
    if not friendship:
        return JsonResponse({"error": "好友请求不存在。"}, status=404)
    if friendship.addressee_id != request.user.pk:
        return JsonResponse({"error": "这条请求不属于你。"}, status=403)
    if friendship.status != "pending":
        return JsonResponse({"error": "这条请求已经处理过了。"}, status=409)
    friendship.status = "accepted"
    friendship.save(update_fields=["status", "updated_at"])
    return JsonResponse(_friendship_dict(friendship))


@require_POST
@api_login_required
def api_friend_reject(request, pk):
    friendship = Friendship.objects.filter(pk=pk).select_related(
        "requester", "addressee"
    ).first()
    if not friendship:
        return JsonResponse({"error": "好友请求不存在。"}, status=404)
    if friendship.addressee_id != request.user.pk:
        return JsonResponse({"error": "这条请求不属于你。"}, status=403)
    if friendship.status != "pending":
        return JsonResponse({"error": "这条请求已经处理过了。"}, status=409)
    friendship.status = "rejected"
    friendship.save(update_fields=["status", "updated_at"])
    return JsonResponse(_friendship_dict(friendship))


@require_http_methods(["DELETE"])
@api_login_required
def api_friend_delete(request, pk):
    friendship = Friendship.objects.filter(pk=pk).first()
    if not friendship:
        return JsonResponse({"error": "好友关系不存在。"}, status=404)
    if request.user.pk not in (friendship.requester_id, friendship.addressee_id):
        return JsonResponse({"error": "这条关系不属于你。"}, status=403)
    friendship.delete()
    return JsonResponse({"message": "已解除互督关系。"}, status=204)


@require_GET
def api_tags(request):
    tags = Tag.objects.annotate(
        plan_count=Count("plans", distinct=True)
    ).order_by("-plan_count", "name")
    return JsonResponse(
        {
            "count": tags.count(),
            "results": [
                {"id": tag.pk, "name": tag.name, "plan_count": tag.plan_count}
                for tag in tags
            ],
        }
    )


@require_GET
def api_stats(request):
    today = timezone.localdate()
    public_plans = Plan.objects.filter(visibility="public")
    top_plans = (
        public_plans.annotate(checkin_count=Count("checkins", distinct=True))
        .filter(checkin_count__gt=0)
        .order_by("-checkin_count", "-created_at")[:5]
    )
    return JsonResponse(
        {
            "plans": public_plans.count(),
            "active_plans": public_plans.filter(status="active").count(),
            "checkins_today": CheckIn.objects.filter(
                date=today, plan__visibility="public"
            ).count(),
            "members": User.objects.filter(is_active=True).count(),
            "cheers": Cheer.objects.count(),
            "top_plans": [
                {
                    "id": plan.pk,
                    "title": plan.title,
                    "owner": plan.owner.username,
                    "checkin_count": plan.checkin_count,
                }
                for plan in top_plans
            ],
        }
    )


@require_GET
def api_docs_payload(request):
    """Small machine-readable index used by the docs page."""
    endpoints = [
        {"method": "GET", "path": "/api/v1/csrf/", "desc": "获取 CSRF Token"},
        {"method": "POST", "path": "/api/v1/auth/login/", "desc": "登录并建立会话"},
        {"method": "POST", "path": "/api/v1/auth/logout/", "desc": "退出登录"},
        {"method": "GET", "path": "/api/v1/me/", "desc": "当前用户与统计"},
        {"method": "GET", "path": "/api/v1/plans/", "desc": "计划列表，支持 q/tag/sort/page"},
        {"method": "POST", "path": "/api/v1/plans/", "desc": "创建计划"},
        {"method": "GET", "path": "/api/v1/plans/{id}/", "desc": "计划详情"},
        {"method": "PUT", "path": "/api/v1/plans/{id}/", "desc": "修改计划"},
        {"method": "DELETE", "path": "/api/v1/plans/{id}/", "desc": "删除计划"},
        {"method": "GET", "path": "/api/v1/plans/{id}/checkins/", "desc": "计划打卡列表"},
        {"method": "POST", "path": "/api/v1/plans/{id}/checkins/", "desc": "新增打卡"},
        {"method": "GET", "path": "/api/v1/checkins/{id}/", "desc": "打卡详情"},
        {"method": "PUT", "path": "/api/v1/checkins/{id}/", "desc": "修改打卡"},
        {"method": "DELETE", "path": "/api/v1/checkins/{id}/", "desc": "删除打卡"},
        {"method": "POST", "path": "/api/v1/checkins/{id}/cheer/", "desc": "给好友打卡鼓励"},
        {"method": "DELETE", "path": "/api/v1/checkins/{id}/cheer/", "desc": "取消鼓励"},
        {"method": "GET", "path": "/api/v1/friends/", "desc": "好友与待处理请求"},
        {"method": "POST", "path": "/api/v1/friends/", "desc": "发送好友请求"},
        {"method": "POST", "path": "/api/v1/friends/{id}/accept/", "desc": "接受请求"},
        {"method": "POST", "path": "/api/v1/friends/{id}/reject/", "desc": "拒绝请求"},
        {"method": "DELETE", "path": "/api/v1/friends/{id}/", "desc": "解除好友关系"},
        {"method": "GET", "path": "/api/v1/tags/", "desc": "标签列表"},
        {"method": "GET", "path": "/api/v1/stats/", "desc": "公开统计"},
    ]
    return JsonResponse({"endpoints": endpoints})
