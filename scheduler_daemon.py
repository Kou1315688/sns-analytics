"""スケジューラーデーモン - 5分毎にリマインドをチェック・送信"""
import json
import time
import signal
import sys
from datetime import datetime
from pathlib import Path

from config import DATA_DIR
from posting_scheduler import (
    load_schedule,
    save_schedule,
    get_posts_needing_reminder,
    get_settings,
)
from notifier import send_reminder

HEARTBEAT_FILE = DATA_DIR / "scheduler_heartbeat.json"
CHECK_INTERVAL = 300  # 5分


def write_heartbeat(status: str = "running", extra: dict = None):
    """ハートビート情報を書き込み"""
    info = {
        "status": status,
        "last_check": datetime.now().isoformat(),
        "pid": __import__("os").getpid(),
    }
    if extra:
        info.update(extra)
    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)


def check_and_send_reminders():
    """リマインドが必要な投稿をチェックし、通知を送信"""
    posts = get_posts_needing_reminder()
    if not posts:
        return 0

    settings = get_settings()
    sent_count = 0

    for post in posts:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] リマインド送信: {post['title']}")
        results = send_reminder(post, settings)

        # 送信結果を記録
        data = load_schedule()
        for p in data["scheduled_posts"]:
            if p["id"] == post["id"]:
                if results.get("line") is not None:
                    p["reminders_sent"]["line"] = datetime.now().isoformat()
                if results.get("gmail") is not None:
                    p["reminders_sent"]["gmail"] = datetime.now().isoformat()
                if results.get("line") or results.get("gmail"):
                    p["status"] = "reminded"
                break
        save_schedule(data)
        sent_count += 1

    return sent_count


def run_daemon():
    """デーモンメインループ"""
    print("=" * 50)
    print("投稿スケジューラー デーモン 起動")
    print(f"チェック間隔: {CHECK_INTERVAL}秒 ({CHECK_INTERVAL // 60}分)")
    print(f"PID: {__import__('os').getpid()}")
    print("=" * 50)

    # シグナルハンドラ
    def handle_signal(signum, frame):
        print(f"\nシグナル {signum} を受信。シャットダウンします...")
        write_heartbeat("stopped")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    write_heartbeat("running")

    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent = check_and_send_reminders()
            write_heartbeat("running", {"last_sent_count": sent})

            if sent > 0:
                print(f"[{now}] {sent}件のリマインドを送信しました")
            else:
                print(f"[{now}] チェック完了 — リマインドなし")

        except Exception as e:
            print(f"[ERROR] {e}")
            write_heartbeat("error", {"error": str(e)})

        time.sleep(CHECK_INTERVAL)


def generate_launchd_plist() -> str:
    """macOS launchd 用 plist を生成"""
    project_dir = Path(__file__).parent.resolve()
    venv_python = project_dir / "venv" / "bin" / "python3"
    python_path = str(venv_python) if venv_python.exists() else sys.executable
    script_path = str(project_dir / "scheduler_daemon.py")

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sns-analytics.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{project_dir}/data/scheduler_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{project_dir}/data/scheduler_stderr.log</string>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
</dict>
</plist>"""
    return plist


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="投稿スケジューラー デーモン")
    parser.add_argument("--install", action="store_true", help="launchd plist を生成・インストール")
    parser.add_argument("--once", action="store_true", help="1回だけチェックして終了")
    args = parser.parse_args()

    if args.install:
        plist_content = generate_launchd_plist()
        plist_path = Path.home() / "Library/LaunchAgents/com.sns-analytics.scheduler.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(plist_path, "w") as f:
            f.write(plist_content)
        print(f"plist を保存しました: {plist_path}")
        print(f"\n起動コマンド:")
        print(f"  launchctl load {plist_path}")
        print(f"\n停止コマンド:")
        print(f"  launchctl unload {plist_path}")

    elif args.once:
        print("単発チェック実行...")
        sent = check_and_send_reminders()
        print(f"送信件数: {sent}")

    else:
        run_daemon()
