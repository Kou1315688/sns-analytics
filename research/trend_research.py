"""競合・トレンドリサーチ

Instagram Graph APIのハッシュタグ検索を利用してトレンド調査を行う。
"""
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
    RESEARCH_HASHTAGS,
    get_access_token,
    classify_content,
)


def _api_get(endpoint: str, params: Optional[Dict] = None) -> dict:
    token = get_access_token()
    url = f"{GRAPH_API_BASE}/{endpoint}"
    default_params = {"access_token": token}
    if params:
        default_params.update(params)
    resp = requests.get(url, params=default_params, timeout=30)
    if resp.status_code != 200:
        print(f"  API Error [{resp.status_code}]: {resp.text[:200]}")
        return {}
    return resp.json()


def search_hashtag_id(hashtag_name: str) -> Optional[str]:
    """ハッシュタグ名からIDを取得"""
    data = _api_get("ig_hashtag_search", {
        "q": hashtag_name,
        "user_id": INSTAGRAM_USER_ID,
    })
    results = data.get("data", [])
    if results:
        return results[0]["id"]
    return None


def fetch_hashtag_top_media(hashtag_id: str, user_id: str = "") -> List[Dict]:
    """ハッシュタグのトップ投稿を取得"""
    user_id = user_id or INSTAGRAM_USER_ID
    data = _api_get(f"{hashtag_id}/top_media", {
        "user_id": user_id,
        "fields": "id,caption,media_type,like_count,comments_count,timestamp,permalink",
    })
    return data.get("data", [])


def fetch_hashtag_recent_media(hashtag_id: str, user_id: str = "") -> List[Dict]:
    """ハッシュタグの最新投稿を取得"""
    user_id = user_id or INSTAGRAM_USER_ID
    data = _api_get(f"{hashtag_id}/recent_media", {
        "user_id": user_id,
        "fields": "id,caption,media_type,like_count,comments_count,timestamp,permalink",
    })
    return data.get("data", [])


def research_hashtags(hashtags: Optional[List[str]] = None, max_tags: int = 30) -> pd.DataFrame:
    """複数ハッシュタグのトレンドリサーチ

    注意: Instagram Graph APIのハッシュタグ検索は週30個まで
    """
    hashtags = (hashtags or RESEARCH_HASHTAGS)[:max_tags]

    print("=" * 50)
    print("ハッシュタグリサーチ")
    print("=" * 50)
    print(f"調査対象: {len(hashtags)}個のハッシュタグ")
    print(f"注意: 週30ハッシュタグまでの制限があります\n")

    all_results = []

    for i, tag in enumerate(hashtags):
        print(f"[{i+1}/{len(hashtags)}] #{tag} を調査中...")

        # ハッシュタグID取得
        tag_id = search_hashtag_id(tag)
        if not tag_id:
            print(f"  → ハッシュタグが見つかりません")
            continue

        # トップ投稿取得
        top_media = fetch_hashtag_top_media(tag_id)
        recent_media = fetch_hashtag_recent_media(tag_id)

        for media in top_media:
            media["hashtag"] = tag
            media["ranking_type"] = "top"
            all_results.append(media)

        for media in recent_media:
            media["hashtag"] = tag
            media["ranking_type"] = "recent"
            all_results.append(media)

        print(f"  → トップ: {len(top_media)}件, 最新: {len(recent_media)}件")
        time.sleep(1)  # レートリミット対策

    if not all_results:
        print("\nデータを取得できませんでした。")
        return pd.DataFrame()

    df = pd.DataFrame(all_results)

    # エンゲージメント計算
    df["engagement"] = df.get("like_count", 0) + df.get("comments_count", 0)

    # カテゴリ分類
    df["categories"] = df["caption"].fillna("").apply(classify_content)
    df["primary_category"] = df["categories"].apply(lambda x: x[0])

    # 保存
    output_path = DATA_DIR / "hashtag_research_latest.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n{len(df)}件のリサーチデータを保存: {output_path}")

    return df


def analyze_research_results(df: Optional[pd.DataFrame] = None) -> dict:
    """リサーチ結果の分析"""
    if df is None:
        csv_path = DATA_DIR / "hashtag_research_latest.csv"
        if not csv_path.exists():
            print("リサーチデータが見つかりません。先に research_hashtags() を実行してください。")
            return {}
        df = pd.read_csv(csv_path)

    print("\n── リサーチ結果分析 ──")

    # ハッシュタグ別の平均エンゲージメント
    print("\n【ハッシュタグ別 平均エンゲージメント（トップ投稿）】")
    top_df = df[df["ranking_type"] == "top"]
    if not top_df.empty:
        tag_stats = top_df.groupby("hashtag")["engagement"].agg(["mean", "median", "max", "count"])
        tag_stats = tag_stats.sort_values("mean", ascending=False)
        print(tag_stats.to_string())

    # トップ投稿の共通パターン
    print("\n【高エンゲージメント投稿の特徴】")
    if not top_df.empty and "engagement" in top_df.columns:
        high_eng = top_df.nlargest(20, "engagement")
        print(f"  投稿タイプ分布:")
        if "media_type" in high_eng.columns:
            type_dist = high_eng["media_type"].value_counts()
            for mt, count in type_dist.items():
                print(f"    {mt}: {count}件 ({count/len(high_eng)*100:.0f}%)")

        print(f"  カテゴリ分布:")
        cat_dist = high_eng["primary_category"].value_counts()
        for cat, count in cat_dist.items():
            print(f"    {cat}: {count}件 ({count/len(high_eng)*100:.0f}%)")

        # キャプション長
        high_eng_caption_len = high_eng["caption"].fillna("").str.len()
        print(f"  キャプション文字数: 平均={high_eng_caption_len.mean():.0f}, "
              f"中央値={high_eng_caption_len.median():.0f}")

    results = {
        "total_posts_analyzed": len(df),
        "hashtags_researched": df["hashtag"].nunique() if "hashtag" in df.columns else 0,
        "top_hashtags_by_engagement": (
            tag_stats.head(10).to_dict() if not top_df.empty else {}
        ),
    }

    # JSON保存
    results_path = DATA_DIR / "research_results_latest.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    return results


def run_full_research() -> dict:
    """フルリサーチ実行"""
    df = research_hashtags()
    if df.empty:
        return {}
    return analyze_research_results(df)


if __name__ == "__main__":
    run_full_research()
