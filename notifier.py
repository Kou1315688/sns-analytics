"""通知送信 - LINE Notify + Gmail SMTP"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import requests


def format_reminder_message(post: dict) -> str:
    """リマインド通知メッセージを整形"""
    title = post.get("title", "無題")
    hour = post.get("scheduled_hour", 0)
    minute = post.get("scheduled_minute", 0)
    time_str = f"{hour:02d}:{minute:02d}"
    fmt = post.get("format", "")
    category = post.get("category", "")
    date_str = post.get("scheduled_date", "")

    content_plan = post.get("content_plan", {})
    hook = content_plan.get("フック（冒頭文）", "")

    lines = [
        "",
        "📱 投稿リマインダー",
        "━━━━━━━━━━━━━━",
        f"テーマ: {title}",
        f"投稿日: {date_str}",
        f"投稿時間: {time_str}",
    ]

    if category:
        lines.append(f"カテゴリ: {category}")
    if fmt:
        lines.append(f"フォーマット: {fmt}")

    lines.append("━━━━━━━━━━━━━━")

    if hook:
        lines.append(f"フック: {hook}")

    notes = post.get("notes", "")
    if notes:
        lines.append(f"メモ: {notes}")

    return "\n".join(lines)


def send_line_notify(token: str, message: str) -> bool:
    """LINE Notifyでメッセージを送信"""
    if not token:
        print("[LINE] トークンが設定されていません")
        return False

    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"message": message}

    try:
        resp = requests.post(url, headers=headers, data=data, timeout=30)
        if resp.status_code == 200:
            print("[LINE] 送信成功")
            return True
        else:
            print(f"[LINE] 送信失敗: {resp.status_code} {resp.text}")
            return False
    except requests.RequestException as e:
        print(f"[LINE] 送信エラー: {e}")
        return False


def send_gmail(
    sender_address: str,
    app_password: str,
    to_address: str,
    subject: str,
    body: str,
) -> bool:
    """Gmail SMTPでメールを送信"""
    if not sender_address or not app_password:
        print("[Gmail] アドレスまたはアプリパスワードが設定されていません")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender_address
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_address, app_password)
            server.send_message(msg)
        print(f"[Gmail] 送信成功: {to_address}")
        return True
    except smtplib.SMTPException as e:
        print(f"[Gmail] 送信エラー: {e}")
        return False


def send_reminder(post: dict, settings: dict) -> dict:
    """投稿のリマインド通知を各チャネルに送信

    Returns:
        送信結果 {"line": bool|None, "gmail": bool|None}
    """
    message = format_reminder_message(post)
    notifications = settings.get("notifications_enabled", {})
    results = {"line": None, "gmail": None}

    reminders_sent = post.get("reminders_sent", {})

    # LINE Notify
    if notifications.get("line") and not reminders_sent.get("line"):
        token = settings.get("line_notify_token", "")
        if token:
            results["line"] = send_line_notify(token, message)

    # Gmail
    if notifications.get("gmail") and not reminders_sent.get("gmail"):
        gmail_addr = settings.get("gmail_address", "")
        gmail_pass = settings.get("gmail_app_password", "")
        to_email = settings.get("reminder_to_email", "") or gmail_addr
        if gmail_addr and gmail_pass and to_email:
            subject = f"📱 投稿リマインド: {post.get('title', '無題')}"
            results["gmail"] = send_gmail(gmail_addr, gmail_pass, to_email, subject, message)

    return results


if __name__ == "__main__":
    # テスト用ダミー投稿
    test_post = {
        "title": "朝活ルーティン リール投稿",
        "category": "自分磨き",
        "format": "リール",
        "scheduled_date": "2026-03-07",
        "scheduled_hour": 20,
        "scheduled_minute": 0,
        "content_plan": {
            "フック（冒頭文）": "5時起きを1ヶ月続けた結果",
        },
        "notes": "",
    }

    print("=== リマインドメッセージ プレビュー ===")
    print(format_reminder_message(test_post))

    print("\n=== LINE Notify テスト送信 ===")
    print("LINE_NOTIFY_TOKEN を設定してから実行してください")
    # send_line_notify("YOUR_TOKEN", format_reminder_message(test_post))

    print("\n=== Gmail テスト送信 ===")
    print("Gmail アドレスとアプリパスワードを設定してから実行してください")
    # send_gmail("your@gmail.com", "app_password", "your@gmail.com",
    #            "テスト通知", format_reminder_message(test_post))
