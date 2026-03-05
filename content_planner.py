"""投稿案生成 - 分析結果をもとにコンテンツプランを作成"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd

from config import DATA_DIR, CATEGORIES, RESEARCH_HASHTAGS

OUTPUT_DIR = DATA_DIR


def load_analysis_results() -> dict:
    """Instagram分析結果を読み込み"""
    results = {
        "instagram": None,
        "tiktok": None,
        "research": None,
    }

    ig_path = DATA_DIR / "instagram_analyzed.csv"
    if ig_path.exists():
        results["instagram"] = pd.read_csv(ig_path)

    tk_path = DATA_DIR / "tiktok_analyzed.csv"
    if tk_path.exists():
        results["tiktok"] = pd.read_csv(tk_path)

    research_path = DATA_DIR / "research_results_latest.json"
    if research_path.exists():
        with open(research_path, "r", encoding="utf-8") as f:
            results["research"] = json.load(f)

    return results


def _get_best_posting_times(df: pd.DataFrame) -> dict:
    """最適な投稿時間帯を分析"""
    if df.empty or "hour" not in df.columns:
        return {"best_hours": [19, 20, 21], "best_days": ["土", "日"]}

    engagement_col = "engagement_rate" if "engagement_rate" in df.columns else "views"

    by_hour = df.groupby("hour")[engagement_col].mean().sort_values(ascending=False)
    best_hours = by_hour.head(3).index.tolist()

    if "day_of_week_jp" in df.columns:
        by_day = df.groupby("day_of_week_jp")[engagement_col].mean().sort_values(ascending=False)
        best_days = by_day.head(3).index.tolist()
    else:
        best_days = ["土", "日", "金"]

    return {"best_hours": best_hours, "best_days": best_days}


def _get_best_categories(df: pd.DataFrame) -> List[str]:
    """パフォーマンスの高いカテゴリを特定"""
    if df.empty or "primary_category" not in df.columns:
        return list(CATEGORIES.keys())

    engagement_col = "engagement_rate" if "engagement_rate" in df.columns else "likes"
    by_cat = df.groupby("primary_category")[engagement_col].mean().sort_values(ascending=False)
    return by_cat.index.tolist()


def _get_optimal_hashtags(df: pd.DataFrame, category: str) -> List[str]:
    """カテゴリに適したハッシュタグを推奨"""
    base_tags = {
        "暮らし": ["#暮らし", "#一人暮らし", "#丁寧な暮らし", "#シンプルライフ", "#暮らしを楽しむ",
                   "#日々の暮らし", "#ルームツアー", "#部屋作り"],
        "旅行": ["#旅行", "#国内旅行", "#旅行好きな人と繋がりたい", "#旅スタグラム",
                 "#カフェ巡り", "#グルメ旅", "#週末旅行", "#絶景スポット"],
        "筋トレ": ["#筋トレ", "#筋トレ男子", "#ワークアウト", "#トレーニング",
                  "#ジム", "#フィットネス", "#ボディメイク", "#筋トレ好きと繋がりたい"],
        "美容": ["#メンズ美容", "#スキンケア", "#美容", "#メンズスキンケア",
                "#メンズコスメ", "#肌ケア", "#美容男子", "#垢抜け"],
        "自分磨き": ["#自分磨き", "#自分磨き男子", "#モーニングルーティン", "#朝活",
                   "#習慣化", "#読書", "#成長記録", "#QOL向上"],
        "大学生活": ["#大学生", "#大学生の日常", "#大学生活", "#キャンパスライフ",
                   "#大学生の暮らし", "#大学生vlog"],
    }

    tags = base_tags.get(category, ["#日常", "#vlog", "#ライフスタイル"])

    # 共通タグ追加
    common = ["#日常", "#vlog", "#ライフスタイル", "#大学生"]
    tags.extend([t for t in common if t not in tags])

    # 分析データがあればパフォーマンスの高いタグを優先
    if not df.empty and "hashtags" in df.columns:
        import ast
        all_tags = []
        for tags_str in df["hashtags"].dropna():
            if isinstance(tags_str, str) and tags_str.startswith("["):
                try:
                    all_tags.extend(ast.literal_eval(tags_str))
                except (ValueError, SyntaxError):
                    pass

    return tags[:15]


def _get_best_media_type(df: pd.DataFrame) -> str:
    """最もパフォーマンスの高い投稿タイプ"""
    if df.empty or "media_type" not in df.columns:
        return "CAROUSEL_ALBUM"

    engagement_col = "engagement_rate" if "engagement_rate" in df.columns else "likes"
    by_type = df.groupby("media_type")[engagement_col].mean()
    return by_type.idxmax() if not by_type.empty else "CAROUSEL_ALBUM"


# ── 投稿テーマテンプレート ──

CONTENT_THEMES = {
    "暮らし": [
        {"theme": "一人暮らしルームツアー", "format": "リール/カルーセル", "hook": "社会人1年目の部屋が快適すぎる"},
        {"theme": "週末のモーニングルーティン", "format": "リール", "hook": "休日の朝、丁寧に過ごす"},
        {"theme": "自炊レシピ紹介", "format": "カルーセル", "hook": "一人暮らし男子の簡単ごはん"},
        {"theme": "部屋の模様替えBefore/After", "format": "カルーセル", "hook": "3000円で部屋が激変した話"},
        {"theme": "買ってよかったもの紹介", "format": "カルーセル/リール", "hook": "QOL爆上がりアイテム5選"},
        {"theme": "ナイトルーティン", "format": "リール", "hook": "次の日を最高にする夜の過ごし方"},
    ],
    "旅行": [
        {"theme": "週末弾丸旅行vlog", "format": "リール", "hook": "1泊2日で行ける最高の旅先"},
        {"theme": "カフェ巡り", "format": "カルーセル", "hook": "この街で絶対行くべきカフェ"},
        {"theme": "旅先グルメまとめ", "format": "カルーセル", "hook": "地元民おすすめの名店"},
        {"theme": "ホテルレビュー", "format": "カルーセル/リール", "hook": "コスパ最強のホテル見つけた"},
        {"theme": "旅行パッキング", "format": "カルーセル", "hook": "旅行の荷物、全部見せます"},
    ],
    "筋トレ": [
        {"theme": "筋トレルーティン", "format": "リール", "hook": "大学生の筋トレメニュー公開"},
        {"theme": "ビフォーアフター", "format": "カルーセル", "hook": "3ヶ月の変化がエグい"},
        {"theme": "食事管理", "format": "カルーセル", "hook": "筋トレしてる人の1日の食事"},
        {"theme": "おすすめプロテイン", "format": "カルーセル", "hook": "ガチで美味しいプロテインTOP5"},
        {"theme": "自宅トレーニング", "format": "リール", "hook": "器具なしで腹筋バキバキにする方法"},
    ],
    "美容": [
        {"theme": "スキンケアルーティン", "format": "リール/カルーセル", "hook": "肌が変わったスキンケア全公開"},
        {"theme": "メンズ美容入門", "format": "カルーセル", "hook": "何から始めればいい？メンズ美容の基本"},
        {"theme": "おすすめコスメ", "format": "カルーセル", "hook": "ドラッグストアで買えるメンズコスメ"},
        {"theme": "垢抜けた方法", "format": "カルーセル/リール", "hook": "大学入学から垢抜けるまでの全記録"},
        {"theme": "ヘアケアルーティン", "format": "リール", "hook": "美容室帰りの髪をキープする方法"},
    ],
    "自分磨き": [
        {"theme": "朝活ルーティン", "format": "リール", "hook": "5時起きを1ヶ月続けた結果"},
        {"theme": "おすすめ本紹介", "format": "カルーセル", "hook": "人生変わった本5冊"},
        {"theme": "習慣化のコツ", "format": "カルーセル", "hook": "三日坊主だった僕が習慣化できた方法"},
        {"theme": "1日のスケジュール", "format": "カルーセル/リール", "hook": "大学生のリアルな1日"},
        {"theme": "目標設定", "format": "カルーセル", "hook": "今年やりたいこと100リスト"},
    ],
    "大学生活": [
        {"theme": "大学生の1日", "format": "リール", "hook": "授業・バイト・筋トレを両立する1日"},
        {"theme": "大学生の持ち物", "format": "カルーセル", "hook": "カバンの中身全部見せます"},
        {"theme": "節約術", "format": "カルーセル", "hook": "月5万で生活する大学生の節約法"},
    ],
}


def generate_content_plans(num_plans: int = 10) -> List[Dict]:
    """投稿案を生成"""
    print("=" * 50)
    print("投稿案生成")
    print("=" * 50)

    data = load_analysis_results()
    ig_df = data["instagram"] if data["instagram"] is not None else pd.DataFrame()
    tk_df = data["tiktok"] if data["tiktok"] is not None else pd.DataFrame()

    # 分析結果から最適条件を取得
    main_df = ig_df if not ig_df.empty else tk_df
    best_times = _get_best_posting_times(main_df)
    best_categories = _get_best_categories(main_df)
    best_media_type = _get_best_media_type(ig_df)

    print(f"\n最適投稿時間: {best_times['best_hours']}時")
    print(f"最適投稿曜日: {best_times['best_days']}")
    print(f"高パフォーマンスカテゴリ: {best_categories[:3]}")
    print(f"推奨フォーマット: {best_media_type}")

    # 投稿案生成
    plans = []
    used_themes = set()

    # パフォーマンスの高いカテゴリを優先的に配分
    category_weights = {}
    for i, cat in enumerate(best_categories):
        category_weights[cat] = max(1, len(best_categories) - i)

    for plan_num in range(num_plans):
        # カテゴリ選択（重み付き）
        cats = list(category_weights.keys())
        weights = [category_weights.get(c, 1) for c in cats]
        # テーマのあるカテゴリのみ
        available_cats = [c for c in cats if c in CONTENT_THEMES]
        if not available_cats:
            available_cats = list(CONTENT_THEMES.keys())

        category = random.choices(
            available_cats,
            weights=[category_weights.get(c, 1) for c in available_cats],
            k=1,
        )[0]

        # テーマ選択（未使用のもの優先）
        available_themes = [
            t for t in CONTENT_THEMES.get(category, [])
            if t["theme"] not in used_themes
        ]
        if not available_themes:
            available_themes = CONTENT_THEMES.get(category, CONTENT_THEMES["暮らし"])

        theme = random.choice(available_themes)
        used_themes.add(theme["theme"])

        # 投稿時間
        hour = random.choice(best_times["best_hours"])
        day = best_times["best_days"][plan_num % len(best_times["best_days"])]

        # ハッシュタグ
        hashtags = _get_optimal_hashtags(main_df, category)

        plan = {
            "番号": plan_num + 1,
            "カテゴリ": category,
            "テーマ": theme["theme"],
            "フォーマット": theme["format"],
            "フック（冒頭文）": theme["hook"],
            "キャプション案": (
                theme["hook"] + "\n\n"
                + "─" * 20 + "\n"
                + "[本文をここに記載]\n"
                + "─" * 20 + "\n\n"
                + " ".join(hashtags)
            ),
            "推奨ハッシュタグ": hashtags,
            "推奨投稿時間": f"{day}曜日 {hour}:00",
            "ポイント": _get_content_tips(category, theme["format"]),
        }
        plans.append(plan)

    # 結果表示
    print(f"\n── 生成された投稿案 ({len(plans)}件) ──\n")
    for plan in plans:
        print(f"【{plan['番号']}】{plan['カテゴリ']} / {plan['テーマ']}")
        print(f"  フォーマット: {plan['フォーマット']}")
        print(f"  フック: {plan['フック（冒頭文）']}")
        print(f"  投稿推奨: {plan['推奨投稿時間']}")
        print(f"  ポイント: {plan['ポイント']}")
        print()

    # 保存
    plans_df = pd.DataFrame(plans)
    output_path = OUTPUT_DIR / "content_plans_latest.csv"
    plans_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    plans_json_path = OUTPUT_DIR / "content_plans_latest.json"
    with open(plans_json_path, "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)

    print(f"投稿案保存: {output_path}")
    return plans


def _get_content_tips(category: str, format_type: str) -> str:
    """カテゴリとフォーマットに応じた投稿のコツ"""
    tips = {
        "暮らし": "生活感のあるナチュラルな雰囲気。BGMは落ち着いた曲。整理整頓されたビジュアルが伸びやすい",
        "旅行": "冒頭3秒で絶景や料理のインパクトカット。場所のテロップ必須。保存されやすい情報量を意識",
        "筋トレ": "ビフォーアフターは数字で変化を見せる。フォーム解説はスロー再生が効果的",
        "美容": "手順をステップで見せる。使用アイテムのテロップ必須。ビフォーアフターが最強",
        "自分磨き": "共感を呼ぶ「変わりたい」というストーリー性。具体的なアクションを提示",
        "大学生活": "リアル感が大事。同世代の「あるある」共感を狙う",
    }

    format_tips = {
        "リール": "冒頭1秒でフック。テンポよく編集。トレンド音源を活用",
        "カルーセル": "1枚目が命。文字は大きく読みやすく。最後にCTA（保存・フォロー促進）",
    }

    base = tips.get(category, "ターゲットの悩みに寄り添うコンテンツを意識")
    fmt = ""
    for key, tip in format_tips.items():
        if key in format_type:
            fmt = f" / {tip}"
            break

    return base + fmt


if __name__ == "__main__":
    generate_content_plans(10)
