"""API設定・トークン管理"""
import os
import json
import time
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv
import requests

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Instagram Graph API
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
INSTAGRAM_USER_ID = os.getenv("INSTAGRAM_USER_ID", "")
INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID", "")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "")

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

# Google Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# LINE Notify
LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", "")

# Gmail (リマインド通知用)
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# トークン情報ファイル
TOKEN_FILE = BASE_DIR / ".token_info.json"

# コンテンツカテゴリ定義
CATEGORIES = {
    "暮らし": ["暮らし", "一人暮らし", "部屋", "インテリア", "ルーティン", "生活", "料理", "自炊", "掃除", "収納"],
    "旅行": ["旅行", "旅", "観光", "ホテル", "温泉", "カフェ巡り", "グルメ", "食べ歩き", "絶景", "旅先"],
    "筋トレ": ["筋トレ", "ワークアウト", "ジム", "トレーニング", "プロテイン", "バルクアップ", "筋肉", "ダイエット"],
    "美容": ["美容", "スキンケア", "メンズ美容", "コスメ", "ヘアケア", "脱毛", "肌", "メイク"],
    "自分磨き": ["自分磨き", "モーニングルーティン", "習慣", "読書", "勉強", "朝活", "成長", "目標"],
    "大学生活": ["大学生", "大学", "キャンパス", "サークル", "就活", "バイト", "学生"],
}

# リサーチ用ハッシュタグ
RESEARCH_HASHTAGS = [
    "暮らし", "一人暮らし", "丁寧な暮らし", "シンプルライフ",
    "旅行", "国内旅行", "旅行好きな人と繋がりたい",
    "大学生", "大学生の日常", "大学生活",
    "筋トレ", "筋トレ男子", "ワークアウト",
    "美容", "メンズ美容", "スキンケア",
    "自分磨き", "自分磨き男子", "モーニングルーティン",
    "vlog", "日常vlog",
]


def _load_token_info() -> dict:
    """トークン情報をファイルから読み込み"""
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}


def _save_token_info(info: dict):
    """トークン情報をファイルに保存"""
    TOKEN_FILE.write_text(json.dumps(info, indent=2))


def get_access_token() -> str:
    """有効なアクセストークンを取得（必要に応じてリフレッシュ）"""
    token_info = _load_token_info()

    # トークン情報がある場合、有効期限をチェック
    if token_info.get("expires_at"):
        remaining = token_info["expires_at"] - time.time()
        # 残り7日未満ならリフレッシュ
        if remaining < 7 * 24 * 3600:
            print(f"トークンの残り有効期間: {remaining / 3600:.1f}時間 → リフレッシュします")
            new_token = refresh_token(token_info.get("access_token", INSTAGRAM_ACCESS_TOKEN))
            if new_token:
                return new_token

    return token_info.get("access_token", INSTAGRAM_ACCESS_TOKEN)


def refresh_token(current_token: str) -> Optional[str]:
    """長期トークンをリフレッシュ（60日延長）"""
    url = f"{GRAPH_API_BASE}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": INSTAGRAM_APP_ID,
        "client_secret": INSTAGRAM_APP_SECRET,
        "fb_exchange_token": current_token,
    }
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        new_token = data["access_token"]
        expires_in = data.get("expires_in", 5184000)  # デフォルト60日
        token_info = {
            "access_token": new_token,
            "expires_at": time.time() + expires_in,
            "refreshed_at": time.time(),
        }
        _save_token_info(token_info)
        print("トークンをリフレッシュしました")
        return new_token
    else:
        print(f"トークンリフレッシュ失敗: {resp.status_code} {resp.text}")
        return None


def save_initial_token(token: str):
    """初回トークン設定時に呼び出す"""
    # まずトークン情報を取得
    url = f"{GRAPH_API_BASE}/debug_token"
    params = {"input_token": token, "access_token": token}
    resp = requests.get(url, params=params, timeout=30)

    expires_at = time.time() + 5184000  # デフォルト60日
    if resp.status_code == 200:
        data = resp.json().get("data", {})
        if data.get("expires_at"):
            expires_at = data["expires_at"]

    token_info = {
        "access_token": token,
        "expires_at": expires_at,
        "refreshed_at": time.time(),
    }
    _save_token_info(token_info)
    print(f"トークンを保存しました（有効期限: {(expires_at - time.time()) / 3600 / 24:.1f}日）")


def classify_content(text: str) -> List[str]:
    """テキスト（キャプション）からコンテンツカテゴリを自動分類"""
    if not text:
        return ["その他"]
    text_lower = text.lower()
    matched = []
    for category, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append(category)
                break
    return matched if matched else ["その他"]
