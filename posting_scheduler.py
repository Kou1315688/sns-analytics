"""投稿スケジュール管理 - データCRUD・自動生成・クエリ"""
import json
import uuid
import re
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Dict, Optional

from config import DATA_DIR

SCHEDULE_FILE = DATA_DIR / "posting_schedule.json"

# 曜日マッピング
DAY_MAP = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}
DAY_MAP_REVERSE = {v: k for k, v in DAY_MAP.items()}


def _default_schedule_data() -> dict:
    """デフォルトのスケジュールデータ"""
    return {
        "settings": {
            "line_notify_token": "",
            "gmail_address": "",
            "gmail_app_password": "",
            "reminder_to_email": "",
            "default_reminder_minutes": 30,
            "notifications_enabled": {
                "dashboard": True,
                "line": False,
                "gmail": False,
            },
        },
        "scheduled_posts": [],
        "history": [],
    }


def load_schedule() -> dict:
    """スケジュールデータを読み込み"""
    if not SCHEDULE_FILE.exists():
        return _default_schedule_data()
    with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_schedule(data: dict):
    """スケジュールデータを保存"""
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _generate_id() -> str:
    """ユニークIDを生成"""
    return f"sp_{uuid.uuid4().hex[:8]}"


def _parse_posting_time(time_str: str) -> Optional[dict]:
    """推奨投稿時間をパース (例: '金曜日 12:00' → {'day': '金', 'hour': 12, 'minute': 0})"""
    if not time_str:
        return None

    # パターン: "金曜日 12:00" or "金 12:00"
    match = re.match(r"([月火水木金土日])(?:曜日?)?\s*(\d{1,2}):(\d{2})", time_str)
    if match:
        return {
            "day": match.group(1),
            "hour": int(match.group(2)),
            "minute": int(match.group(3)),
        }
    return None


def _next_weekday(start_date: date, target_weekday: int) -> date:
    """start_date以降の次の指定曜日の日付を計算"""
    days_ahead = target_weekday - start_date.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return start_date + timedelta(days=days_ahead)


def generate_weekly_schedule(
    content_plans: List[Dict],
    week_start: Optional[date] = None,
    max_posts: int = 5,
) -> List[Dict]:
    """投稿案から週間スケジュールを自動生成

    content_plansの各プランの「推奨投稿時間」をパースし、
    week_start以降の実日付に変換してスケジュール化する。
    """
    if week_start is None:
        today = date.today()
        # 今日が含まれる週の月曜日
        week_start = today - timedelta(days=today.weekday())

    scheduled = []
    selected_plans = content_plans[:max_posts]

    for plan in selected_plans:
        time_str = plan.get("推奨投稿時間") or plan.get("posting_time", "")
        parsed = _parse_posting_time(time_str)

        if not parsed:
            # パースできない場合はデフォルト
            parsed = {"day": "金", "hour": 20, "minute": 0}

        target_weekday = DAY_MAP.get(parsed["day"], 4)  # デフォルト金曜
        scheduled_date = _next_weekday(week_start, target_weekday)

        # 過去の日付なら翌週に
        if scheduled_date < date.today():
            scheduled_date += timedelta(days=7)

        # content_plan情報を抽出
        content_info = {}
        for key in ["テーマ", "フック（冒頭文）", "推奨ハッシュタグ", "キャプション案", "ポイント"]:
            if key in plan:
                content_info[key] = plan[key]
        # AI構成案の場合
        if "hook" in plan:
            content_info["テーマ"] = plan.get("title", "")
            content_info["フック（冒頭文）"] = plan.get("hook", "")

        post = {
            "id": _generate_id(),
            "title": plan.get("テーマ") or plan.get("title", "無題"),
            "category": plan.get("カテゴリ") or plan.get("category", ""),
            "format": plan.get("フォーマット") or plan.get("format", ""),
            "scheduled_day": parsed["day"],
            "scheduled_hour": parsed["hour"],
            "scheduled_minute": parsed["minute"],
            "scheduled_date": scheduled_date.isoformat(),
            "status": "scheduled",
            "source": "auto",
            "content_plan": content_info,
            "notes": "",
            "reminder_minutes": 30,
            "reminders_sent": {"line": None, "gmail": None},
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        }
        scheduled.append(post)

    return scheduled


