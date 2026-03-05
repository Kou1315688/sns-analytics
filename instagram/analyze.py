"""Instagram 投稿パフォーマンス分析"""
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
    """利用可能な日本語フォントを検索して設定"""
    japanese_fonts = [
        "Hiragino Sans", "Hiragino Kaku Gothic Pro",
        "Yu Gothic", "Meiryo", "Noto Sans CJK JP",
        "IPAGothic", "IPAPGothic",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in japanese_fonts:
        if font in available:
            plt.rcParams["font.family"] = font
            return
    print("警告: 日本語フォントが見つかりません。グラフの日本語が文字化けする可能性があります。")

_setup_japanese_font()
sns.set_style("whitegrid")

OUTPUT_DIR = DATA_DIR / "charts"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_latest_data() -> pd.DataFrame:
    """最新のInstagramデータを読み込み"""
    csv_path = DATA_DIR / "instagram_posts_latest.csv"
    if not csv_path.exists():
        print(f"データファイルが見つかりません: {csv_path}")
        print("先に instagram/fetch.py を実行してデータを取得してください。")
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.day_name()
    df["day_of_week_jp"] = df["timestamp"].dt.weekday.map(
        {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
    )
    return df


def add_engagement_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """エンゲージメント指標を追加"""
    df = df.copy()

    # エンゲージメント率 = (いいね+コメント+保存+シェア) / リーチ
    df["engagement_total"] = (
        df["like_count"] + df["comments_count"] + df["saved"].fillna(0) + df["shares"].fillna(0)
    )
    df["engagement_rate"] = df.apply(
        lambda r: r["engagement_total"] / r["reach"] * 100 if r.get("reach", 0) > 0 else 0,
        axis=1,
    )

    # 保存率
    df["save_rate"] = df.apply(
        lambda r: r["saved"] / r["reach"] * 100 if r.get("reach", 0) > 0 else 0,
        axis=1,
    )

    # キャプション分析
    df["caption_length"] = df["caption"].fillna("").str.len()
    df["hashtag_count"] = df["caption"].fillna("").apply(
        lambda x: len(re.findall(r"#\S+", x))
    )
    df["hashtags"] = df["caption"].fillna("").apply(
        lambda x: re.findall(r"#(\S+)", x)
    )

    # カテゴリ分類
    df["categories"] = df["caption"].fillna("").apply(classify_content)
    df["primary_category"] = df["categories"].apply(lambda x: x[0] if x else "その他")

    return df


def top_posts(df: pd.DataFrame, metric: str = "engagement_rate", n: int = 10) -> pd.DataFrame:
    """トップ投稿をランキング"""
    cols = ["timestamp", "media_type", "caption", "reach", "engagement_rate",
            "like_count", "saved", "shares", "primary_category", "permalink"]
    available_cols = [c for c in cols if c in df.columns]
    return df.nlargest(n, metric)[available_cols].reset_index(drop=True)


def analyze_by_media_type(df: pd.DataFrame) -> pd.DataFrame:
    """投稿タイプ別パフォーマンス分析"""
    metrics = ["reach", "engagement_rate", "like_count", "comments_count", "saved", "shares", "save_rate"]
    available = [m for m in metrics if m in df.columns]
    result = df.groupby("media_type")[available].agg(["mean", "median", "count"])
    return result


def analyze_by_time(df: pd.DataFrame) -> dict:
    """投稿時間帯・曜日別パフォーマンス"""
    day_order = ["月", "火", "水", "木", "金", "土", "日"]

    by_hour = df.groupby("hour")[["engagement_rate", "reach"]].mean()
    by_day = df.groupby("day_of_week_jp")[["engagement_rate", "reach"]].mean()
    if not by_day.empty:
        by_day = by_day.reindex([d for d in day_order if d in by_day.index])

    return {"by_hour": by_hour, "by_day": by_day}


def analyze_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """コンテンツカテゴリ別パフォーマンス"""
    # カテゴリを展開（1投稿が複数カテゴリの場合がある）
    rows = []
    for _, row in df.iterrows():
        for cat in row["categories"]:
            rows.append({"category": cat, **row.to_dict()})
    expanded = pd.DataFrame(rows)

    metrics = ["reach", "engagement_rate", "like_count", "saved", "save_rate"]
    available = [m for m in metrics if m in expanded.columns]
    return expanded.groupby("category")[available].agg(["mean", "count"])


def analyze_caption_correlation(df: pd.DataFrame) -> dict:
    """キャプション特性との相関分析"""
    correlations = {}
    if "engagement_rate" in df.columns:
        if df["caption_length"].std() > 0:
            correlations["caption_length_vs_engagement"] = df["caption_length"].corr(df["engagement_rate"])
        if df["hashtag_count"].std() > 0:
            correlations["hashtag_count_vs_engagement"] = df["hashtag_count"].corr(df["engagement_rate"])
        if "reach" in df.columns and df["caption_length"].std() > 0:
            correlations["caption_length_vs_reach"] = df["caption_length"].corr(df["reach"])
        if "reach" in df.columns and df["hashtag_count"].std() > 0:
            correlations["hashtag_count_vs_reach"] = df["hashtag_count"].corr(df["reach"])
    return correlations


def analyze_hashtags(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """ハッシュタグ別パフォーマンス"""
    rows = []
    for _, row in df.iterrows():
        for tag in row.get("hashtags", []):
            rows.append({
                "hashtag": tag,
                "reach": row.get("reach", 0),
                "engagement_rate": row.get("engagement_rate", 0),
                "saved": row.get("saved", 0),
            })
    if not rows:
        return pd.DataFrame()

    tag_df = pd.DataFrame(rows)
    result = tag_df.groupby("hashtag").agg(
        使用回数=("reach", "count"),
        平均リーチ=("reach", "mean"),
        平均エンゲージメント率=("engagement_rate", "mean"),
        平均保存数=("saved", "mean"),
    ).sort_values("平均エンゲージメント率", ascending=False)
    return result.head(top_n)


# ── 可視化 ──

def plot_engagement_trend(df: pd.DataFrame):
    """エンゲージメント推移グラフ"""
    fig, ax1 = plt.subplots(figsize=(14, 6))
    df_sorted = df.sort_values("timestamp")

    ax1.plot(df_sorted["timestamp"], df_sorted["engagement_rate"], "o-", color="tab:blue", label="エンゲージメント率(%)")
    ax1.set_xlabel("投稿日")
    ax1.set_ylabel("エンゲージメント率 (%)", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.bar(df_sorted["timestamp"], df_sorted["reach"], alpha=0.3, color="tab:orange", label="リーチ")
    ax2.set_ylabel("リーチ", color="tab:orange")
    ax2.tick_params(axis="y", labelcolor="tab:orange")

    fig.suptitle("投稿パフォーマンス推移", fontsize=14)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "engagement_trend.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: engagement_trend.png")


def plot_by_media_type(df: pd.DataFrame):
    """投稿タイプ別比較"""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for ax, metric, title in zip(
        axes,
        ["engagement_rate", "reach", "saved"],
        ["エンゲージメント率(%)", "リーチ", "保存数"],
    ):
        if metric in df.columns:
            data = df.groupby("media_type")[metric].mean().sort_values(ascending=False)
            data.plot(kind="bar", ax=ax, color=sns.color_palette("pastel"))
            ax.set_title(title)
            ax.set_xlabel("")
            ax.tick_params(axis="x", rotation=0)

    fig.suptitle("投稿タイプ別パフォーマンス", fontsize=14)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "by_media_type.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: by_media_type.png")


def plot_by_time(df: pd.DataFrame):
    """時間帯・曜日別ヒートマップ"""
    time_data = analyze_by_time(df)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # 時間帯別
    by_hour = time_data["by_hour"]
    if not by_hour.empty:
        by_hour["engagement_rate"].plot(kind="bar", ax=ax1, color="steelblue")
        ax1.set_title("時間帯別 平均エンゲージメント率")
        ax1.set_xlabel("時間")
        ax1.set_ylabel("エンゲージメント率 (%)")

    # 曜日別
    by_day = time_data["by_day"]
    if not by_day.empty:
        by_day["engagement_rate"].plot(kind="bar", ax=ax2, color="coral")
        ax2.set_title("曜日別 平均エンゲージメント率")
        ax2.set_xlabel("曜日")
        ax2.set_ylabel("エンゲージメント率 (%)")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "by_time.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: by_time.png")


def plot_by_category(df: pd.DataFrame):
    """カテゴリ別パフォーマンス"""
    cat_data = analyze_by_category(df)
    if cat_data.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # エンゲージメント率
    if ("engagement_rate", "mean") in cat_data.columns:
        cat_data[("engagement_rate", "mean")].sort_values(ascending=False).plot(
            kind="barh", ax=axes[0], color="mediumpurple"
        )
        axes[0].set_title("カテゴリ別 平均エンゲージメント率")
        axes[0].set_xlabel("エンゲージメント率 (%)")

    # 投稿数
    if ("reach", "count") in cat_data.columns:
        cat_data[("reach", "count")].sort_values(ascending=False).plot(
            kind="barh", ax=axes[1], color="mediumseagreen"
        )
        axes[1].set_title("カテゴリ別 投稿数")
        axes[1].set_xlabel("投稿数")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "by_category.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: by_category.png")


