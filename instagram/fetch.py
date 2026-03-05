"""Instagram Graph API データ取得"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import requests

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    GRAPH_API_BASE,
    INSTAGRAM_USER_ID,
    DATA_DIR,
    get_access_token,
)


def _api_get(endpoint: str, params: Optional[Dict] = None, retries: int = 3) -> dict:
    """Graph API GETリクエスト（リトライ付き）"""
    token = get_access_token()
    url = f"{GRAPH_API_BASE}/{endpoint}"
    default_params = {"access_token": token}
    if params:
        default_params.update(params)

    for attempt in range(retries):
        try:
            resp = requests.get(url, params=default_params, timeout=60)
            if resp.status_code != 200:
                print(f"API Error [{resp.status_code}]: {resp.text[:200]}")
                return {}
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"  タイムアウト、{wait}秒後にリトライ ({attempt+1}/{retries})")
                time.sleep(wait)
            else:
                print(f"  タイムアウト: {endpoint}")
                return {}
        except requests.exceptions.RequestException as e:
            print(f"  リクエストエラー: {e}")
            return {}


def fetch_media_list(user_id: str = "", limit: int = 100) -> list[dict]:
    """全投稿一覧を取得（ページネーション対応）"""
    user_id = user_id or INSTAGRAM_USER_ID
    all_media = []
    params = {
        "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count",
        "limit": min(limit, 100),
    }
    endpoint = f"{user_id}/media"

    while True:
        data = _api_get(endpoint, params)
        if not data:
            break

        media_list = data.get("data", [])
        all_media.extend(media_list)
        print(f"  取得済み: {len(all_media)}件")

        # ページネーション
        paging = data.get("paging", {})
        next_url = paging.get("next")
        if not next_url or len(all_media) >= limit:
            break

        # next URLからcursorを抽出
        after = paging.get("cursors", {}).get("after")
        if after:
            params["after"] = after
        else:
            break

        time.sleep(0.5)  # レートリミット対策

    return all_media[:limit]


def fetch_media_insights(media_id: str, media_type: str = "IMAGE") -> dict:
    """個別投稿のインサイトを取得"""
    # v22.0以降: plays, impressions は廃止。メディアタイプで分岐
    if media_type in ("VIDEO", "REELS"):
        metrics = "reach,saved,shares,likes,comments,total_interactions"
    else:
        metrics = "reach,saved,shares,likes,comments,total_interactions"

    data = _api_get(f"{media_id}/insights", {"metric": metrics})
    if not data or "data" not in data:
        # フォールバック: 最小限のメトリクスで再試行
        data = _api_get(f"{media_id}/insights", {"metric": "reach,saved,likes,comments"})
        if not data or "data" not in data:
            return {}

    result = {}
    for item in data.get("data", []):
        name = item["name"]
        value = item["values"][0]["value"] if item.get("values") else 0
        result[name] = value
    return result


def fetch_account_insights(user_id: str = "", period: str = "day", days: int = 30) -> dict:
    """アカウント全体のインサイトを取得"""
    user_id = user_id or INSTAGRAM_USER_ID

    # フォロワー属性（年齢・性別・地域）
    demographics = {}
    for breakdown in ["age", "gender", "city", "country"]:
        data = _api_get(f"{user_id}/insights", {
            "metric": "follower_demographics",
            "period": "lifetime",
            "metric_type": "total_value",
            "timeframe": "last_30_days",
            "breakdown": breakdown,
        })
        if data and data.get("data"):
            for item in data["data"]:
                demographics[breakdown] = item.get("total_value", {}).get("breakdowns", [])

    # リーチ推移
    reach_data = _api_get(f"{user_id}/insights", {
        "metric": "reach",
        "period": period,
        "since": int(time.time()) - days * 86400,
        "until": int(time.time()),
    })

    # エンゲージメント
    engaged_data = _api_get(f"{user_id}/insights", {
        "metric": "accounts_engaged",
        "period": period,
        "metric_type": "total_value",
        "since": int(time.time()) - days * 86400,
        "until": int(time.time()),
    })

    return {
        "demographics": demographics,
        "reach_data": reach_data.get("data", []),
        "engaged_data": engaged_data.get("data", []),
    }


def fetch_all_and_save() -> pd.DataFrame:
    """全投稿データ＋インサイトを取得してCSV保存"""
    print("=" * 50)
    print("Instagram データ取得開始")
    print("=" * 50)

    # 1. 投稿一覧取得
    print("\n[1/3] 投稿一覧を取得中...")
    media_list = fetch_media_list()
    print(f"  → {len(media_list)}件の投稿を取得")

    if not media_list:
        print("投稿が取得できませんでした。アクセストークンとユーザーIDを確認してください。")
        return pd.DataFrame()

    # 2. 各投稿のインサイト取得
    print("\n[2/3] 各投稿のインサイトを取得中...")
    posts_data = []
    for i, media in enumerate(media_list):
        media_type = media.get("media_type", "IMAGE")
        insights = fetch_media_insights(media["id"], media_type)

        post = {
            "id": media["id"],
            "caption": media.get("caption", ""),
            "media_type": media_type,
            "permalink": media.get("permalink", ""),
            "timestamp": media.get("timestamp", ""),
            "like_count": media.get("like_count", 0),
            "comments_count": media.get("comments_count", 0),
            "reach": insights.get("reach", 0),
            "impressions": insights.get("impressions", 0),
            "saved": insights.get("saved", 0),
            "shares": insights.get("shares", 0),
            "plays": insights.get("plays", 0),
            "total_interactions": insights.get("total_interactions", 0),
        }
        posts_data.append(post)

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(media_list)} 完了")
        time.sleep(0.3)  # レートリミット対策

    print(f"  → 全{len(posts_data)}件のインサイト取得完了")

    # 3. アカウントインサイト取得
    print("\n[3/3] アカウントインサイトを取得中...")
    account_insights = fetch_account_insights()

    # データ保存
    df = pd.DataFrame(posts_data)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # CSV保存
    csv_path = DATA_DIR / f"instagram_posts_{timestamp_str}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n投稿データ保存: {csv_path}")

    # 最新データへのシンボリックリンク的にコピー
    latest_csv = DATA_DIR / "instagram_posts_latest.csv"
    df.to_csv(latest_csv, index=False, encoding="utf-8-sig")

    # アカウントインサイトをJSON保存
    account_path = DATA_DIR / f"instagram_account_{timestamp_str}.json"
    with open(account_path, "w", encoding="utf-8") as f:
        json.dump(account_insights, f, ensure_ascii=False, indent=2)

    latest_account = DATA_DIR / "instagram_account_latest.json"
    with open(latest_account, "w", encoding="utf-8") as f:
        json.dump(account_insights, f, ensure_ascii=False, indent=2)

    print(f"アカウントデータ保存: {account_path}")
    print(f"\n取得完了！ 合計 {len(df)} 件の投稿データ")
    return df


if __name__ == "__main__":
    fetch_all_and_save()