def add_scheduled_post(
    title: str,
    category: str,
    format_type: str,
    scheduled_date: str,
    scheduled_hour: int,
    scheduled_minute: int = 0,
    notes: str = "",
    reminder_minutes: int = 30,
) -> dict:
    """手動でスケジュール投稿を追加"""
    d = date.fromisoformat(scheduled_date)
    day_jp = DAY_MAP_REVERSE.get(d.weekday(), "月")

    post = {
        "id": _generate_id(),
        "title": title,
        "category": category,
        "format": format_type,
        "scheduled_day": day_jp,
        "scheduled_hour": scheduled_hour,
        "scheduled_minute": scheduled_minute,
        "scheduled_date": scheduled_date,
        "status": "scheduled",
        "source": "manual",
        "content_plan": {},
        "notes": notes,
        "reminder_minutes": reminder_minutes,
        "reminders_sent": {"line": None, "gmail": None},
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    data = load_schedule()
    data["scheduled_posts"].append(post)
    save_schedule(data)
    return post


def update_scheduled_post(post_id: str, updates: dict) -> Optional[dict]:
    """スケジュール投稿を更新"""
    data = load_schedule()
    for post in data["scheduled_posts"]:
        if post["id"] == post_id:
            post.update(updates)
            save_schedule(data)
            return post
    return None


def delete_scheduled_post(post_id: str) -> bool:
    """スケジュール投稿を削除"""
    data = load_schedule()
    original_len = len(data["scheduled_posts"])
    data["scheduled_posts"] = [
        p for p in data["scheduled_posts"] if p["id"] != post_id
    ]
    if len(data["scheduled_posts"]) < original_len:
        save_schedule(data)
        return True
    return False


def mark_posted(post_id: str) -> Optional[dict]:
    """投稿完了としてマーク"""
    data = load_schedule()
    for post in data["scheduled_posts"]:
        if post["id"] == post_id:
            post["status"] = "posted"
            post["completed_at"] = datetime.now().isoformat()
            # 履歴に移動
            data["history"].append(post)
            data["scheduled_posts"] = [
                p for p in data["scheduled_posts"] if p["id"] != post_id
            ]
            save_schedule(data)
            return post
    return None


def mark_skipped(post_id: str) -> Optional[dict]:
    """投稿をスキップとしてマーク"""
    data = load_schedule()
    for post in data["scheduled_posts"]:
        if post["id"] == post_id:
            post["status"] = "skipped"
            post["completed_at"] = datetime.now().isoformat()
            data["history"].append(post)
            data["scheduled_posts"] = [
                p for p in data["scheduled_posts"] if p["id"] != post_id
            ]
            save_schedule(data)
            return post
    return None


def get_todays_posts() -> List[dict]:
    """今日の投稿予定を取得"""
    today_str = date.today().isoformat()
    data = load_schedule()
    return [
        p for p in data["scheduled_posts"]
        if p.get("scheduled_date") == today_str
        and p.get("status") in ("scheduled", "reminded")
    ]


def get_upcoming_posts(days: int = 7) -> List[dict]:
    """今後N日間の投稿予定を取得"""
    today = date.today()
    end_date = today + timedelta(days=days)
    data = load_schedule()
    upcoming = []
    for p in data["scheduled_posts"]:
        if p.get("status") not in ("scheduled", "reminded"):
            continue
        try:
            post_date = date.fromisoformat(p["scheduled_date"])
            if today <= post_date <= end_date:
                upcoming.append(p)
        except (ValueError, KeyError):
            continue
    return sorted(upcoming, key=lambda x: (x["scheduled_date"], x["scheduled_hour"], x["scheduled_minute"]))


def get_posts_needing_reminder() -> List[dict]:
    """リマインド送信が必要な投稿を取得

    現在時刻が「投稿時間 - リマインド分数」を超えていて、
    まだ通知を送っていない投稿を返す。
    """
    now = datetime.now()
    data = load_schedule()
    settings = data.get("settings", {})
    notifications = settings.get("notifications_enabled", {})

    needing = []
    for post in data["scheduled_posts"]:
        if post.get("status") not in ("scheduled", "reminded"):
            continue

        try:
            post_date = date.fromisoformat(post["scheduled_date"])
        except (ValueError, KeyError):
            continue

        post_datetime = datetime.combine(
            post_date,
            datetime.min.time().replace(
                hour=post.get("scheduled_hour", 0),
                minute=post.get("scheduled_minute", 0),
            ),
        )

        reminder_minutes = post.get("reminder_minutes", settings.get("default_reminder_minutes", 30))
        reminder_time = post_datetime - timedelta(minutes=reminder_minutes)

        if now < reminder_time:
            continue

        # まだ投稿時間を過ぎていないか、過ぎていても1時間以内
        if now > post_datetime + timedelta(hours=1):
            continue

        # どのチャネルで通知が必要か
        reminders_sent = post.get("reminders_sent", {})
        needs_send = False

        if notifications.get("line") and not reminders_sent.get("line"):
            needs_send = True
        if notifications.get("gmail") and not reminders_sent.get("gmail"):
            needs_send = True

        if needs_send:
            needing.append(post)

    return needing


def save_auto_generated_schedule(posts: List[dict]):
    """自動生成されたスケジュールを一括保存"""
    data = load_schedule()
    data["scheduled_posts"].extend(posts)
    save_schedule(data)


def update_settings(new_settings: dict):
    """設定を更新"""
    data = load_schedule()
    data["settings"].update(new_settings)
    save_schedule(data)


def get_settings() -> dict:
    """現在の設定を取得"""
    data = load_schedule()
    return data.get("settings", _default_schedule_data()["settings"])


def get_history(limit: int = 50) -> List[dict]:
    """投稿履歴を取得"""
    data = load_schedule()
    history = data.get("history", [])
    return sorted(history, key=lambda x: x.get("completed_at", ""), reverse=True)[:limit]


if __name__ == "__main__":
    # テスト: content_plans_latest.json からスケジュール自動生成
    plans_path = DATA_DIR / "content_plans_latest.json"
    if plans_path.exists():
        with open(plans_path, "r", encoding="utf-8") as f:
            plans = json.load(f)

        print("=" * 50)
        print("週間スケジュール自動生成テスト")
        print("=" * 50)

        schedule = generate_weekly_schedule(plans, max_posts=5)
        for s in schedule:
            print(f"\n[{s['id']}] {s['title']}")
            print(f"  カテゴリ: {s['category']}")
            print(f"  日時: {s['scheduled_date']} ({s['scheduled_day']}) {s['scheduled_hour']:02d}:{s['scheduled_minute']:02d}")
            print(f"  フォーマット: {s['format']}")
            print(f"  ソース: {s['source']}")

        # 保存テスト
        save_auto_generated_schedule(schedule)
        print(f"\n保存完了: {SCHEDULE_FILE}")
        print(f"  スケジュール済み投稿数: {len(load_schedule()['scheduled_posts'])}")
    else:
        print("content_plans_latest.json が見つかりません。先に投稿案を生成してください。")
