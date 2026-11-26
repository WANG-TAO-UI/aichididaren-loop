# -*- coding: utf-8 -*-
"""Capture a small mobile viewport for layout QA."""

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


def main():
    plan = Plan.objects.filter(visibility="public").first()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=1,
            is_mobile=True,
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto(BASE + "/", wait_until="networkidle")
        page.screenshot(path=os.path.join(OUT, "mobile-home.png"), full_page=True)
        print("captured mobile-home.png")
        page.goto(BASE + f"/plans/{plan.pk}/", wait_until="networkidle")
        page.screenshot(path=os.path.join(OUT, "mobile-plan-detail.png"), full_page=True)
        print("captured mobile-plan-detail.png")
        browser.close()


if __name__ == "__main__":
    main()
