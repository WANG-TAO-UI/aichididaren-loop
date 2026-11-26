# -*- coding: utf-8 -*-
"""Registration, login and logout views."""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import RegisterForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect("community:home")
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, f"欢迎回来，{form.get_user().username}。")
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}
            ):
                return redirect(next_url)
            return redirect("community:home")
        messages.error(request, "用户名或密码不正确，请重试。")
    else:
        form = AuthenticationForm(request)
    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": next_url},
    )


def register_view(request):
    if request.user.is_authenticated:
        return redirect("community:home")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "注册成功，先制定一个 7 天小计划吧。")
            return redirect("community:plan_create")
        messages.error(request, "注册信息有误，请按提示修改。")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "已退出登录。")
    return redirect("community:home")
