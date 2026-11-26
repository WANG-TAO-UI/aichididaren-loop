# -*- coding: utf-8 -*-
"""Forms used by the web UI."""

from datetime import timedelta
import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import CheckIn, Friendship, Plan, Tag
from .utils import parse_tag_names


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label="邮箱（选填）",
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "用于找回账号，可不填"}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        widgets = {
            "username": forms.TextInput(attrs={"placeholder": "例如：wangzutao"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "3–20 位字母、数字或下划线，注册后不可修改。"
        self.fields["password1"].help_text = "至少 8 位，不能是纯数字或常见密码。"
        self.fields["password2"].help_text = "再次输入相同的密码。"

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
            raise forms.ValidationError("用户名需为 3–20 位字母、数字或下划线。")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("该用户名已被使用，请换一个。")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "").strip()
        if commit:
            user.save()
        return user


class PlanForm(forms.ModelForm):
    tags_text = forms.CharField(
        label="标签",
        required=False,
        max_length=180,
        help_text="用逗号分隔，最多 5 个，例如：考研, 英语, 早起",
        widget=forms.TextInput(attrs={"placeholder": "考研, 英语, 早起"}),
    )

    class Meta:
        model = Plan
        fields = [
            "title",
            "summary",
            "description",
            "category",
            "start_date",
            "end_date",
            "daily_target",
            "visibility",
            "status",
            "cover",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "例如：21 天高数冲刺"}),
            "summary": forms.TextInput(
                attrs={"placeholder": "一句话说明这个计划要达成什么"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 5, "placeholder": "阶段目标、学习材料、打卡规则……"}
            ),
            "start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "daily_target": forms.NumberInput(attrs={"min": 1, "max": 720}),
            "cover": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["tags_text"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True)
            )
        today = timezone.localdate()
        max_date = (today + timedelta(days=365)).isoformat()
        self.fields["start_date"].widget.attrs.setdefault("max", max_date)
        self.fields["end_date"].widget.attrs.setdefault("max", max_date)

    def clean_tags_text(self):
        raw = self.cleaned_data.get("tags_text", "")
        names = parse_tag_names(raw, limit=5)
        if len(parse_tag_names(raw, limit=99)) > 5:
            raise forms.ValidationError("标签最多只能填 5 个。")
        return names

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "结束日期不能早于开始日期。")
        if start and end and (end - start).days > 365:
            self.add_error("end_date", "单个计划最长支持 365 天。")
        return cleaned

    def save(self, commit=True):
        plan = super().save(commit=commit)
        if commit:
            from .utils import tags_for_names

            plan.tags.set(tags_for_names(self.cleaned_data.get("tags_text", [])))
        return plan


class CheckInForm(forms.ModelForm):
    class Meta:
        model = CheckIn
        fields = ["date", "minutes", "content", "mood", "image"]
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "minutes": forms.NumberInput(attrs={"min": 1, "max": 720}),
            "content": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "今天学了什么？完成了哪些具体任务？遇到了什么卡点？",
                }
            ),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, plan=None, user=None, **kwargs):
        self.plan = plan
        self.user = user
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["date"].widget.attrs["max"] = today.isoformat()
        if plan:
            self.fields["date"].widget.attrs["min"] = plan.start_date.isoformat()
            self.fields["date"].widget.attrs["max"] = min(today, plan.end_date).isoformat()
            if not self.instance.pk:
                self.fields["date"].initial = today

    def clean_date(self):
        date = self.cleaned_data["date"]
        if not self.plan:
            return date
        today = timezone.localdate()
        if date > today:
            raise forms.ValidationError("不能给未来的日期打卡。")
        if date < self.plan.start_date or date > self.plan.end_date:
            raise forms.ValidationError("打卡日期必须落在计划起止日期内。")
        exists = CheckIn.objects.filter(plan=self.plan, date=date)
        if self.instance.pk:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise forms.ValidationError("这个计划当天已经打卡了，直接编辑当天记录即可。")
        return date

    def save(self, commit=True):
        checkin = super().save(commit=False)
        if self.plan:
            checkin.plan = self.plan
        if self.user:
            checkin.user = self.user
        if commit:
            checkin.save()
        return checkin


class FriendRequestForm(forms.Form):
    username = forms.CharField(
        label="对方的用户名",
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "输入用户名，例如 chenxi"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        try:
            target = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            raise forms.ValidationError("没有找到这个用户。")
        if not target.is_active:
            raise forms.ValidationError("该账号已被停用。")
        if target == self.user:
            raise forms.ValidationError("不能添加自己为好友。")
        if Friendship.are_friends(self.user, target):
            raise forms.ValidationError("你们已经是互督好友了。")
        pending = Friendship.pending_between(self.user, target)
        if pending:
            if pending.addressee_id == self.user.pk:
                raise forms.ValidationError("对方已经向你发出请求，请到好友页确认。")
            raise forms.ValidationError("请求已发送，等待对方确认。")
        self.cleaned_data["target_user"] = target
        return username

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)


class CheerForm(forms.Form):
    content = forms.CharField(
        label="鼓励留言",
        max_length=120,
        widget=forms.TextInput(attrs={"placeholder": "例如：连续 3 天了，稳住！"}),
    )

    def clean_content(self):
        content = self.cleaned_data["content"].strip()
        if not content:
            raise forms.ValidationError("写一句鼓励的话吧。")
        return content


class TagForm(forms.Form):
    name = forms.CharField(
        label="标签名",
        max_length=30,
        widget=forms.TextInput(attrs={"placeholder": "例如：考研"}),
    )

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Tag.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("这个标签已经存在。")
        return name