def plot_caption_analysis(df: pd.DataFrame):
    """キャプション分析散布図"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    if "engagement_rate" in df.columns:
        ax1.scatter(df["caption_length"], df["engagement_rate"], alpha=0.6, c="steelblue")
        ax1.set_xlabel("キャプション文字数")
        ax1.set_ylabel("エンゲージメント率 (%)")
        ax1.set_title("文字数 vs エンゲージメント率")

        # トレンドライン
        if len(df) > 2 and df["caption_length"].std() > 0:
            z = np.polyfit(df["caption_length"], df["engagement_rate"], 1)
            p = np.poly1d(z)
            x_range = np.linspace(df["caption_length"].min(), df["caption_length"].max(), 100)
            ax1.plot(x_range, p(x_range), "--", color="red", alpha=0.5)

        ax2.scatter(df["hashtag_count"], df["engagement_rate"], alpha=0.6, c="coral")
        ax2.set_xlabel("ハッシュタグ数")
        ax2.set_ylabel("エンゲージメント率 (%)")
        ax2.set_title("ハッシュタグ数 vs エンゲージメント率")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "caption_analysis.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  保存: caption_analysis.png")


def run_full_analysis() -> dict:
    """全分析を実行"""
    print("=" * 50)
    print("Instagram パフォーマンス分析")
    print("=" * 50)

    df = load_latest_data()
    if df.empty:
        return {}

    df = add_engagement_metrics(df)

    print(f"\n総投稿数: {len(df)}")
    print(f"期間: {df['timestamp'].min().strftime('%Y-%m-%d')} ～ {df['timestamp'].max().strftime('%Y-%m-%d')}")

    # 基本統計
    print("\n── 基本統計 ──")
    for metric in ["reach", "engagement_rate", "like_count", "saved", "shares"]:
        if metric in df.columns:
            print(f"  {metric}: 平均={df[metric].mean():.1f}, 中央値={df[metric].median():.1f}")

    # トップ投稿
    print("\n── トップ10投稿（エンゲージメント率） ──")
    top = top_posts(df)
    for i, row in top.iterrows():
        caption_preview = (row.get("caption", "") or "")[:40]
        print(f"  {i+1}. [{row.get('media_type', '')}] ER={row.get('engagement_rate', 0):.2f}% "
              f"R={row.get('reach', 0)} | {caption_preview}...")

    # タイプ別分析
    print("\n── 投稿タイプ別 ──")
    type_analysis = analyze_by_media_type(df)
    print(type_analysis.to_string())

    # カテゴリ別分析
    print("\n── カテゴリ別 ──")
    cat_analysis = analyze_by_category(df)
    print(cat_analysis.to_string())

    # キャプション相関
    print("\n── キャプション相関分析 ──")
    correlations = analyze_caption_correlation(df)
    for key, value in correlations.items():
        print(f"  {key}: {value:.3f}")

    # ハッシュタグ分析
    print("\n── ハッシュタグ別パフォーマンス Top20 ──")
    tag_analysis = analyze_hashtags(df)
    if not tag_analysis.empty:
        print(tag_analysis.to_string())

    # グラフ生成
    print("\n── グラフ生成中 ──")
    plot_engagement_trend(df)
    plot_by_media_type(df)
    plot_by_time(df)
    plot_by_category(df)
    plot_caption_analysis(df)

    # 分析結果をJSON保存
    results = {
        "summary": {
            "total_posts": len(df),
            "avg_engagement_rate": df["engagement_rate"].mean(),
            "avg_reach": df["reach"].mean(),
            "avg_saves": df["saved"].mean(),
        },
        "top_posts": top.to_dict(orient="records"),
        "by_category": cat_analysis.to_dict() if not cat_analysis.empty else {},
        "correlations": correlations,
        "best_hour": int(df.groupby("hour")["engagement_rate"].mean().idxmax()) if not df.empty else 0,
        "best_day": df.groupby("day_of_week_jp")["engagement_rate"].mean().idxmax() if not df.empty else "",
    }

    # 分析済みデータ保存
    df.to_csv(DATA_DIR / "instagram_analyzed.csv", index=False, encoding="utf-8-sig")
    print(f"\n分析済みデータ保存: {DATA_DIR / 'instagram_analyzed.csv'}")
    print(f"グラフ保存先: {OUTPUT_DIR}")

    return results


if __name__ == "__main__":
    run_full_analysis()
