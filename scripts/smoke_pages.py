# -*- coding: utf-8 -*-
"""Quick page smoke test. Run from the project root:

    python scripts/smoke_pages.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studyplan.settings")

import django

django.setup()

from django.test import Client  # noqa: E402
from community.models import Plan  # noqa: E402


def show(client, path, expected, label):
    response = client.get(path, follow=False)
    ok = response.status_code == expected
    print(f"{'OK ' if ok else 'FAIL'} {response.status_code:>3} (want {expected}) {label:<22} {path}")
    return ok


def main():
    all_ok = True
    client = Client()
    public_paths = [
        ("/", 200, "home anonymous"),
        ("/accounts/login/", 200, "login page"),
        ("/accounts/register/", 200, "register page"),
        ("/plans/", 200, "plan square"),
        ("/api-docs/", 200, "api docs"),
        ("/u/admin/", 200, "profile"),
        ("/api/v1/plans/", 200, "api plans"),
        ("/api/v1/tags/", 200, "api tags"),
        ("/api/v1/stats/", 200, "api stats"),
        ("/api/v1/docs/", 200, "api index"),
        ("/api/v1/csrf/", 200, "api csrf"),
    ]
    for path, expected, label in public_paths:
        all_ok &= show(client, path, expected, label)

    plan = Plan.objects.filter(visibility="public", owner__username="admin").first()
    if plan:
        all_ok &= show(client, f"/plans/{plan.pk}/", 200, "plan detail")
    private = Plan.objects.filter(visibility="private").first()
    if private:
        all_ok &= show(client, f"/plans/{private.pk}/", 403, "private plan denied")

    assert client.login(username="admin", password="admin123")
    auth_paths = [
        ("/my/plans/", 200, "my plans"),
        ("/friends/", 200, "friends"),
        ("/manage/", 200, "staff dashboard"),
        ("/plans/new/", 200, "plan form"),
        ("/api/v1/me/", 200, "api me"),
        ("/api/v1/friends/", 200, "api friends"),
    ]
    for path, expected, label in auth_paths:
        all_ok &= show(client, path, expected, label)
    if plan:
        all_ok &= show(client, f"/plans/{plan.pk}/checkin/", 302, "checkin already done")
        all_ok &= show(client, f"/api/v1/plans/{plan.pk}/", 200, "api plan detail")
        all_ok &= show(client, f"/api/v1/plans/{plan.pk}/checkins/", 200, "api checkins")

    client.logout()
    client.login(username="chenxi", password="demo12345")
    if private:
        all_ok &= show(client, f"/plans/{private.pk}/", 403, "private denied to friend")
    all_ok &= show(client, "/plans/new/", 200, "member plan form")

    print("\nRESULT:", "ALL OK" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
