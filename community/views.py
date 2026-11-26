# -*- coding: utf-8 -*-
"""Web pages for the StudyLoop community."""

from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    CheckInForm,
    CheerForm,
    FriendRequestForm,
    PlanForm,
    TagForm,
)
from .models import CheckIn, Cheer, Friendship, Plan, Tag
from .utils import plan_queryset_for, tags_for_names


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(), login_url=reverse("accounts:login")
            )
        if not request.user.is_staff:
            raise PermissionDenied("站务管理仅对站务成员开放。")
        return view_func(request, *args, **kwargs)

    return wrapper


def _page(request, queryset, per_page):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def _base_query(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def home(request):
    today = timezone.localdate()
    public_active = Plan.objects.filter(visibility="public", status="active")
    stats = {
        "plans": public_active.count(),
        "today_checkins": CheckIn.objects.filter(
            date=today, plan__visibility="public"
        ).count(),
        "members": User.objects.filter(is_active=True).count(),
        "cheers": Cheer.objects.count(),
    }
    featured = (
        public_active.select_related("owner")
        .prefetch_related("tags")
        .annotate(checkin_count=Count("checkins", distinct=True))
        .order_by("-created_at")[:3]
    )
    today_feed = (
        CheckIn.objects.filter(date=today, plan__visibility="public")
        .select_related("plan", "user", "plan__owner")
        .prefetch_related("cheers")
        .order_by("-created_at")[:6]
    )
    week_start = today - timedelta(days=6)
    leaderboard = (
        User.objects.filter(is_active=True)
        .annotate(
            week_checkins=Count(
                "checkins", filter=Q(checkins__date__gte=week_start), distinct=True
            ),
            week_minutes=Sum(
                "checkins__minutes", filter=Q(checkins__date__gte=week_start)
            ),
        )
        .filter(week_checkins__gt=0)
        .order_by("-week_checkins", "-week_minutes")[:5]
    )
    top_tags = (
        Tag.objects.annotate(
            plan_count=Count(
                "plans", filter=Q(plans__visibility="public"), distinct=True
            )
        )
        .filter(plan_count__gt=0)
        .order_by("-plan_count", "name")[:8]
    )
    friend_feed = []
    my_plans = []
    if request.user.is_authenticated:
        friend_ids = Friendship.friend_ids(request.user)
        friend_feed = (
            CheckIn.objects.filter(user_id__in=friend_ids)
            .filter(plan__visibility__in=["public", "friends"])
            .select_related("plan", "user")
            .order_by("-date", "-created_at")[:5]
        )
        my_plans = (
            Plan.objects.filter(owner=request.user)
            .prefetch_related("tags")
            .order_by("-updated_at")[:4]
        )
    return render(
        request,
        "community/home.html",
        {
            "stats": stats,
            "featured": featured,
            "today_feed": today_feed,
            "leaderboard": leaderboard,
            "top_tags": top_tags,
            "friend_feed": friend_feed,
            "my_plans": my_plans,
            "today": today,
        },
    )


def plan_list(request):
    queryset = plan_queryset_for(request.user)
    query = request.GET.get("q", "").strip()
    tag_id = request.GET.get("tag", "").strip()
    category = request.GET.get("category", "").strip()
    sort = request.GET.get("sort", "latest").strip()

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(description__icontains=query)
            | Q(owner__username__icontains=query)
        )
    selected_tag = None
    if tag_id.isdigit():
        selected_tag = Tag.objects.filter(pk=int(tag_id)).first()
        if selected_tag:
            queryset = queryset.filter(tags=selected_tag)
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
        sort = "latest"
        queryset = queryset.order_by("-created_at")

    page_obj = _page(request, queryset, 9)
    tags = (
        Tag.objects.annotate(
            plan_count=Count(
                "plans", filter=Q(plans__visibility="public"), distinct=True
            )
        )
        .filter(plan_count__gt=0)
        .order_by("-plan_count", "name")
    )
    return render(
        request,
        "community/plan_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "selected_tag": selected_tag,
            "category": category,
            "sort": sort,
            "tags": tags,
            "categories": Plan.CATEGORY_CHOICES,
            "base_query": _base_query(request),
        },
    )


