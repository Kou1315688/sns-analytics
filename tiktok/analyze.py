"""TikTok 投稿パフォーマンス分析"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR, classify_content

# 日本語フォント設定
def _setup_japanese_font():
    japanese_fonts = [
        "Hiragino Sans", "Hiragino Kaku Gothic Pro",
        "Yu Gothic", "Meiryo", "Noto Sans CJK JP",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in japanese_fonts:
        if font in available:
            plt.rcParams["font.family"] = font
            return

_setup_japanese_font()
sns.set_style("whitegrid")

OUTPUT_DIR = DATA_DIR / "charts"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_latest_data() -> pd.DataFrame:
    """最新のTikTokデータを読み込み"""
    csv_path = DATA_DIR / "tiktok_posts_latest.csv"
    if not csv_path.exists():
        print(f"データファイルが見つかりません: {csv_path}")
        print("先に tiktok/parse_export.py を実行してデータをパースしてください。")
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week_jp"] = df["timestamp"].dt.weekday.map(
            {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
        )
    return df


def add_engagement_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """エンゲージメント指標を追加"""
    df = df.copy()
    df["engagement_total"] = df["likes"] + df["comments"] + df["shares"]
    df["engagement_rate"] = df.apply(
        lambda r: r["engagement_total"] / r["views"] * 100 if r.get("views", 0) > 0 else 0,
        axis=1,
    )
    df["like_rate"] = df.apply(
        lambda r: r["likes"] / r["views"] * 100 if r.get("views", 0) > 0 else 0,
        axis=1,
    )

    # ハッシュタグを文字列からリストに戻す
    if "hashtags" in df.columns and df["hashtags"].dtype == object:
        import ast
        df["hashtags"] = df["hashtags"].apply(
            lambda x: ast.literal_eval(x) if isinstance(x, str) and x.startswith("[") else []
        )

    return df


def top_posts(df: pd.DataFrame, metric: str = "views", n: int = 10) -> pd.DataFrame:
    """トップ投稿ランキング"""
    cols = ["timestamp", "caption", "views", "likes", "comments", "shares",
            "engagement_rate", "primary_category", "link"]
    available_cols = [c for c in cols if c in df.columns]
    return df.nlargest(n, metric)[available_cols].reset_index(drop=True)


def analyze_by_time(df: pd.DataFrame) -> dict:
    """時間帯・曜日別パフォーマンス"""
    day_order = ["月", "火", "水", "木", "金", "土", "日"]
    result = {}

    if "hour" in df.columns:
        result["by_hour"] = df.groupby("hour")[["views", "engagement_rate", "likes"]].mean()

    if "day_of_week_jp" in df.columns:
        by_day = df.groupby("day_of_week_jp")[["views", "engagement_rate", "likes"]].mean()
        result["by_day"] = by_day.reindex([d for d in day_order if d in by_day.index])

    return result


def analyze_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """カテゴリ別パフォーマンス"""
    if "categories" not in df.columns:
        return pd.DataFrame()

    import ast
    rows = []
    for _, row in df.iterrows():
        cats = row["categories"]
        if isinstance(cats, str):
            try:
                cats = ast.literal_eval(cats)
            except (ValueError, SyntaxError):
                cats = [cats]
        for cat in cats:
            rows.append({"category": cat, **row.to_dict()})

    if not rows:
        return pd.DataFrame()

    expanded = pd.DataFrame(rows)
    metrics = ["views", "engagement_rate", "likes", "comments", "shares"]
    available = [m for m in metrics if m in expanded.columns]
    return expanded.groupby("category")[available].agg(["mean", "count"])


def analyze_caption_correlation(df: pd.DataFrame) -> dict:
    """キャプション特性との相関"""
    correlations = {}
    if "caption_length" not in df.columns:
        df["caption_length"] = df["caption"].fillna("").str.len()
    if "hashtag_count" not in df.columns:
        df["hashtag_count"] = df["caption"].fillna("").apply(lambda x: len(re.findall(r"#\S+", x)))

    if df["caption_length"].std() > 0 and "views" in df.columns:
        correlations["caption_length_vs_views"] = df["caption_length"].corr(df["views"])
        correlations["caption_length_vs_engagement"] = df["caption_length"].corr(df["engagement_rate"])
    if df["hashtag_count"].std() > 0 and "views" in df.columns:
        correlations["hashtag_count_vs_views"] = df["hashtag_count"].corr(df["views"])
        correlations["hashtag_count_vs_engagement"] = df["hashtag_count"].corr(df["engagement_rate"])
    return correlations


# ── 可視化 ──

def plot_views_trend(df: pd.DataFrame):
    """再生数推移グラフ"""
    fig, ax1 = plt.subplots(figsize=(14, 6))
    df_sorted = df.sort_values("timestamp")

    ax1.bar(range(len(df_sorted)), df_sorted["views"], alpha=0.7, color="tab:red", label="再生数")
    ax1.set_xlabel("投稿")
    ax1.set_ylabel("再生数", color="tab:red")

    ax2 = ax1.twinx()
    ax2.plot(range(len(df_sorted)), df_sorted["engagement_rate"], "o-", color="tab:blue", label="ER(%)")
    ax2.set_ylabel("エンゲージメント率(%)", color="tab:blue")

    fig.suptitle("TikTok 投稿パフォーマンス推移", fontsize=14)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "tiktok_views_trend.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: tiktok_views_trend.png")


def plot_by_time(df: pd.DataFrame):
    """時間帯・曜日別"""
    time_data = analyze_by_time(df)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    if "by_hour" in time_data and not time_data["by_hour"].empty:
        time_data["by_hour"]["views"].plot(kind="bar", ax=ax1, color="salmon")
        ax1.set_title("時間帯別 平均再生数")
        ax1.set_xlabel("時間")

    if "by_day" in time_data and not time_data["by_day"].empty:
        time_data["by_day"]["views"].plot(kind="bar", ax=ax2, color="skyblue")
        ax2.set_title("曜日別 平均再生数")
        ax2.set_xlabel("曜日")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "tiktok_by_time.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: tiktok_by_time.png")


def plot_by_category(df: pd.DataFrame):
    """カテゴリ別パフォーマンス"""
    cat_data = analyze_by_category(df)
    if cat_data.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    if ("views", "mean") in cat_data.columns:
        cat_data[("views", "mean")].sort_values(ascending=False).plot(
            kind="barh", ax=axes[0], color="salmon"
        )
        axes[0].set_title("カテゴリ別 平均再生数")

    if ("engagement_rate", "mean") in cat_data.columns:
        cat_data[("engagement_rate", "mean")].sort_values(ascending=False).plot(
            kind="barh", ax=axes[1], color="mediumpurple"
        )
        axes[1].set_title("カテゴリ別 平均エンゲージメント率")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "tiktok_by_category.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: tiktok_by_category.png")


def run_full_analysis() -> dict:
    """TikTok全分析を実行"""
    print("=" * 50)
    print("TikTok パフォーマンス分析")
    print("=" * 50)

    df = load_latest_data()
    if df.empty:
        return {}

    df = add_engagement_metrics(df)

    print(f"\n総投稿数: {len(df)}")
    if "timestamp" in df.columns and df["timestamp"].notna().any():
        print(f"期間: {df['timestamp'].min()} ～ {df['timestamp'].max()}")

    # 基本統計
    print("\n── 基本統計 ──")
    for metric in ["views", "likes", "comments", "shares", "engagement_rate"]:
        if metric in df.columns:
            print(f"  {metric}: 平均={df[metric].mean():.1f}, 中央値={df[metric].median():.1f}")

    # トップ投稿
    print("\n── トップ10投稿（再生数） ──")
    top = top_posts(df, "views")
    for i, row in top.iterrows():
        caption_preview = (row.get("caption", "") or "")[:40]
        print(f"  {i+1}. 再生={row.get('views', 0):,} いいね={row.get('likes', 0):,} "
              f"ER={row.get('engagement_rate', 0):.2f}% | {caption_preview}...")

    # カテゴリ別
    print("\n── カテゴリ別 ──")
    cat_analysis = analyze_by_category(df)
    if not cat_analysis.empty:
        print(cat_analysis.to_string())

    # 相関分析
    print("\n── キャプション相関分析 ──")
    correlations = analyze_caption_correlation(df)
    for key, value in correlations.items():
        print(f"  {key}: {value:.3f}")

    # グラフ生成
    print("\n── グラフ生成中 ──")
    if "timestamp" in df.columns and df["timestamp"].notna().any():
        plot_views_trend(df)
        plot_by_time(df)
    plot_by_category(df)

    # 分析済みデータ保存
    df.to_csv(DATA_DIR / "tiktok_analyzed.csv", index=False, encoding="utf-8-sig")

    results = {
        "summary": {
            "total_posts": len(df),
            "avg_views": df["views"].mean(),
            "avg_engagement_rate": df["engagement_rate"].mean(),
            "avg_likes": df["likes"].mean(),
        },
        "top_posts": top.to_dict(orient="records"),
        "correlations": correlations,
    }

    print(f"\n分析完了！")
    return results


if __name__ == "__main__":
    run_full_analysis()
