# -*- coding: utf-8 -*-
"""Automated tests for models, web pages and the REST API."""

import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CheckIn, Cheer, Friendship, Plan


def make_user(username, password="testpass123"):
    return User.objects.create_user(username=username, password=password)


def make_plan(owner, **kwargs):
    today = timezone.localdate()
    payload = {
        "title": "测试计划",
        "summary": "用于自动化测试",
        "description": "",
        "category": "exam",
        "start_date": today - timedelta(days=3),
        "end_date": today + timedelta(days=6),
        "daily_target": 60,
        "visibility": "public",
        "status": "active",
    }
    payload.update(kwargs)
    return Plan.objects.create(owner=owner, **payload)


def make_checkin(plan, user, day=None, minutes=45, content="今天完成了测试。"):
    return CheckIn.objects.create(
        plan=plan,
        user=user,
        date=day or timezone.localdate(),
        minutes=minutes,
        content=content,
        mood="good",
    )


class ModelTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.plan = make_plan(self.alice)

    def test_duration_and_progress(self):
        self.assertEqual(self.plan.duration_days, 10)
        make_checkin(self.plan, self.alice, day=timezone.localdate())
        make_checkin(
            self.plan,
            self.alice,
            day=timezone.localdate() - timedelta(days=1),
            content="昨天。",
        )
        self.assertEqual(self.plan.checked_days, 2)
        self.assertEqual(self.plan.progress_percent, 20)
        self.assertEqual(self.plan.current_streak, 2)

    def test_visibility_rules(self):
        private = make_plan(self.alice, title="私有计划", visibility="private")
        friends_only = make_plan(self.alice, title="好友计划", visibility="friends")
        self.assertTrue(self.plan.visible_to(self.bob))
        self.assertFalse(private.visible_to(self.bob))
        self.assertFalse(friends_only.visible_to(self.bob))
        Friendship.objects.create(requester=self.alice, addressee=self.bob, status="accepted")
        self.assertTrue(friends_only.visible_to(self.bob))
        self.assertFalse(private.visible_to(self.bob))
        self.assertTrue(private.visible_to(self.alice))

    def test_plan_date_validation(self):
        with self.assertRaises(ValidationError):
            make_plan(
                self.alice,
                title="日期错误",
                start_date=timezone.localdate(),
                end_date=timezone.localdate() - timedelta(days=1),
            )

    def test_checkin_unique_per_plan_day(self):
        make_checkin(self.plan, self.alice)
        with self.assertRaises(ValidationError):
            make_checkin(self.plan, self.alice, content="重复。")

    def test_only_owner_can_checkin(self):
        with self.assertRaises(ValidationError):
            make_checkin(self.plan, self.bob, content="不是发起人。")

    def test_cheer_unique(self):
        item = make_checkin(self.plan, self.alice)
        Cheer.objects.create(checkin=item, from_user=self.bob, content="加油")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cheer.objects.create(checkin=item, from_user=self.bob, content="重复")


class WebFlowTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.staff = User.objects.create_user("staff", password="testpass123", is_staff=True)
        self.plan = make_plan(self.alice, title="公开计划")
        self.private = make_plan(self.alice, title="私有计划", visibility="private")
        self.friends_plan = make_plan(self.alice, title="好友计划", visibility="friends")

    def test_home_and_square_are_public(self):
        for path in [reverse("community:home"), reverse("community:plan_list")]:
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_anonymous_cannot_see_private_plan(self):
        response = self.client.get(reverse("community:plan_detail", args=[self.private.pk]))
        self.assertEqual(response.status_code, 403)

    def test_friend_can_see_friends_only_plan(self):
        Friendship.objects.create(requester=self.alice, addressee=self.bob, status="accepted")
        self.client.login(username="bob", password="testpass123")
        response = self.client.get(
            reverse("community:plan_detail", args=[self.friends_plan.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_register_and_login(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password1": "strongpass12345",
                "password2": "strongpass12345",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username="newuser").exists())
        self.client.logout()
        self.assertTrue(self.client.login(username="newuser", password="strongpass12345"))

    def test_register_rejects_bad_username(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "a!",
                "password1": "strongpass12345",
                "password2": "strongpass12345",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="a!").exists())
        self.assertContains(response, "3–20 位")

    def test_create_plan_and_checkin(self):
        self.client.login(username="alice", password="testpass123")
        today = timezone.localdate()
        response = self.client.post(
            reverse("community:plan_create"),
            {
                "title": "新计划",
                "summary": "简介",
                "description": "说明",
                "category": "skill",
                "tags_text": "测试, 学习",
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=6)).isoformat(),
                "daily_target": 45,
                "visibility": "public",
                "status": "active",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        created = Plan.objects.get(title="新计划")
        self.assertEqual(created.owner, self.alice)
        self.assertEqual(created.tags.count(), 2)

        response = self.client.post(
            reverse("community:checkin_create", args=[created.pk]),
            {
                "date": today.isoformat(),
                "minutes": 50,
                "content": "完成第一次打卡。",
                "mood": "great",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CheckIn.objects.filter(plan=created, date=today).exists())

    def test_duplicate_checkin_redirects_to_edit(self):
        today = timezone.localdate()
        item = make_checkin(self.plan, self.alice, day=today)
        self.client.login(username="alice", password="testpass123")
        response = self.client.get(reverse("community:checkin_create", args=[self.plan.pk]))
        self.assertRedirects(
            response, reverse("community:checkin_edit", args=[item.pk]), fetch_redirect_response=False
        )

    def test_staff_dashboard_permissions(self):
        self.client.login(username="bob", password="testpass123")
        self.assertEqual(self.client.get(reverse("community:dashboard")).status_code, 403)
        self.client.logout()
        self.client.login(username="staff", password="testpass123")
        self.assertEqual(self.client.get(reverse("community:dashboard")).status_code, 200)

    def test_friend_request_and_accept(self):
        self.client.login(username="alice", password="testpass123")
        response = self.client.post(
            reverse("community:friend_request"), {"username": "bob"}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        friendship = Friendship.objects.get(requester=self.alice, addressee=self.bob)
        self.assertEqual(friendship.status, "pending")

        self.client.logout()
        self.client.login(username="bob", password="testpass123")
        self.client.post(
            reverse("community:friend_respond", args=[friendship.pk]),
            {"action": "accept"},
            follow=True,
        )
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, "accepted")

    def test_owner_can_delete_plan_but_other_cannot(self):
        self.client.login(username="bob", password="testpass123")
        response = self.client.post(reverse("community:plan_delete", args=[self.plan.pk]))
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        self.client.login(username="alice", password="testpass123")
        response = self.client.post(reverse("community:plan_delete", args=[self.plan.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Plan.objects.filter(pk=self.plan.pk).exists())


class ApiTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.carol = make_user("carol")
        self.plan = make_plan(self.alice)

    def api_login(self, username="alice", password="testpass123"):
        response = self.client.post(
            reverse("api:login"),
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_csrf_and_anonymous_401(self):
        response = self.client.get(reverse("api:csrf"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrf_token", response.json())
        response = self.client.get(reverse("api:me"))
        self.assertEqual(response.status_code, 401)

    def test_login_and_me(self):
        self.api_login()
        response = self.client.get(reverse("api:me"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "alice")

    def test_plan_list_only_visible(self):
        make_plan(self.alice, title="私有", visibility="private")
        response = self.client.get(reverse("api:plans"))
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()["results"]]
        self.assertIn("测试计划", titles)
        self.assertNotIn("私有", titles)

    def test_create_read_update_delete_plan(self):
        self.api_login()
        today = timezone.localdate()
        payload = {
            "title": "API 新计划",
            "summary": "通过 API 创建",
            "category": "reading",
            "tags": ["API", "测试"],
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=4)).isoformat(),
            "daily_target": 30,
            "visibility": "public",
        }
        response = self.client.post(
            reverse("api:plans"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        plan_id = response.json()["id"]
        self.assertEqual(len(response.json()["tags"]), 2)

        response = self.client.get(reverse("api:plan-detail", args=[plan_id]))
        self.assertEqual(response.status_code, 200)

        response = self.client.patch(
            reverse("api:plan-detail", args=[plan_id]),
            data=json.dumps({"title": "改过的标题", "daily_target": 40}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "改过的标题")
        self.assertEqual(response.json()["daily_target"], 40)

        response = self.client.delete(reverse("api:plan-detail", args=[plan_id]))
        self.assertEqual(response.status_code, 204)

    def test_create_plan_validation_error(self):
        self.api_login()
        response = self.client.post(
            reverse("api:plans"),
            data=json.dumps({"title": "", "tags": "bad"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_checkin_create_duplicate_and_permissions(self):
        self.api_login()
        today = timezone.localdate()
        payload = {
            "date": today.isoformat(),
            "minutes": 30,
            "content": "API 打卡。",
            "mood": "good",
        }
        response = self.client.post(
            reverse("api:plan-checkins", args=[self.plan.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)

        response = self.client.post(
            reverse("api:plan-checkins", args=[self.plan.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

        self.client.logout()
        self.api_login("bob")
        response = self.client.post(
            reverse("api:plan-checkins", args=[self.plan.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_friend_cheer_flow(self):
        Friendship.objects.create(
            requester=self.alice, addressee=self.bob, status="accepted"
        )
        item = make_checkin(self.plan, self.alice)
        self.api_login("bob")
        response = self.client.post(
            reverse("api:checkin-cheer", args=[item.pk]),
            data=json.dumps({"content": "继续稳住！"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(item.cheers.count(), 1)

        response = self.client.post(
            reverse("api:checkin-cheer", args=[item.pk]),
            data=json.dumps({"content": "重复"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

        response = self.client.delete(reverse("api:checkin-cheer", args=[item.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(item.cheers.count(), 0)

    def test_self_and_stranger_cannot_cheer(self):
        item = make_checkin(self.plan, self.alice)
        self.api_login("alice")
        response = self.client.post(
            reverse("api:checkin-cheer", args=[item.pk]),
            data=json.dumps({"content": "给自己"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        self.client.logout()
        self.api_login("carol")
        response = self.client.post(
            reverse("api:checkin-cheer", args=[item.pk]),
            data=json.dumps({"content": "陌生人"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_friend_request_api(self):
        self.api_login("alice")
        response = self.client.post(
            reverse("api:friends"),
            data=json.dumps({"username": "bob"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        friendship_id = response.json()["id"]

        self.client.logout()
        self.api_login("bob")
        response = self.client.post(
            reverse("api:friend-accept", args=[friendship_id]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")

    def test_friend_accept_wrong_user(self):
        friendship = Friendship.objects.create(
            requester=self.alice, addressee=self.bob, status="pending"
        )
        self.api_login("carol")
        response = self.client.post(
            reverse("api:friend-accept", args=[friendship.pk]),
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_plan_404_and_unauthorized_update(self):
        self.api_login("bob")
        response = self.client.get(reverse("api:plan-detail", args=[9999]))
        self.assertEqual(response.status_code, 404)
        response = self.client.patch(
            reverse("api:plan-detail", args=[self.plan.pk]),
            data=json.dumps({"title": "越权"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_stats_and_tags(self):
        response = self.client.get(reverse("api:stats"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("plans", response.json())
        response = self.client.get(reverse("api:tags"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())
