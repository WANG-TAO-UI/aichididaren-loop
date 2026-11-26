# -*- coding: utf-8 -*-
"""Domain models for the StudyLoop study-plan check-in community."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone


def validate_image_size(file_obj):
    """Reject uploaded images larger than 5 MB (defence in depth)."""
    limit = 5 * 1024 * 1024
    if file_obj and getattr(file_obj, "size", 0) > limit:
        raise ValidationError("图片不能超过 5MB，请压缩后重新上传。")


class Tag(models.Model):
    """A free-form label shared by many plans (many-to-many)."""

    name = models.CharField("标签名", max_length=30, unique=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "标签"
        verbose_name_plural = "标签"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Plan(models.Model):
    """A study plan created by one user."""

    CATEGORY_CHOICES = [
        ("exam", "考试备考"),
        ("skill", "技能学习"),
        ("reading", "阅读写作"),
        ("language", "语言学习"),
        ("habit", "习惯养成"),
        ("other", "其他"),
    ]
    VISIBILITY_CHOICES = [
        ("public", "公开"),
        ("friends", "仅好友"),
        ("private", "仅自己"),
    ]
    STATUS_CHOICES = [
        ("active", "进行中"),
        ("completed", "已完成"),
        ("abandoned", "已放弃"),
    ]

    owner = models.ForeignKey(
        User,
        verbose_name="发起人",
        on_delete=models.CASCADE,
        related_name="study_plans",
    )
    title = models.CharField("计划标题", max_length=80)
    summary = models.CharField("一句话简介", max_length=160, blank=True)
    description = models.TextField("计划说明", blank=True)
    category = models.CharField(
        "计划类型", max_length=20, choices=CATEGORY_CHOICES, default="exam"
    )
    tags = models.ManyToManyField(
        Tag, verbose_name="标签", related_name="plans", blank=True
    )
    cover = models.ImageField(
        "封面图",
        upload_to="covers/%Y/%m/",
        blank=True,
        validators=[validate_image_size],
        help_text="支持 JPG/PNG/WebP，5MB 以内；不上传则使用渐变色封面。",
    )
    start_date = models.DateField("开始日期", default=timezone.localdate)
    end_date = models.DateField("结束日期")
    daily_target = models.PositiveIntegerField(
        "每日目标（分钟）",
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(720)],
    )
    visibility = models.CharField(
        "可见范围", max_length=10, choices=VISIBILITY_CHOICES, default="public"
    )
    status = models.CharField(
        "计划状态", max_length=12, choices=STATUS_CHOICES, default="active"
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "学习计划"
        verbose_name_plural = "学习计划"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["visibility", "status", "-created_at"]),
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.owner.username} · {self.title}"

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "结束日期不能早于开始日期。"
        if self.daily_target is not None and not 1 <= self.daily_target <= 720:
            errors["daily_target"] = "每日目标需在 1 到 720 分钟之间。"
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=20)
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("community:plan_detail", args=[self.pk])

    @property
    def duration_days(self):
        if not self.start_date or not self.end_date:
            return 0
        return max((self.end_date - self.start_date).days + 1, 1)

    @property
    def checked_days(self):
        values = self.checkins.values_list("date", flat=True).distinct()
        return len(list(values))

    @property
    def total_minutes(self):
        return self.checkins.aggregate(total=Sum("minutes"))["total"] or 0

    @property
    def progress_percent(self):
        if not self.duration_days:
            return 0
        return min(100, round(self.checked_days * 100 / self.duration_days))

    @property
    def current_streak(self):
        """Consecutive days ending today (or yesterday if today is not yet done)."""
        dates = set(self.checkins.values_list("date", flat=True))
        if not dates:
            return 0
        today = timezone.localdate()
        cursor = today if today in dates else today - timedelta(days=1)
        streak = 0
        while cursor in dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    @property
    def today_checkin(self):
        return self.checkins.filter(date=timezone.localdate()).first()

    @property
    def cheer_total(self):
        return sum(item.cheers.count() for item in self.checkins.all())

    @property
    def category_label(self):
        return self.get_category_display()

    @property
    def cover_tone(self):
        return f"tone-{self.pk % 5 if self.pk else 0}"

    @property
    def initial(self):
        if not self.title:
            return "计"
        for char in self.title:
            if char.isalpha():
                return char
        return self.title[0]

    def visible_to(self, user):
        """Return True when *user* may view this plan."""
        if self.visibility == "public":
            return True
        if not user or not user.is_authenticated:
            return False
        if user == self.owner or user.is_staff:
            return True
        if self.visibility == "friends":
            return Friendship.are_friends(user, self.owner)
        return False


class CheckIn(models.Model):
    """One daily report attached to a plan; one per plan per day."""

    MOOD_CHOICES = [
        ("great", "元气满满"),
        ("good", "状态不错"),
        ("ok", "平稳推进"),
        ("tired", "有点疲惫"),
    ]

    plan = models.ForeignKey(
        Plan,
        verbose_name="所属计划",
        on_delete=models.CASCADE,
        related_name="checkins",
    )
    user = models.ForeignKey(
        User,
        verbose_name="打卡人",
        on_delete=models.CASCADE,
        related_name="checkins",
    )
    date = models.DateField("打卡日期", default=timezone.localdate)
    minutes = models.PositiveIntegerField(
        "投入分钟",
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(720)],
    )
    content = models.TextField("今日汇报", max_length=2000)
    mood = models.CharField(
        "今日状态", max_length=10, choices=MOOD_CHOICES, default="good"
    )
    image = models.ImageField(
        "学习留影",
        upload_to="checkins/%Y/%m/",
        blank=True,
        validators=[validate_image_size],
    )
    created_at = models.DateTimeField("提交时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "每日打卡"
        verbose_name_plural = "每日打卡"
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "date"], name="unique_checkin_per_plan_day"
            )
        ]
        indexes = [models.Index(fields=["user", "-date"])]

    def __str__(self):
        return f"{self.user.username} · {self.plan.title} · {self.date}"

    def clean(self):
        errors = {}
        today = timezone.localdate()
        if self.date and self.date > today:
            errors["date"] = "不能给未来的日期打卡。"
        if self.plan_id:
            plan = self.plan
            if self.date and self.date < plan.start_date:
                errors["date"] = "打卡日期不能早于计划开始日期。"
            if self.date and self.date > plan.end_date:
                errors["date"] = "打卡日期不能晚于计划结束日期。"
            if self.user_id and plan.owner_id != self.user_id:
                errors["user"] = "只有计划发起人可以给该计划打卡。"
        if self.minutes is not None and not 1 <= self.minutes <= 720:
            errors["minutes"] = "投入分钟需在 1 到 720 之间。"
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def mood_label(self):
        return self.get_mood_display()


class Friendship(models.Model):
    """A directional friend request that becomes a mutual friendship."""

    STATUS_CHOICES = [
        ("pending", "待确认"),
        ("accepted", "已互督"),
        ("rejected", "已拒绝"),
    ]

    requester = models.ForeignKey(
        User,
        verbose_name="发起人",
        on_delete=models.CASCADE,
        related_name="sent_friend_requests",
    )
    addressee = models.ForeignKey(
        User,
        verbose_name="接收人",
        on_delete=models.CASCADE,
        related_name="received_friend_requests",
    )
    status = models.CharField(
        "状态", max_length=10, choices=STATUS_CHOICES, default="pending"
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "好友关系"
        verbose_name_plural = "好友关系"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["requester", "addressee"],
                name="unique_friend_request_direction",
            )
        ]

    def __str__(self):
        return f"{self.requester.username} → {self.addressee.username} ({self.status})"

    def clean(self):
        if self.requester_id and self.addressee_id:
            if self.requester_id == self.addressee_id:
                raise ValidationError("不能添加自己为好友。")

    @classmethod
    def are_friends(cls, user_a, user_b):
        if not user_a or not user_b or not user_a.is_authenticated:
            return False
        if user_a.pk == user_b.pk:
            return False
        return cls.objects.filter(status="accepted").filter(
            Q(requester=user_a, addressee=user_b)
            | Q(requester=user_b, addressee=user_a)
        ).exists()

    @classmethod
    def friend_ids(cls, user):
        if not user or not user.is_authenticated:
            return []
        rows = cls.objects.filter(status="accepted").filter(
            Q(requester=user) | Q(addressee=user)
        )
        ids = []
        for row in rows:
            ids.append(
                row.addressee_id if row.requester_id == user.pk else row.requester_id
            )
        return ids

    @classmethod
    def pending_between(cls, user_a, user_b):
        if not user_a or not user_b or user_a.pk == user_b.pk:
            return None
        return cls.objects.filter(status="pending").filter(
            Q(requester=user_a, addressee=user_b)
            | Q(requester=user_b, addressee=user_a)
        ).first()


class Cheer(models.Model):
    """A short encouragement left by a friend under a daily check-in."""

    checkin = models.ForeignKey(
        CheckIn,
        verbose_name="打卡记录",
        on_delete=models.CASCADE,
        related_name="cheers",
    )
    from_user = models.ForeignKey(
        User,
        verbose_name="留言人",
        on_delete=models.CASCADE,
        related_name="cheers_sent",
    )
    content = models.CharField("鼓励内容", max_length=120, default="继续加油！")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "互督鼓励"
        verbose_name_plural = "互督鼓励"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["checkin", "from_user"], name="unique_cheer_per_user_checkin"
            )
        ]

    def __str__(self):
        return f"{self.from_user.username} → {self.checkin.user.username}: {self.content}"
