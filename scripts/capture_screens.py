# -*- coding: utf-8 -*-
"""Capture the course-project screenshots.

Run with the local server on 127.0.0.1:8021:

    python scripts/capture_screens.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studyplan.settings")

import django

django.setup()

from community.models import Plan  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://127.0.0.1:8021"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)


def shot(page, path, name, full=True):
    page.goto(BASE + path, wait_until="networkidle")
    page.screenshot(path=os.path.join(OUT, name), full_page=full)
    print("captured", name)


def main():
    public_plan = Plan.objects.filter(owner__username="admin", visibility="public").first()
    checkin_plan = public_plan
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
        page = context.new_page()

        shot(page, "/", "home.png")
        shot(page, "/plans/", "plan-list.png")
        shot(page, f"/plans/{public_plan.pk}/", "plan-detail-public.png")
        shot(page, "/accounts/login/", "login.png")
        shot(page, "/accounts/register/", "register.png")
        shot(page, "/api-docs/", "api-docs.png")
        shot(page, "/u/admin/", "profile.png")

        page.goto(BASE + "/accounts/login/", wait_until="networkidle")
        page.fill("#id_username", "admin")
        page.fill("#id_password", "admin123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        shot(page, f"/plans/{public_plan.pk}/", "plan-detail.png")
        shot(page, "/my/plans/", "my-plans.png")
        shot(page, "/friends/", "friends.png")
        shot(page, "/manage/", "dashboard.png")
        shot(page, "/plans/new/", "plan-form.png")
        page.goto(BASE + f"/plans/{checkin_plan.pk}/checkin/", wait_until="networkidle")
        page.screenshot(path=os.path.join(OUT, "checkin-form.png"), full_page=True)
        print("captured checkin-form.png")

        browser.close()


if __name__ == "__main__":
    main()