def plan_detail(request, pk):
    plan = get_object_or_404(
        Plan.objects.select_related("owner").prefetch_related("tags"), pk=pk
    )
    if not plan.visible_to(request.user):
        raise PermissionDenied("这个计划仅对发起人或好友可见。")

    checkins_qs = (
        plan.checkins.select_related("user")
        .prefetch_related("cheers__from_user")
        .order_by("-date", "-created_at")
    )
    checkin_page = _page(request, checkins_qs, 5)
    page_checkins = list(checkin_page.object_list)

    is_owner = request.user.is_authenticated and request.user.pk == plan.owner_id
    can_manage = is_owner or (
        request.user.is_authenticated and request.user.is_staff
    )
    is_friend = (
        request.user.is_authenticated
        and Friendship.are_friends(request.user, plan.owner)
    )
    pending_request = None
    if request.user.is_authenticated and request.user.pk != plan.owner_id:
        pending_request = Friendship.pending_between(request.user, plan.owner)
    cheered_ids = set()
    if request.user.is_authenticated and page_checkins:
        cheered_ids = set(
            Cheer.objects.filter(
                from_user=request.user, checkin_id__in=[c.pk for c in page_checkins]
            ).values_list("checkin_id", flat=True)
        )

    owner_stats = {
        "plans": Plan.objects.filter(owner=plan.owner).count(),
        "checkins": CheckIn.objects.filter(user=plan.owner).count(),
        "minutes": CheckIn.objects.filter(user=plan.owner).aggregate(
            total=Sum("minutes")
        )["total"]
        or 0,
    }
    related = (
        Plan.objects.filter(visibility="public", status="active", category=plan.category)
        .exclude(pk=plan.pk)
        .select_related("owner")
        .prefetch_related("tags")[:3]
    )
    today = timezone.localdate()
    today_checkin = plan.today_checkin
    can_checkin_today = (
        is_owner
        and not today_checkin
        and plan.start_date <= today <= plan.end_date
        and plan.status == "active"
    )
    return render(
        request,
        "community/plan_detail.html",
        {
            "plan": plan,
            "checkin_page": checkin_page,
            "checkins": page_checkins,
            "is_owner": is_owner,
            "can_manage": can_manage,
            "is_friend": is_friend,
            "pending_request": pending_request,
            "cheered_ids": cheered_ids,
            "owner_stats": owner_stats,
            "related": related,
            "today": today,
            "today_checkin": today_checkin,
            "can_checkin_today": can_checkin_today,
            "cheer_form": CheerForm(),
            "base_query": _base_query(request),
        },
    )


@login_required
def plan_create(request):
    if request.method == "POST":
        form = PlanForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.owner = request.user
            plan.save()
            plan.tags.set(tags_for_names(form.cleaned_data.get("tags_text", [])))
            messages.success(request, "计划已创建，今天就可以开始第一次打卡。")
            return redirect("community:plan_detail", pk=plan.pk)
        messages.error(request, "计划没有保存成功，请检查表单提示。")
    else:
        today = timezone.localdate()
        form = PlanForm(
            user=request.user,
            initial={
                "start_date": today,
                "end_date": today + timedelta(days=20),
                "daily_target": 60,
                "visibility": "public",
            },
        )
    return render(request, "community/plan_form.html", {"form": form, "mode": "create"})


