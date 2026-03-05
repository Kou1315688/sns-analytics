"""TikTok エクスポートデータ解析

TikTokアプリからエクスポートしたJSONデータを解析する。
エクスポート手順: 設定 → アカウント → データをダウンロード → JSON形式
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR, classify_content

TIKTOK_DATA_DIR = DATA_DIR / "tiktok_export"


def find_export_file() -> Optional[Path]:
    """エクスポートファイルを検索"""
    # data/tiktok_export/ 内のJSONを探す
    if TIKTOK_DATA_DIR.exists():
        json_files = list(TIKTOK_DATA_DIR.glob("*.json"))
        if json_files:
            return json_files[0]

    # data/ 直下も探す
    for pattern in ["user_data*.json", "tiktok*.json"]:
        files = list(DATA_DIR.glob(pattern))
        if files:
            return files[0]

    return None


def parse_export(file_path: Optional[Path] = None) -> pd.DataFrame:
    """TikTokエクスポートJSONをパースしてDataFrameに変換"""
    if file_path is None:
        file_path = find_export_file()
    if file_path is None or not file_path.exists():
        print(f"TikTokエクスポートファイルが見つかりません。")
        print(f"以下のいずれかにエクスポートJSONを配置してください:")
        print(f"  - {TIKTOK_DATA_DIR}/")
        print(f"  - {DATA_DIR}/")
        print(f"\nエクスポート手順:")
        print(f"  1. TikTokアプリ → プロフィール → 設定")
        print(f"  2. アカウント → データをダウンロード")
        print(f"  3. JSON形式を選択 → リクエスト")
        print(f"  4. ダウンロードしたファイルをdata/tiktok_export/に配置")
        return pd.DataFrame()

    print(f"TikTokデータ読み込み: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # TikTokエクスポートの構造に対応
    # 一般的な構造: {"Activity": {"Video Browsing History": ...}, "Video": {"Videos": {"VideoList": [...]}}}
    videos = []

    # パターン1: Video.Videos.VideoList
    video_section = raw_data.get("Video", {}).get("Videos", {})
    if isinstance(video_section, dict):
        video_list = video_section.get("VideoList", [])
    elif isinstance(video_section, list):
        video_list = video_section
    else:
        video_list = []

    # パターン2: Activity.Like List 等にも投稿データがある場合
    if not video_list:
        # フラットな構造を試行
        for key in ["videos", "Posts", "posts"]:
            if key in raw_data:
                video_list = raw_data[key] if isinstance(raw_data[key], list) else []
                break

    if not video_list:
        print("動画データが見つかりません。エクスポートファイルの構造を確認してください。")
        print(f"トップレベルキー: {list(raw_data.keys())}")
        return pd.DataFrame()

    for video in video_list:
        # 日時パース（複数のフォーマットに対応）
        date_str = video.get("Date", video.get("date", video.get("CreateTime", "")))
        timestamp = None
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                timestamp = datetime.strptime(str(date_str), fmt)
                break
            except (ValueError, TypeError):
                continue
        if timestamp is None and isinstance(date_str, (int, float)):
            timestamp = datetime.fromtimestamp(date_str)

        caption = video.get("Desc", video.get("desc", video.get("Description", "")))
        likes = video.get("Likes", video.get("likes", video.get("DiggCount", 0)))
        comments = video.get("Comments", video.get("comments", video.get("CommentCount", 0)))
        shares = video.get("Shares", video.get("shares", video.get("ShareCount", 0)))
        views = video.get("Views", video.get("views", video.get("PlayCount", 0)))

        # 数値変換
        for val_name in ["likes", "comments", "shares", "views"]:
            val = locals()[val_name]
            if isinstance(val, str):
                try:
                    locals()[val_name] = int(val)
                except ValueError:
                    locals()[val_name] = 0

        videos.append({
            "timestamp": timestamp,
            "caption": caption or "",
            "likes": int(likes) if likes else 0,
            "comments": int(comments) if comments else 0,
            "shares": int(shares) if shares else 0,
            "views": int(views) if views else 0,
            "link": video.get("Link", video.get("link", "")),
        })

    if not videos:
        print("パース可能な動画データがありませんでした。")
        return pd.DataFrame()

    df = pd.DataFrame(videos)

    # メタデータ追加
    if "timestamp" in df.columns and df["timestamp"].notna().any():
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
        df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
        df["day_of_week_jp"] = pd.to_datetime(df["timestamp"]).dt.weekday.map(
            {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
        )

    # ハッシュタグ抽出
    import re
    df["hashtags"] = df["caption"].apply(lambda x: re.findall(r"#(\S+)", x) if x else [])
    df["hashtag_count"] = df["hashtags"].apply(len)
    df["caption_length"] = df["caption"].str.len()

    # カテゴリ分類
    df["categories"] = df["caption"].apply(classify_content)
    df["primary_category"] = df["categories"].apply(lambda x: x[0])

    # 保存
    output_path = DATA_DIR / "tiktok_posts_latest.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n{len(df)}件の動画データをパースしました")
    print(f"保存: {output_path}")

    return df


if __name__ == "__main__":
    parse_export()
