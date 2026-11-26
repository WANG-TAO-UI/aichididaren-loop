# -*- coding: utf-8 -*-
"""Seed a believable demo community for the course presentation."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from community.models import CheckIn, Cheer, Friendship, Plan, Tag


class Command(BaseCommand):
    help = "创建演示账号、计划、打卡、好友关系与鼓励"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="清空社区业务数据后重新生成（不会删除用户）",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            Cheer.objects.all().delete()
            Friendship.objects.all().delete()
            CheckIn.objects.all().delete()
            Plan.objects.all().delete()
            Tag.objects.all().delete()
            self.stdout.write(self.style.WARNING("已清空计划、打卡、好友、鼓励与标签。"))

        if Plan.objects.exists() and not options["reset"]:
            self.stdout.write(self.style.WARNING("已有计划数据，跳过种子生成。需要重置请加 --reset。"))
            return

        today = timezone.localdate()

        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True},
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password("admin123")
        admin.save()

        demo_users = {}
        profiles = [
            ("chenxi", "陈曦", "demo12345"),
            ("linwan", "林晚", "demo12345"),
            ("zhouyu", "周屿", "demo12345"),
            ("suyi", "苏一", "demo12345"),
            ("heyan", "何言", "demo12345"),
        ]
        for username, first_name, password in profiles:
            user, _ = User.objects.get_or_create(
                username=username, defaults={"first_name": first_name}
            )
            user.first_name = first_name
            user.set_password(password)
            user.save()
            demo_users[username] = user

        tags = {}
        for name in ["考研", "高数", "雅思", "口语", "阅读", "历史", "算法", "秋招", "早起", "自律", "Python", "自动化", "复盘"]:
            tags[name], _ = Tag.objects.get_or_create(name=name)

        def make_plan(owner, title, summary, description, category, tag_names,
                      start_offset, duration, daily_target, visibility="public",
                      status="active"):
            plan = Plan.objects.create(
                owner=owner,
                title=title,
                summary=summary,
                description=description,
                category=category,
                start_date=today + timedelta(days=start_offset),
                end_date=today + timedelta(days=start_offset + duration - 1),
                daily_target=daily_target,
                visibility=visibility,
                status=status,
            )
            plan.tags.set([tags[name] for name in tag_names])
            return plan

        plans = {}
        plans["math"] = make_plan(
            admin,
            "21 天高数冲刺",
            "每天 90 分钟，把极限、导数与级数的错题重新过一遍。",
            "材料：课程讲义 + 近五年真题。\n"
            "方法：每天先做 20 道基础题，再整理 1 页错题；周日只复盘，不刷新题。\n"
            "打卡规则：写清楚今天完成了哪一节、错了哪几类题，不用写漂亮话。",
            "exam",
            ["考研", "高数"],
            -8,
            21,
            90,
        )
        plans["ielts"] = make_plan(
            demo_users["chenxi"],
            "雅思口语 30 天开口计划",
            "每天 45 分钟，先敢说，再考虑说得好不好。",
            "每天一个 Part 2 话题，录音 2 分钟，回听并记下 3 个卡顿点。\n"
            "每周找一天把当周话题连起来说一遍，模拟真实考试节奏。",
            "language",
            ["雅思", "口语"],
            -12,
            30,
            45,
        )
        plans["reading"] = make_plan(
            demo_users["linwan"],
            "《人类简史》精读",
            "两周读完，每天 40 分钟，输出一段自己的判断。",
            "不做摘抄搬运，只回答三个问题：作者说了什么、证据是什么、我同不同意。\n"
            "读完后用 300 字写一张主题卡片。",
            "reading",
            ["阅读", "历史"],
            -6,
            14,
            40,
        )
        plans["leetcode"] = make_plan(
            demo_users["zhouyu"],
            "LeetCode 每日一题",
            "秋招前刷完高频 100 题，重点记录思路而不是题数。",
            "按专题推进：数组 → 哈希 → 双指针 → 二叉树 → 动态规划。\n"
            "每题必须写三行：暴力思路、优化点、复杂度。",
            "skill",
            ["算法", "秋招"],
            -20,
            30,
            60,
        )
        plans["early"] = make_plan(
            demo_users["suyi"],
            "早起 21 天",
            "把起床时间从 8:30 慢慢挪到 7:00，不靠意志力硬扛。",
            "每晚 23:30 前放下手机；起床后先喝水、拉开窗帘，不立刻看消息。",
            "habit",
            ["早起", "自律"],
            -5,
            21,
            30,
            visibility="friends",
        )
        plans["python"] = make_plan(
            demo_users["heyan"],
            "Python 自动化脚本",
            "用 14 天写出三个能真正节省时间的小脚本。",
            "目标脚本：批量重命名文件、Excel 合并、每日课表提醒。\n"
            "每个脚本都要有 README 和一次真实运行记录。",
            "skill",
            ["Python", "自动化"],
            -3,
            14,
            60,
            visibility="friends",
        )
        plans["private"] = make_plan(
            admin,
            "教资面试复盘（仅自己）",
            "把结构化问答的卡壳点逐个拆掉。",
            "每天录一道结构化题，回听开头 30 秒，只改一个最明显的问题。",
            "other",
            ["复盘"],
            -4,
            10,
            30,
            visibility="private",
        )

        contents = {
            "math": [
                "完成极限基础题 24 道，错了 5 道，主要集中在等价无穷小替换。",
                "把昨天 5 道错题重做一遍，3 道独立做对。整理了 1 页替换条件。",
                "导数定义相关 18 道，正确率 83%。还是容易漏定义域。",
                "今天状态一般，只做了 12 道基础题，但把错因写清楚了。",
                "级数收敛判别 20 道，比值法和根值法混了两次，已记在错题本。",
                "把近三年真题里的极限题挑出来做，限时 40 分钟，完成度比上周好。",
                "周日复盘：本周共 96 道题，错题 21 道，重做正确 17 道。",
                "今天只整理了错题，没有刷新题。把“先看条件再选方法”写成了检查清单。",
                "完成 30 道综合小题，第一次在 90 分钟内做完。明天开始线代部分。",
            ],
            "ielts": [
                "Part 2 话题 Describe a useful skill，录音 2 分 10 秒，卡顿 4 次。",
                "重录昨天的话题，卡顿降到 2 次。把连接词写在便签上，效果明显。",
                "今天练 Part 1，回答太短。逼自己每个问题补一个原因。",
                "整理 10 个常用替换表达，并用它们重说了一遍。",
                "和同学对练 30 分钟，被指出时态总飘。晚上专门练了 20 句过去时。",
                "Part 3 话题练习，观点有了但例子不够具体。记下三个万能例子。",
                "录音回听：语速偏快。今天刻意放慢，停顿反而更自然。",
                "只做了 20 分钟，但把当周 7 个话题连起来说了一遍，完整度提高。",
                "模拟全套口语，Part 2 超时 15 秒。下次先写 4 个关键词。",
                "把高频话题按人物/地点/物品分类，发现很多素材可以复用。",
                "今天开口有点抵触，还是录了 1 分钟。先保持不断。",
                "当周复盘：录音 11 条，最明显的问题是例子不够具体。",
                "完成一次完整模拟，比上周少卡 3 次。下周重点练 Part 3。",
            ],
            "reading": [
                "读到第二章“认知革命”，作者的核心论点是虚构故事带来大规模协作。",
                "第三章读完。对“农业革命是骗局”这个判断保留意见，写了 200 字反驳。",
                "今天读得慢，只读了 12 页，但把“想象的共同体”这个概念弄清楚了。",
                "第四章，重点记了帝国、货币、宗教三条线索。",
                "读第五章并画了一张时间轴，发现作者用大量类比代替论证。",
                "读完第二部分。写了一张 300 字卡片：进步叙事是否忽略了普通人的体验。",
                "今天只读了 8 页，把之前的概念重新串了一遍。慢一点也算推进。",
            ],
            "leetcode": [
                "两数之和，哈希一次过。补写了暴力解和复杂度。",
                "三数之和，去重逻辑卡了很久，看了题解才理顺。",
                "有效括号，栈。边界：空字符串和只剩右括号。",
                "二叉树层序遍历，模板题，但写的时候忘了导入 deque。",
                "最长无重复子串，滑动窗口。今天第一次独立写出来。",
                "合并两个有序链表，递归和迭代都写了一遍。",
                "只复习了错题，没有开新题。把三数之和重新默写。",
                "动态规划入门：爬楼梯。状态转移想清楚了，但初始化写错一次。",
                "最大子数组和，贪心思路。写完发现和 DP 的转移其实一致。",
                "周复盘：本周 9 题，独立完成 6 题，2 题需要题解。",
                "回文链表，快慢指针 + 反转。空间 O(1) 的写法第一次写完整。",
            ],
            "early": [
                "7:40 起床，比目标晚 10 分钟，但比上周稳定。",
                "7:25 起床。昨晚 23:10 放下手机，入睡快了很多。",
                "7:20 起床，拉开窗帘后没有回床。",
                "今天醒了但赖了 15 分钟，仍然在 7:35 起来。",
                "7:10 起床，第一次达到目标。早餐后直接开始阅读。",
                "7:05 起床。连续 6 天没有超过 7:40。",
            ],
            "python": [
                "搭好虚拟环境，写了批量重命名脚本，处理了 42 个文件。",
                "Excel 合并脚本完成，能读取多张表并统一表头。",
                "只修了昨天的 bug：空单元格导致表头错位。",
                "课表提醒脚本跑通，用 schedule 库每早 7:30 推送。",
            ],
            "private": [
                "录了“如何处理学生冲突”这道题，开头 30 秒太绕。",
                "重录，先把结论放前面，结构清楚多了。",
                "练“如何看待成绩与成长”，例子还是空泛。",
                "把答题框架缩成三步：判断—依据—做法。",
                "今天只录了一遍，明显比上周稳。",
            ],
        }

        offsets = {
            "math": list(range(9)),
            "ielts": [0, 1, 3, 4, 5, 7, 8, 9, 11, 12],
            "reading": [0, 1, 2, 4, 5, 6],
            "leetcode": [0, 2, 4, 7, 9, 12, 14, 16, 18, 19, 20],
            "early": [0, 1, 2, 3, 4, 5],
            "python": [0, 1, 3],
            "private": [0, 2, 4],
        }
        moods = ["great", "good", "good", "ok", "tired"]
        minutes_map = {"math": 95, "ielts": 50, "reading": 42, "leetcode": 65, "early": 35, "python": 70, "private": 32}

        checkins = {}
        for key, plan in plans.items():
            entries = contents[key]
            checkins[key] = []
            for index, offset in enumerate(offsets[key]):
                if index >= len(entries):
                    break
                checkin_date = plan.start_date + timedelta(days=offset)
                if checkin_date > today:
                    continue
                item = CheckIn.objects.create(
                    plan=plan,
                    user=plan.owner,
                    date=checkin_date,
                    minutes=max(5, minutes_map[key] + (index % 3 - 1) * 10),
                    content=entries[index],
                    mood=moods[index % len(moods)],
                )
                checkins[key].append(item)

        admin = demo_users.get("admin", admin)
        chenxi = demo_users["chenxi"]
        linwan = demo_users["linwan"]
        zhouyu = demo_users["zhouyu"]
        suyi = demo_users["suyi"]
        heyan = demo_users["heyan"]

        Friendship.objects.get_or_create(requester=admin, addressee=chenxi, defaults={"status": "accepted"})
        Friendship.objects.get_or_create(requester=admin, addressee=linwan, defaults={"status": "accepted"})
        Friendship.objects.get_or_create(requester=admin, addressee=zhouyu, defaults={"status": "accepted"})
        Friendship.objects.get_or_create(requester=suyi, addressee=admin, defaults={"status": "pending"})
        Friendship.objects.get_or_create(requester=admin, addressee=heyan, defaults={"status": "pending"})

        cheer_pairs = [
            (admin, checkins["ielts"][-1], "Part 3 的例子可以再具体一点，试试讲你真实上过的一节课。"),
            (chenxi, checkins["math"][-1], "90 分钟做完 30 道综合题很稳了，线代部分先抓概念。"),
            (admin, checkins["reading"][-1], "“慢一点也算推进”这句很好，精读本来就不是比页数。"),
            (linwan, checkins["math"][-1], "你的错题清单很清楚，建议周末只看错因，不重抄题目。"),
            (zhouyu, checkins["math"][-4], "比值法和根值法确实容易混，可以各写一个判别流程图。"),
            (admin, checkins["leetcode"][-1], "独立写出来最重要，明天可以试试限时 25 分钟。"),
        ]
        for from_user, checkin, content in cheer_pairs:
            Cheer.objects.get_or_create(
                checkin=checkin, from_user=from_user, defaults={"content": content}
            )

        self.stdout.write(self.style.SUCCESS("演示数据生成完成。"))
        self.stdout.write("管理员：admin / admin123")
        self.stdout.write("普通用户：chenxi、linwan、zhouyu、suyi、heyan / demo12345")
        self.stdout.write(f"计划 {Plan.objects.count()} 个，打卡 {CheckIn.objects.count()} 条，鼓励 {Cheer.objects.count()} 条。")