@login_required
def plan_edit(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    if not (request.user.is_staff or plan.owner_id == request.user.pk):
        raise PermissionDenied("只有计划发起人可以编辑这个计划。")
    if request.method == "POST":
        form = PlanForm(request.POST, request.FILES, instance=plan, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "计划已更新。")
            return redirect("community:plan_detail", pk=plan.pk)
        messages.error(request, "修改没有保存成功，请检查表单提示。")
    else:
        form = PlanForm(instance=plan, user=request.user)
    return render(
        request,
        "community/plan_form.html",
        {"form": form, "mode": "edit", "plan": plan},
    )


@login_required
@require_POST
def plan_delete(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    if not (request.user.is_staff or plan.owner_id == request.user.pk):
        raise PermissionDenied("只有计划发起人可以删除这个计划。")
    title = plan.title
    plan.delete()
    messages.success(request, f"计划「{title}」及其打卡记录已删除。")
    return redirect("community:my_plans")


@login_required
def my_plans(request):
    status = request.GET.get("status", "").strip()
    queryset = (
        Plan.objects.filter(owner=request.user)
        .prefetch_related("tags")
        .annotate(checkin_count=Count("checkins", distinct=True))
        .order_by("-updated_at")
    )
    if status in dict(Plan.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    page_obj = _page(request, queryset, 10)
    week_start = timezone.localdate() - timedelta(days=6)
    stats = {
        "total": Plan.objects.filter(owner=request.user).count(),
        "active": Plan.objects.filter(owner=request.user, status="active").count(),
        "week_checkins": CheckIn.objects.filter(
            user=request.user, date__gte=week_start
        ).count(),
        "week_minutes": CheckIn.objects.filter(
            user=request.user, date__gte=week_start
        ).aggregate(total=Sum("minutes"))["total"]
        or 0,
    }
    return render(
        request,
        "community/my_plans.html",
        {
            "page_obj": page_obj,
            "status": status,
            "statuses": Plan.STATUS_CHOICES,
            "stats": stats,
            "base_query": _base_query(request),
        },
    )


@login_required
def checkin_create(request, pk):
    plan = get_object_or_404(Plan.objects.select_related("owner"), pk=pk)
    if plan.owner_id != request.user.pk:
        raise PermissionDenied("只有计划发起人可以打卡。")
    if plan.status != "active":
        messages.error(request, "这个计划已经结束或已放弃，不能再新增打卡。")
        return redirect("community:plan_detail", pk=plan.pk)
    today = timezone.localdate()
    if not (plan.start_date <= today <= plan.end_date):
        messages.error(request, "今天不在计划起止日期内，无法打卡。")
        return redirect("community:plan_detail", pk=plan.pk)
    existing = plan.checkins.filter(date=today).first()
    if existing:
        messages.info(request, "今天已经打卡了，可以直接编辑今天的记录。")
        return redirect("community:checkin_edit", pk=existing.pk)
    if request.method == "POST":
        form = CheckInForm(
            request.POST, request.FILES, plan=plan, user=request.user
        )
        if form.is_valid():
            form.save()
            messages.success(request, "今日打卡完成，连续记录又往前了一步。")
            return redirect("community:plan_detail", pk=plan.pk)
        messages.error(request, "打卡没有保存成功，请检查表单提示。")
    else:
        form = CheckInForm(plan=plan, user=request.user)
    return render(
        request,
        "community/checkin_form.html",
        {"form": form, "plan": plan, "mode": "create"},
    )


@login_required
def checkin_edit(request, pk):
    checkin = get_object_or_404(
        CheckIn.objects.select_related("plan", "user"), pk=pk
    )
    if not (request.user.is_staff or checkin.user_id == request.user.pk):
        raise PermissionDenied("只有打卡人可以编辑这条记录。")
    if request.method == "POST":
        form = CheckInForm(
            request.POST,
            request.FILES,
            instance=checkin,
            plan=checkin.plan,
            user=checkin.user,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "今天的打卡记录已更新。")
            return redirect("community:plan_detail", pk=checkin.plan_id)
        messages.error(request, "修改没有保存成功，请检查表单提示。")
    else:
        form = CheckInForm(
            instance=checkin, plan=checkin.plan, user=checkin.user
        )
    return render(
        request,
        "community/checkin_form.html",
        {"form": form, "plan": checkin.plan, "checkin": checkin, "mode": "edit"},
    )


@login_required
@require_POST
def checkin_delete(request, pk):
    checkin = get_object_or_404(CheckIn, pk=pk)
    if not (request.user.is_staff or checkin.user_id == request.user.pk):
        raise PermissionDenied("只有打卡人可以删除这条记录。")
    plan_id = checkin.plan_id
    checkin.delete()
    messages.success(request, "打卡记录已删除。")
    return redirect("community:plan_detail", pk=plan_id)


@login_required
def friends(request):
    friend_ids = Friendship.friend_ids(request.user)
    friend_cards = []
    for friend in User.objects.filter(id__in=friend_ids, is_active=True):
        friend_cards.append(
            {
                "user": friend,
                "plans": Plan.objects.filter(owner=friend)
                .filter(Q(visibility="public") | Q(visibility="friends"))
                .prefetch_related("tags")[:3],
                "latest": CheckIn.objects.filter(user=friend)
                .filter(plan__visibility__in=["public", "friends"])
                .select_related("plan")
                .first(),
            }
        )
    pending_received = (
        Friendship.objects.filter(addressee=request.user, status="pending")
        .select_related("requester")
        .order_by("-created_at")
    )
    pending_sent = (
        Friendship.objects.filter(requester=request.user, status="pending")
        .select_related("addressee")
        .order_by("-created_at")
    )
    return render(
        request,
        "community/friends.html",
        {
            "friend_cards": friend_cards,
            "pending_received": pending_received,
            "pending_sent": pending_sent,
            "form": FriendRequestForm(user=request.user),
        },
    )


@login_required
@require_POST
def friend_request(request):
    form = FriendRequestForm(request.POST, user=request.user)
    if form.is_valid():
        friendship = Friendship(
            requester=request.user, addressee=form.cleaned_data["target_user"]
        )
        try:
            friendship.full_clean()
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
        else:
            friendship.save()
            messages.success(request, "好友请求已发送，等对方确认后即可互相督学。")
    else:
        for error in form.errors.values():
            messages.error(request, error.as_text().lstrip("* "))
    return redirect("community:friends")


@login_required
@require_POST
def friend_respond(request, pk):
    friendship = get_object_or_404(
        Friendship.objects.select_related("requester", "addressee"), pk=pk
    )
    if friendship.addressee_id != request.user.pk or friendship.status != "pending":
        raise PermissionDenied("这条好友请求不属于你。")
    action = request.POST.get("action")
    if action == "accept":
        friendship.status = "accepted"
        friendship.save(update_fields=["status", "updated_at"])
        messages.success(request, f"你和 {friendship.requester.username} 已成为互督好友。")
    elif action == "reject":
        friendship.status = "rejected"
        friendship.save(update_fields=["status", "updated_at"])
        messages.info(request, "已拒绝这条好友请求。")
    else:
        messages.error(request, "未知操作。")
    return redirect("community:friends")


@login_required
@require_POST
def friend_remove(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    friendship = Friendship.objects.filter(status="accepted").filter(
        Q(requester=request.user, addressee=target)
        | Q(requester=target, addressee=request.user)
    ).first()
    if not friendship:
        messages.error(request, "你们还不是互督好友。")
    else:
        friendship.delete()
        messages.info(request, f"已解除与 {target.username} 的互督关系。")
    return redirect("community:friends")


def profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    is_self = request.user.is_authenticated and request.user.pk == profile_user.pk
    if is_self:
        visible_plans = Plan.objects.filter(owner=profile_user)
    else:
        visible_plans = Plan.objects.filter(owner=profile_user, visibility="public")
    public_plans = (
        visible_plans.prefetch_related("tags").order_by("-created_at")[:6]
    )
    stats = {
        "plans": Plan.objects.filter(owner=profile_user).count(),
        "checkins": CheckIn.objects.filter(user=profile_user).count(),
        "minutes": CheckIn.objects.filter(user=profile_user).aggregate(
            total=Sum("minutes")
        )["total"]
        or 0,
        "cheers": Cheer.objects.filter(checkin__user=profile_user).count(),
    }
    is_friend = (
        request.user.is_authenticated
        and Friendship.are_friends(request.user, profile_user)
    )
    pending = None
    if request.user.is_authenticated and not is_self:
        pending = Friendship.pending_between(request.user, profile_user)
    return render(
        request,
        "community/profile.html",
        {
            "profile_user": profile_user,
            "public_plans": public_plans,
            "stats": stats,
            "is_self": is_self,
            "is_friend": is_friend,
            "pending": pending,
        },
    )


@staff_required
def dashboard(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "delete_plan":
            plan = get_object_or_404(Plan, pk=request.POST.get("id"))
            plan.delete()
            messages.success(request, "计划已由管理员删除。")
        elif action == "delete_checkin":
            checkin = get_object_or_404(CheckIn, pk=request.POST.get("id"))
            checkin.delete()
            messages.success(request, "打卡记录已由管理员删除。")
        elif action == "toggle_user":
            user = get_object_or_404(User, pk=request.POST.get("id"))
            if user.pk == request.user.pk:
                messages.error(request, "不能停用自己的账号。")
            elif user.is_superuser:
                messages.error(request, "不能停用超级管理员。")
            else:
                user.is_active = not user.is_active
                user.save(update_fields=["is_active"])
                messages.success(
                    request,
                    f"账号 {user.username} 已{'启用' if user.is_active else '停用'}。",
                )
        elif action == "add_tag":
            form = TagForm(request.POST)
            if form.is_valid():
                Tag.objects.create(name=form.cleaned_data["name"])
                messages.success(request, "标签已添加。")
            else:
                for error in form.errors.values():
                    messages.error(request, error.as_text().lstrip("* "))
        elif action == "delete_tag":
            tag = get_object_or_404(Tag, pk=request.POST.get("id"))
            tag.delete()
            messages.success(request, "标签已删除，原有计划的其他标签不受影响。")
        return redirect("community:dashboard")

    stats = {
        "plans": Plan.objects.count(),
        "active_plans": Plan.objects.filter(status="active").count(),
        "checkins": CheckIn.objects.count(),
        "users": User.objects.count(),
    }
    return render(
        request,
        "community/dashboard.html",
        {
            "stats": stats,
            "recent_plans": Plan.objects.select_related("owner")
            .prefetch_related("tags")
            .order_by("-created_at")[:10],
            "recent_checkins": CheckIn.objects.select_related("plan", "user")
            .order_by("-created_at")[:10],
            "users": User.objects.annotate(
                plan_count=Count("study_plans", distinct=True),
                checkin_count=Count("checkins", distinct=True),
            ).order_by("-is_staff", "username"),
            "tags": Tag.objects.annotate(
                plan_count=Count("plans", distinct=True)
            ).order_by("name"),
            "tag_form": TagForm(),
        },
    )


def api_docs(request):
    return render(request, "community/api_docs.html")


def error_403(request, exception=None):
    return render(request, "403.html", status=403)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)
