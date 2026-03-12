"""SNS分析ダッシュボード - Streamlit"""
import json
import ast
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import DATA_DIR, CATEGORIES
from posting_scheduler import (
    load_schedule, save_schedule, generate_weekly_schedule,
    add_scheduled_post, delete_scheduled_post,
    mark_posted, mark_skipped,
    get_todays_posts, get_upcoming_posts,
    save_auto_generated_schedule, update_settings, get_settings, get_history,
)
from github_sync import sync_data_files, is_cloud_environment

st.set_page_config(
    page_title="SNS分析ダッシュボード",
    page_icon="📊",
    layout="wide",
)

# モバイル対応CSS
st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container { padding: 1rem 0.5rem !important; }
    [data-testid="stSidebar"] { min-width: 200px !important; }
    .stButton > button { padding: 0.4rem 0.8rem !important; font-size: 0.85rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ── データ読み込み（キャッシュなし：常に最新を読み込む） ──

def load_instagram_data() -> pd.DataFrame:
    path = DATA_DIR / "instagram_analyzed.csv"
    if not path.exists():
        path = DATA_DIR / "instagram_posts_latest.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_tiktok_data() -> pd.DataFrame:
    path = DATA_DIR / "tiktok_analyzed.csv"
    if not path.exists():
        path = DATA_DIR / "tiktok_posts_latest.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_content_plans():
    path = DATA_DIR / "content_plans_latest.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_research_data() -> pd.DataFrame:
    path = DATA_DIR / "hashtag_research_latest.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def get_last_updated(filename: str) -> str:
    """ファイルの最終更新日時を取得"""
    path = DATA_DIR / filename
    if path.exists():
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    return "未取得"


def run_script(script_path: str, label: str) -> bool:
    """Pythonスクリプトを実行"""
    venv_python = Path(__file__).parent / "venv" / "bin" / "python3"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable
    full_path = Path(__file__).parent / script_path

    try:
        result = subprocess.run(
            [python_cmd, str(full_path)],
            cwd=str(Path(__file__).parent),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            st.success(f"{label} 完了！")
            return True
        else:
            st.error(f"{label} エラー:\n{result.stderr[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        st.error(f"{label} タイムアウト（10分超過）")
        return False


# ── サイドバー ──

st.sidebar.title("📊 SNS分析ツール")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "ページ選択",
    ["🏠 概要", "📸 Instagram分析", "🎵 TikTok分析", "🔍 トレンドリサーチ", "📝 投稿企画", "📅 投稿スケジュール", "⚡ 人生管理"],
)

# データ更新セクション
st.sidebar.markdown("---")
st.sidebar.subheader("🔄 データ更新")

ig_updated = get_last_updated("instagram_posts_latest.csv")
research_updated = get_last_updated("hashtag_research_latest.csv")
plans_updated = get_last_updated("content_plans_latest.json")

st.sidebar.caption(f"IG データ: {ig_updated}")
st.sidebar.caption(f"リサーチ: {research_updated}")
st.sidebar.caption(f"投稿案: {plans_updated}")

col_btn1, col_btn2 = st.sidebar.columns(2)
with col_btn1:
    refresh_ig = st.button("📸 IG更新", use_container_width=True)
with col_btn2:
    refresh_research = st.button("🔍 リサーチ", use_container_width=True)

col_btn3, col_btn4 = st.sidebar.columns(2)
with col_btn3:
    refresh_analyze = st.button("📊 分析実行", use_container_width=True)
with col_btn4:
    refresh_plans = st.button("📝 企画生成", use_container_width=True)

refresh_all = st.sidebar.button("⚡ 全て更新", use_container_width=True)

# GitHub同期ヘルパー
def _sync_after_update(file_list):
    """クラウド環境ならGitHubに自動同期"""
    if is_cloud_environment():
        with st.spinner("GitHubに同期中..."):
            n = sync_data_files(file_list)
            if n > 0:
                st.sidebar.success(f"{n}ファイル同期完了")

# ボタン処理
if refresh_ig or refresh_all:
    with st.sidebar:
        with st.spinner("Instagram データ取得中..."):
            ok = run_script("instagram/fetch.py", "Instagram データ取得")
        if ok:
            _sync_after_update(["instagram_posts_latest.csv", "instagram_account_latest.json"])
        if refresh_all:
            pass  # 続けて分析も実行
        else:
            st.rerun()

if refresh_analyze or refresh_all:
    with st.sidebar:
        with st.spinner("分析実行中..."):
            ok = run_script("instagram/analyze.py", "Instagram 分析")
        if ok:
            _sync_after_update(["instagram_analyzed.csv"])
        if refresh_all:
            pass
        else:
            st.rerun()

if refresh_research or refresh_all:
    with st.sidebar:
        with st.spinner("トレンドリサーチ中..."):
            ok = run_script("research/trend_research.py", "トレンドリサーチ")
        if ok:
            _sync_after_update(["hashtag_research_latest.csv", "research_results_latest.json"])
        if refresh_all:
            pass
        else:
            st.rerun()

if refresh_plans or refresh_all:
    with st.sidebar:
        with st.spinner("投稿案生成中..."):
            ok = run_script("content_planner.py", "投稿案生成")
        if ok:
            _sync_after_update(["content_plans_latest.json", "content_plans_latest.csv"])
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**アカウント**\n"
    "- IG: @k_slf_imp\n"
    "- TikTok: @kou9487"
)

# THE SURGE sidebar stats
from surge import load_surge_data, render_sidebar_surge
_surge_data = load_surge_data()
render_sidebar_surge(_surge_data)

# ── 概要ページ ──

if page == "🏠 概要":
    st.title("📊 SNS分析 & 投稿企画ダッシュボード")
    st.markdown("Instagram・TikTokのパフォーマンス分析と投稿プランニング")

    col1, col2 = st.columns(2)

    # Instagram概要
    with col1:
        st.subheader("📸 Instagram")
        ig_df = load_instagram_data()
        if ig_df.empty:
            st.info("データなし — サイドバーの「📸 IG更新」でデータを取得")
        else:
            metrics = st.columns(3)
            metrics[0].metric("投稿数", len(ig_df))
            if "engagement_rate" in ig_df.columns:
                metrics[1].metric("平均ER", f"{ig_df['engagement_rate'].mean():.2f}%")
            if "reach" in ig_df.columns:
                metrics[2].metric("平均リーチ", f"{ig_df['reach'].mean():,.0f}")

            if "engagement_rate" in ig_df.columns and "timestamp" in ig_df.columns:
                fig = px.line(
                    ig_df.sort_values("timestamp"),
                    x="timestamp", y="engagement_rate",
                    title="エンゲージメント率推移",
                )
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

    # TikTok概要
    with col2:
        st.subheader("🎵 TikTok")
        tk_df = load_tiktok_data()
        if tk_df.empty:
            st.info("データなし — TikTokからデータをエクスポートし解析してください")
        else:
            metrics = st.columns(3)
            metrics[0].metric("投稿数", len(tk_df))
            if "views" in tk_df.columns:
                metrics[1].metric("平均再生数", f"{tk_df['views'].mean():,.0f}")
            if "engagement_rate" in tk_df.columns:
                metrics[2].metric("平均ER", f"{tk_df['engagement_rate'].mean():.2f}%")

            if "views" in tk_df.columns and "timestamp" in tk_df.columns:
                fig = px.bar(
                    tk_df.sort_values("timestamp"),
                    x="timestamp", y="views",
                    title="再生数推移",
                )
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

    # 今日の投稿予定
    st.markdown("---")
    st.subheader("📅 今日の投稿予定")
    todays = get_todays_posts()
    if not todays:
        st.info("今日の投稿予定はありません")
    else:
        # 投稿前チェックリスト（常に表示）
        with st.expander("🎯 投稿前チェック — この3つを言語化できない動画は投稿する価値がない", expanded=True):
            st.markdown(
                "1. **誰の、どの感情を奪いに行くか？**\n"
                "   - 例: 暇つぶし中の大学生の劣等感を刺激し、やる気に変える\n"
                "2. **冒頭1秒の「フック」は何か？**\n"
                "   - 例: 鏡越しの圧倒的ビジュアル + 「まだ寝てるの？」という煽り\n"
                "3. **その動画は君の「熱狂」を伝染させているか？**\n"
                "   - ただの情報提供ではなく、自分の哲学が込められているか"
            )

        for tp in todays:
            with st.container():
                tc1, tc2, tc3 = st.columns([3, 1, 1])
                with tc1:
                    time_str = f"{tp.get('scheduled_hour', 0):02d}:{tp.get('scheduled_minute', 0):02d}"
                    status_icon = "🔔" if tp.get("status") == "reminded" else "📌"
                    st.markdown(
                        f"{status_icon} **{time_str}** — {tp.get('title', '無題')}　"
                        f"`{tp.get('category', '')}`　{tp.get('format', '')}"
                    )
                    hook = tp.get("content_plan", {}).get("フック（冒頭文）", "")
                    if hook:
                        st.caption(f"フック: {hook}")
                with tc2:
                    if st.button("✅ 投稿完了", key=f"done_{tp['id']}", use_container_width=True):
                        mark_posted(tp["id"])
                        _sync_after_update(["posting_schedule.json"])
                        st.rerun()
                with tc3:
                    if st.button("⏭️ スキップ", key=f"skip_{tp['id']}", use_container_width=True):
                        mark_skipped(tp["id"])
                        _sync_after_update(["posting_schedule.json"])
                        st.rerun()

    # 投稿案プレビュー
    st.markdown("---")
    st.subheader("📝 最新の投稿企画")
    plans = load_content_plans()
    if not plans:
        st.info("投稿案なし — サイドバーの「📝 企画生成」で投稿案を生成")
    else:
        cols = st.columns(min(3, len(plans)))
        for i, plan in enumerate(plans[:3]):
            with cols[i]:
                st.markdown(f"**{plan.get('カテゴリ', '')}** / {plan.get('テーマ', '')}")
                st.caption(f"📌 {plan.get('フック（冒頭文）', '')}")
                st.caption(f"⏰ {plan.get('推奨投稿時間', '')}")


# ── Instagram分析ページ ──

elif page == "📸 Instagram分析":
    st.title("📸 Instagram パフォーマンス分析")

    ig_df = load_instagram_data()
    if ig_df.empty:
        st.warning("Instagramデータが見つかりません。")
        st.markdown("サイドバーの「📸 IG更新」→「📊 分析実行」でデータを取得・分析してください。")
        st.stop()

    # 最終更新日時
    st.caption(f"最終更新: {get_last_updated('instagram_analyzed.csv')}")

    # KPI
    st.subheader("📈 全体KPI")
    kpi_cols = st.columns(5)
    kpi_cols[0].metric("総投稿数", len(ig_df))
    if "engagement_rate" in ig_df.columns:
        kpi_cols[1].metric("平均ER", f"{ig_df['engagement_rate'].mean():.2f}%")
    if "reach" in ig_df.columns:
        kpi_cols[2].metric("平均リーチ", f"{ig_df['reach'].mean():,.0f}")
    if "saved" in ig_df.columns:
        kpi_cols[3].metric("平均保存数", f"{ig_df['saved'].mean():.1f}")
    if "like_count" in ig_df.columns:
        kpi_cols[4].metric("平均いいね", f"{ig_df['like_count'].mean():.0f}")

    st.markdown("---")

    # タブ
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 パフォーマンス推移", "📋 投稿一覧", "⏰ 時間帯分析",
        "🏷️ カテゴリ分析", "💬 キャプション分析",
    ])

    with tab1:
        st.subheader("パフォーマンス推移")
        if "timestamp" in ig_df.columns:
            metric_choice = st.selectbox(
                "表示指標",
                ["engagement_rate", "reach", "like_count", "saved", "shares"],
                format_func=lambda x: {
                    "engagement_rate": "エンゲージメント率(%)",
                    "reach": "リーチ",
                    "like_count": "いいね数",
                    "saved": "保存数",
                    "shares": "シェア数",
                }.get(x, x),
            )
            if metric_choice in ig_df.columns:
                fig = make_subplots(specs=[[{"secondary_y": True}]])
                sorted_df = ig_df.sort_values("timestamp")
                fig.add_trace(
                    go.Scatter(x=sorted_df["timestamp"], y=sorted_df[metric_choice],
                               mode="lines+markers", name=metric_choice),
                    secondary_y=False,
                )
                if "reach" in ig_df.columns and metric_choice != "reach":
                    fig.add_trace(
                        go.Bar(x=sorted_df["timestamp"], y=sorted_df["reach"],
                               name="リーチ", opacity=0.3),
                        secondary_y=True,
                    )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("投稿一覧")
        sort_col = st.selectbox(
            "ソート基準",
            [c for c in ["engagement_rate", "reach", "like_count", "saved", "timestamp"]
             if c in ig_df.columns],
            format_func=lambda x: {
                "engagement_rate": "エンゲージメント率",
                "reach": "リーチ",
                "like_count": "いいね数",
                "saved": "保存数",
                "timestamp": "投稿日時",
            }.get(x, x),
        )

        display_cols = [c for c in [
            "timestamp", "media_type", "primary_category", "engagement_rate",
            "reach", "like_count", "saved", "shares", "caption", "permalink",
        ] if c in ig_df.columns]

        sorted_df = ig_df.sort_values(sort_col, ascending=False).head(50).copy()
        if "permalink" in sorted_df.columns:
            sorted_df["permalink"] = sorted_df["permalink"].apply(
                lambda x: x if pd.notna(x) and str(x).startswith("http") else ""
            )
        st.dataframe(
            sorted_df[display_cols],
            use_container_width=True,
            height=600,
            column_config={
                "permalink": st.column_config.LinkColumn("投稿リンク", display_text="開く"),
                "timestamp": st.column_config.DatetimeColumn("投稿日時", format="YYYY-MM-DD HH:mm"),
                "engagement_rate": st.column_config.NumberColumn("ER(%)", format="%.2f"),
                "reach": st.column_config.NumberColumn("リーチ", format="%d"),
                "like_count": st.column_config.NumberColumn("いいね", format="%d"),
                "saved": st.column_config.NumberColumn("保存", format="%d"),
                "shares": st.column_config.NumberColumn("シェア", format="%d"),
                "media_type": st.column_config.TextColumn("タイプ"),
                "primary_category": st.column_config.TextColumn("カテゴリ"),
                "caption": st.column_config.TextColumn("キャプション", width="large"),
            },
        )

    with tab3:
        st.subheader("投稿時間帯 × パフォーマンス")
        if "hour" in ig_df.columns and "engagement_rate" in ig_df.columns:
            col1, col2 = st.columns(2)

            with col1:
                by_hour = ig_df.groupby("hour")["engagement_rate"].mean().reset_index()
                fig = px.bar(by_hour, x="hour", y="engagement_rate",
                             title="時間帯別 平均エンゲージメント率",
                             labels={"hour": "時間", "engagement_rate": "ER(%)"})
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                if "day_of_week_jp" in ig_df.columns:
                    day_order = ["月", "火", "水", "木", "金", "土", "日"]
                    by_day = ig_df.groupby("day_of_week_jp")["engagement_rate"].mean().reset_index()
                    by_day["day_of_week_jp"] = pd.Categorical(
                        by_day["day_of_week_jp"], categories=day_order, ordered=True
                    )
                    by_day = by_day.sort_values("day_of_week_jp")
                    fig = px.bar(by_day, x="day_of_week_jp", y="engagement_rate",
                                 title="曜日別 平均エンゲージメント率",
                                 labels={"day_of_week_jp": "曜日", "engagement_rate": "ER(%)"})
                    st.plotly_chart(fig, use_container_width=True)

            # 投稿タイプ別
            if "media_type" in ig_df.columns:
                by_type = ig_df.groupby("media_type")[["engagement_rate", "reach", "saved"]].mean().reset_index()
                fig = px.bar(by_type, x="media_type", y=["engagement_rate", "reach", "saved"],
                             title="投稿タイプ別パフォーマンス", barmode="group")
                st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("コンテンツカテゴリ分析")
        if "primary_category" in ig_df.columns and "engagement_rate" in ig_df.columns:
            by_cat = ig_df.groupby("primary_category").agg(
                投稿数=("engagement_rate", "count"),
                平均ER=("engagement_rate", "mean"),
                平均リーチ=("reach", "mean") if "reach" in ig_df.columns else ("engagement_rate", "count"),
                平均保存=("saved", "mean") if "saved" in ig_df.columns else ("engagement_rate", "count"),
            ).reset_index()

            col1, col2 = st.columns(2)
            with col1:
                fig = px.bar(by_cat.sort_values("平均ER", ascending=True),
                             x="平均ER", y="primary_category", orientation="h",
                             title="カテゴリ別 平均エンゲージメント率",
                             color="平均ER", color_continuous_scale="viridis")
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig = px.pie(by_cat, names="primary_category", values="投稿数",
                             title="カテゴリ別 投稿数の割合")
                st.plotly_chart(fig, use_container_width=True)

            st.dataframe(by_cat.sort_values("平均ER", ascending=False), use_container_width=True)

    with tab5:
        st.subheader("キャプション分析")
        if "caption_length" not in ig_df.columns:
            ig_df["caption_length"] = ig_df["caption"].fillna("").str.len()
        if "hashtag_count" not in ig_df.columns:
            import re
            ig_df["hashtag_count"] = ig_df["caption"].fillna("").apply(
                lambda x: len(re.findall(r"#\S+", x))
            )

        col1, col2 = st.columns(2)
        with col1:
            if "engagement_rate" in ig_df.columns:
                fig = px.scatter(ig_df, x="caption_length", y="engagement_rate",
                                 color="primary_category" if "primary_category" in ig_df.columns else None,
                                 title="キャプション文字数 vs エンゲージメント率",
                                 trendline="ols",
                                 labels={"caption_length": "文字数", "engagement_rate": "ER(%)"})
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if "engagement_rate" in ig_df.columns:
                fig = px.scatter(ig_df, x="hashtag_count", y="engagement_rate",
                                 color="primary_category" if "primary_category" in ig_df.columns else None,
                                 title="ハッシュタグ数 vs エンゲージメント率",
                                 trendline="ols",
                                 labels={"hashtag_count": "ハッシュタグ数", "engagement_rate": "ER(%)"})
                st.plotly_chart(fig, use_container_width=True)

        # 相関係数
        st.markdown("**相関係数**")
        corr_data = {}
        if "engagement_rate" in ig_df.columns:
            if ig_df["caption_length"].std() > 0:
                corr_data["文字数 × ER"] = ig_df["caption_length"].corr(ig_df["engagement_rate"])
            if ig_df["hashtag_count"].std() > 0:
                corr_data["ハッシュタグ数 × ER"] = ig_df["hashtag_count"].corr(ig_df["engagement_rate"])
        if "reach" in ig_df.columns:
            if ig_df["caption_length"].std() > 0:
                corr_data["文字数 × リーチ"] = ig_df["caption_length"].corr(ig_df["reach"])
        if corr_data:
            st.json(corr_data)


# ── TikTok分析ページ ──

elif page == "🎵 TikTok分析":
    st.title("🎵 TikTok パフォーマンス分析")

    tk_df = load_tiktok_data()
    if tk_df.empty:
        st.warning("TikTokデータが見つかりません。")
        st.markdown("""
        ### データ取得方法
        1. TikTokアプリ → 設定 → アカウント → データをダウンロード → JSON形式
        2. ダウンロードしたJSONを `data/tiktok_export/` に配置
        3. `python tiktok/parse_export.py` を実行
        4. このページをリロード
        """)
        st.stop()

    st.caption(f"最終更新: {get_last_updated('tiktok_analyzed.csv')}")

    # KPI
    st.subheader("📈 全体KPI")
    kpi_cols = st.columns(5)
    kpi_cols[0].metric("総投稿数", len(tk_df))
    if "views" in tk_df.columns:
        kpi_cols[1].metric("平均再生数", f"{tk_df['views'].mean():,.0f}")
        kpi_cols[2].metric("合計再生数", f"{tk_df['views'].sum():,.0f}")
    if "likes" in tk_df.columns:
        kpi_cols[3].metric("平均いいね", f"{tk_df['likes'].mean():,.0f}")
    if "engagement_rate" in tk_df.columns:
        kpi_cols[4].metric("平均ER", f"{tk_df['engagement_rate'].mean():.2f}%")

    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 パフォーマンス推移", "📋 投稿一覧", "⏰ 時間帯分析", "🏷️ カテゴリ分析",
    ])

    with tab1:
        if "timestamp" in tk_df.columns and "views" in tk_df.columns:
            sorted_df = tk_df.sort_values("timestamp")
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Bar(x=sorted_df["timestamp"], y=sorted_df["views"],
                       name="再生数", marker_color="rgba(255, 99, 71, 0.7)"),
                secondary_y=False,
            )
            if "engagement_rate" in tk_df.columns:
                fig.add_trace(
                    go.Scatter(x=sorted_df["timestamp"], y=sorted_df["engagement_rate"],
                               mode="lines+markers", name="ER(%)", line=dict(color="blue")),
                    secondary_y=True,
                )
            fig.update_layout(title="再生数 & エンゲージメント率推移", height=500)
            fig.update_yaxes(title_text="再生数", secondary_y=False)
            fig.update_yaxes(title_text="ER(%)", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        sort_col = st.selectbox(
            "ソート基準",
            [c for c in ["views", "likes", "engagement_rate", "comments", "shares", "timestamp"]
             if c in tk_df.columns],
        )
        display_cols = [c for c in [
            "timestamp", "views", "likes", "comments", "shares",
            "engagement_rate", "primary_category", "caption", "link",
        ] if c in tk_df.columns]
        tk_sorted = tk_df.sort_values(sort_col, ascending=False).head(50).copy()
        if "link" in tk_sorted.columns:
            tk_sorted["link"] = tk_sorted["link"].apply(
                lambda x: x if pd.notna(x) and str(x).startswith("http") else ""
            )
        st.dataframe(
            tk_sorted[display_cols],
            use_container_width=True,
            height=600,
            column_config={
                "link": st.column_config.LinkColumn("投稿リンク", display_text="開く"),
                "timestamp": st.column_config.DatetimeColumn("投稿日時", format="YYYY-MM-DD HH:mm"),
                "views": st.column_config.NumberColumn("再生数", format="%d"),
                "likes": st.column_config.NumberColumn("いいね", format="%d"),
                "comments": st.column_config.NumberColumn("コメント", format="%d"),
                "shares": st.column_config.NumberColumn("シェア", format="%d"),
                "engagement_rate": st.column_config.NumberColumn("ER(%)", format="%.2f"),
                "primary_category": st.column_config.TextColumn("カテゴリ"),
                "caption": st.column_config.TextColumn("キャプション", width="large"),
            },
        )

    with tab3:
        if "hour" in tk_df.columns and "views" in tk_df.columns:
            col1, col2 = st.columns(2)
            with col1:
                by_hour = tk_df.groupby("hour")["views"].mean().reset_index()
                fig = px.bar(by_hour, x="hour", y="views",
                             title="時間帯別 平均再生数",
                             labels={"hour": "時間", "views": "再生数"})
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                if "day_of_week_jp" in tk_df.columns:
                    day_order = ["月", "火", "水", "木", "金", "土", "日"]
                    by_day = tk_df.groupby("day_of_week_jp")["views"].mean().reset_index()
                    by_day["day_of_week_jp"] = pd.Categorical(
                        by_day["day_of_week_jp"], categories=day_order, ordered=True
                    )
                    by_day = by_day.sort_values("day_of_week_jp")
                    fig = px.bar(by_day, x="day_of_week_jp", y="views",
                                 title="曜日別 平均再生数",
                                 labels={"day_of_week_jp": "曜日", "views": "再生数"})
                    st.plotly_chart(fig, use_container_width=True)

    with tab4:
        if "primary_category" in tk_df.columns and "views" in tk_df.columns:
            by_cat = tk_df.groupby("primary_category").agg(
                投稿数=("views", "count"),
                平均再生数=("views", "mean"),
                平均いいね=("likes", "mean") if "likes" in tk_df.columns else ("views", "count"),
                平均ER=("engagement_rate", "mean") if "engagement_rate" in tk_df.columns else ("views", "count"),
            ).reset_index()

            col1, col2 = st.columns(2)
            with col1:
                fig = px.bar(by_cat.sort_values("平均再生数", ascending=True),
                             x="平均再生数", y="primary_category", orientation="h",
                             title="カテゴリ別 平均再生数",
                             color="平均再生数", color_continuous_scale="reds")
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig = px.pie(by_cat, names="primary_category", values="投稿数",
                             title="カテゴリ別投稿数")
                st.plotly_chart(fig, use_container_width=True)


# ── トレンドリサーチページ ──

elif page == "🔍 トレンドリサーチ":
    st.title("🔍 トレンドリサーチ")

    research_df = load_research_data()
    if research_df.empty:
        st.warning("リサーチデータが見つかりません。")
        st.markdown("サイドバーの「🔍 リサーチ」ボタンでデータを取得してください。")
        st.stop()

    st.caption(f"最終更新: {get_last_updated('hashtag_research_latest.csv')}")
    st.subheader("ハッシュタグリサーチ結果")
    st.metric("調査済み投稿数", len(research_df))

    # ハッシュタグ別エンゲージメント
    if "hashtag" in research_df.columns and "engagement" in research_df.columns:
        top_df = research_df[research_df["ranking_type"] == "top"] if "ranking_type" in research_df.columns else research_df
        by_tag = top_df.groupby("hashtag")["engagement"].agg(["mean", "median", "max", "count"]).reset_index()
        by_tag.columns = ["ハッシュタグ", "平均", "中央値", "最大", "投稿数"]

        fig = px.bar(by_tag.sort_values("平均", ascending=True),
                     x="平均", y="ハッシュタグ", orientation="h",
                     title="ハッシュタグ別 平均エンゲージメント（トップ投稿）",
                     color="平均", color_continuous_scale="viridis")
        fig.update_layout(height=max(400, len(by_tag) * 25))
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(by_tag.sort_values("平均", ascending=False), use_container_width=True)

    # カテゴリ分布
    if "primary_category" in research_df.columns:
        st.subheader("トップ投稿のカテゴリ分布")
        cat_dist = research_df["primary_category"].value_counts().reset_index()
        cat_dist.columns = ["カテゴリ", "件数"]
        fig = px.pie(cat_dist, names="カテゴリ", values="件数",
                     title="トップ投稿のカテゴリ分布")
        st.plotly_chart(fig, use_container_width=True)

    # 高エンゲージメント投稿一覧
    st.subheader("高エンゲージメント投稿")
    display_cols = [c for c in ["hashtag", "engagement", "like_count", "comments_count",
                                 "media_type", "primary_category", "caption", "permalink"]
                    if c in research_df.columns]
    if display_cols:
        research_sorted = research_df.sort_values("engagement", ascending=False).head(30).copy()
        if "permalink" in research_sorted.columns:
            research_sorted["permalink"] = research_sorted["permalink"].apply(
                lambda x: x if pd.notna(x) and str(x).startswith("http") else ""
            )
        st.dataframe(
            research_sorted[display_cols],
            use_container_width=True,
            column_config={
                "permalink": st.column_config.LinkColumn("投稿リンク", display_text="開く"),
                "engagement": st.column_config.NumberColumn("エンゲージメント", format="%d"),
                "like_count": st.column_config.NumberColumn("いいね", format="%d"),
                "comments_count": st.column_config.NumberColumn("コメント", format="%d"),
                "hashtag": st.column_config.TextColumn("ハッシュタグ"),
                "media_type": st.column_config.TextColumn("タイプ"),
                "primary_category": st.column_config.TextColumn("カテゴリ"),
                "caption": st.column_config.TextColumn("キャプション", width="large"),
            },
        )


# ── 投稿企画ページ ──

elif page == "📝 投稿企画":
    st.title("📝 投稿企画")

    tab_ai, tab_basic = st.tabs(["🤖 AI構成案", "📋 基本投稿案"])

    # ── AI構成案タブ ──
    with tab_ai:
        st.subheader("🤖 AI投稿構成案ジェネレーター")
        st.markdown(
            "コンテンツのアイデアを入力すると、過去の分析データとトレンドリサーチをもとに、"
            "AIが最適な**撮影構成案**を自動生成します。"
        )

        idea_input = st.text_area(
            "コンテンツアイデアを入力",
            placeholder="例: 大学生の朝活ルーティン、筋トレ始めて3ヶ月のビフォーアフター、一人暮らしの部屋紹介...",
            height=100,
        )

        generate_btn = st.button("🚀 AI構成案を生成", type="primary", use_container_width=True)

        if generate_btn and idea_input.strip():
            from config import GEMINI_API_KEY as _check_key
            if not _check_key:
                st.error(
                    "GEMINI_API_KEY が設定されていません。\n\n"
                    "`.env` ファイルに `GEMINI_API_KEY=AIza...` を追加してください。"
                )
            else:
                from ai_content_planner import generate_ai_plan, export_plan_to_excel

                with st.spinner("AI構成案を生成中... (類似投稿の検索 → 構成案の作成)"):
                    plan = generate_ai_plan(idea_input.strip())

                if plan:
                    st.success("構成案の生成が完了しました！")
                    st.rerun()
                else:
                    st.error("構成案の生成に失敗しました。もう一度お試しください。")

        elif generate_btn and not idea_input.strip():
            st.warning("コンテンツアイデアを入力してください。")

        # ── 生成済み構成案の表示 ──
        st.markdown("---")

        from ai_content_planner import load_latest_plan, load_plan_history, export_plan_to_excel

        # 履歴セレクター
        history = load_plan_history()
        if history:
            st.subheader("生成済み構成案")

            # 履歴選択
            history_options = []
            for i, h in enumerate(reversed(history)):
                ts = h.get("_generated_at", "")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts)
                        ts_display = dt.strftime("%m/%d %H:%M")
                    except (ValueError, TypeError):
                        ts_display = ts[:16]
                else:
                    ts_display = f"#{len(history) - i}"
                title = h.get("title", h.get("_idea", "無題"))
                history_options.append(f"{ts_display} - {title}")

            selected_idx = st.selectbox(
                "構成案を選択",
                range(len(history_options)),
                format_func=lambda x: history_options[x],
            )

            # 選択された構成案（逆順なので変換）
            selected_plan = list(reversed(history))[selected_idx]

            # 構成案表示
            st.markdown(f"## {selected_plan.get('title', '')}")

            # メタ情報
            meta_cols = st.columns(4)
            meta_cols[0].metric("フォーマット", selected_plan.get("format", ""))
            meta_cols[1].metric("動画尺", selected_plan.get("duration", ""))
            meta_cols[2].metric("シーン数", len(selected_plan.get("scenes", [])))
            meta_cols[3].metric("推奨投稿時間", selected_plan.get("posting_time", ""))

            # ヘッダー情報
            with st.expander("📋 概要情報", expanded=True):
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.markdown(f"**フック:** {selected_plan.get('hook', '')}")
                    st.markdown(f"**音声:** {selected_plan.get('audio', '')}")
                    st.markdown(f"**音源:** {selected_plan.get('music', '')}")
                with info_col2:
                    st.markdown(f"**衣装・ロケーション:**")
                    st.info(selected_plan.get("outfit_location", ""))

            # キャプション
            with st.expander("💬 キャプション（ハッシュタグ含む）"):
                st.code(selected_plan.get("caption", ""), language=None)

            # シーン別構成
            st.markdown("### 🎬 シーン構成")
            scenes = selected_plan.get("scenes", [])
            if scenes:
                # テーブル表示
                scene_data = []
                for s in scenes:
                    scene_data.append({
                        "No.": s.get("scene_number", ""),
                        "尺": s.get("duration", ""),
                        "シーン": s.get("scene_description", ""),
                        "ロケーション": s.get("location", ""),
                        "衣装": s.get("outfit", ""),
                        "時刻": s.get("time_of_day", ""),
                        "映像・動作": s.get("video_action", ""),
                        "テロップ": s.get("text_overlay", ""),
                        "セリフ": s.get("narration", ""),
                    })

                scene_df = pd.DataFrame(scene_data)
                st.dataframe(
                    scene_df,
                    use_container_width=True,
                    height=min(400, 60 * len(scenes) + 40),
                    column_config={
                        "No.": st.column_config.NumberColumn("No.", width="small"),
                        "尺": st.column_config.TextColumn("尺", width="small"),
                        "シーン": st.column_config.TextColumn("シーン", width="medium"),
                        "映像・動作": st.column_config.TextColumn("映像・動作", width="large"),
                        "テロップ": st.column_config.TextColumn("テロップ", width="medium"),
                        "セリフ": st.column_config.TextColumn("セリフ", width="medium"),
                    },
                )

                # シーン詳細（展開式）
                for s in scenes:
                    with st.expander(f"シーン {s.get('scene_number', '')}: {s.get('scene_description', '')}"):
                        detail_col1, detail_col2 = st.columns(2)
                        with detail_col1:
                            st.markdown(f"**尺:** {s.get('duration', '')}")
                            st.markdown(f"**ロケーション:** {s.get('location', '')}")
                            st.markdown(f"**衣装:** {s.get('outfit', '')}")
                            st.markdown(f"**時刻:** {s.get('time_of_day', '')}")
                        with detail_col2:
                            st.markdown("**映像・動作:**")
                            st.info(s.get("video_action", ""))
                            st.markdown(f"**テロップ:** {s.get('text_overlay', '')}")
                            st.markdown(f"**セリフ:** {s.get('narration', '')}")

            # ポイント・知見
            with st.expander("💡 ポイント・注意事項"):
                st.markdown(selected_plan.get("tips", ""))

            with st.expander("📊 参考データからの知見"):
                st.markdown(selected_plan.get("reference_analysis", ""))

            # Excel出力
            st.markdown("---")
            if st.button("📥 構成案をExcelダウンロード", use_container_width=True):
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    excel_path = export_plan_to_excel(selected_plan, tmp.name)

                with open(excel_path, "rb") as f:
                    excel_data = f.read()

                title_safe = re.sub(r"[^\w\s\-]", "", selected_plan.get("title", "構成案"))
                st.download_button(
                    "📄 Excelファイルをダウンロード",
                    excel_data,
                    file_name=f"構成案_{title_safe}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        else:
            st.info("まだAI構成案が生成されていません。上のフォームからアイデアを入力して生成してください。")

    # ── 基本投稿案タブ ──
    with tab_basic:
        st.subheader("📋 テンプレート投稿案")

        plans = load_content_plans()

        if not plans:
            st.warning("投稿案が見つかりません。")
            st.markdown("サイドバーの「📝 企画生成」ボタンで投稿案を生成してください。")
        else:
            st.caption(f"最終更新: {get_last_updated('content_plans_latest.json')}")
            st.success(f"{len(plans)}件の投稿案があります")

            # フィルタ
            categories = list(set(p.get("カテゴリ", "") for p in plans))
            selected_cats = st.multiselect("カテゴリで絞り込み", categories, default=categories)

            filtered = [p for p in plans if p.get("カテゴリ", "") in selected_cats]

            for plan in filtered:
                with st.expander(f"**{plan.get('番号', '')}. [{plan.get('カテゴリ', '')}] {plan.get('テーマ', '')}**"):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"### {plan.get('テーマ', '')}")
                        st.markdown(f"**フック:** {plan.get('フック（冒頭文）', '')}")
                        st.markdown(f"**フォーマット:** {plan.get('フォーマット', '')}")
                        st.markdown(f"**投稿推奨:** {plan.get('推奨投稿時間', '')}")
                        st.markdown("---")
                        st.markdown("**キャプション案:**")
                        st.code(plan.get("キャプション案", ""), language=None)
                    with col2:
                        st.markdown("**ポイント:**")
                        st.info(plan.get("ポイント", ""))
                        tags = plan.get("推奨ハッシュタグ", [])
                        if tags:
                            st.markdown("**ハッシュタグ:**")
                            st.code(" ".join(tags), language=None)

            # CSV出力
            st.markdown("---")
            plans_df = pd.DataFrame(filtered)
            csv_data = plans_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "📥 投稿案をCSVダウンロード",
                csv_data,
                file_name="content_plans.csv",
                mime="text/csv",
            )


# ── 投稿スケジュールページ ──

elif page == "📅 投稿スケジュール":
    st.title("📅 投稿スケジュール")

    tab_week, tab_add, tab_auto, tab_settings = st.tabs([
        "📅 週間スケジュール", "➕ 手動追加", "🤖 自動生成", "⚙️ 通知設定",
    ])

    # ── 週間スケジュール ──
    with tab_week:
        st.subheader("今後7日間のスケジュール")

        # 投稿前3問チェックリスト
        with st.expander("🎯 投稿前チェック — 3つの必須質問"):
            st.markdown(
                "**この3つを言語化できない動画は、投稿する価値がない。**\n\n"
                "1. **誰の、どの感情を奪いに行くか？**\n"
                "   - 例: 暇つぶし中の大学生の劣等感を刺激し、やる気に変える\n\n"
                "2. **冒頭1秒の「フック」は何か？**\n"
                "   - 例: 鏡越しの圧倒的ビジュアル + 「まだ寝てるの？」という煽り\n\n"
                "3. **その動画は君の「熱狂」を伝染させているか？**\n"
                "   - ただの情報提供ではなく、「退屈への拒絶」という哲学が込められているか"
            )

        upcoming = get_upcoming_posts(days=7)

        if not upcoming:
            st.info("今後7日間の投稿予定はありません。「🤖 自動生成」または「➕ 手動追加」でスケジュールを作成してください。")
        else:
            # 日別にグループ化
            from datetime import date as date_type
            from collections import defaultdict
            day_groups = defaultdict(list)
            for p in upcoming:
                day_groups[p["scheduled_date"]].append(p)

            day_names = {"月": "Mon", "火": "Tue", "水": "Wed", "木": "Thu", "金": "Fri", "土": "Sat", "日": "Sun"}

            for d_str in sorted(day_groups.keys()):
                posts = day_groups[d_str]
                d = date_type.fromisoformat(d_str)
                day_jp = posts[0].get("scheduled_day", "")
                is_today = d == date_type.today()
                header = f"{'**🔵 今日** ' if is_today else ''}{d_str} ({day_jp})"
                st.markdown(f"### {header}")

                for p in sorted(posts, key=lambda x: (x["scheduled_hour"], x["scheduled_minute"])):
                    time_str = f"{p['scheduled_hour']:02d}:{p['scheduled_minute']:02d}"
                    status_map = {
                        "scheduled": "🟡 予定",
                        "reminded": "🔔 通知済",
                        "posted": "✅ 完了",
                        "skipped": "⏭️ スキップ",
                    }
                    status_label = status_map.get(p["status"], p["status"])

                    col_info, col_act1, col_act2, col_del = st.columns([4, 1, 1, 1])
                    with col_info:
                        st.markdown(
                            f"**{time_str}** — {p['title']}　`{p['category']}`　"
                            f"{p['format']}　{status_label}　"
                            f"{'🤖' if p.get('source') == 'auto' else '✏️'}"
                        )
                    with col_act1:
                        if p["status"] in ("scheduled", "reminded"):
                            if st.button("✅ 完了", key=f"wk_done_{p['id']}", use_container_width=True):
                                mark_posted(p["id"])
                                _sync_after_update(["posting_schedule.json"])
                                st.rerun()
                    with col_act2:
                        if p["status"] in ("scheduled", "reminded"):
                            if st.button("⏭️", key=f"wk_skip_{p['id']}", use_container_width=True):
                                mark_skipped(p["id"])
                                _sync_after_update(["posting_schedule.json"])
                                st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"wk_del_{p['id']}", use_container_width=True):
                            delete_scheduled_post(p["id"])
                            _sync_after_update(["posting_schedule.json"])
                            st.rerun()

                st.markdown("---")

        # 履歴
        st.subheader("📜 投稿履歴")
        hist = get_history(20)
        if hist:
            hist_data = []
            for h in hist:
                hist_data.append({
                    "日付": h.get("scheduled_date", ""),
                    "時間": f"{h.get('scheduled_hour', 0):02d}:{h.get('scheduled_minute', 0):02d}",
                    "テーマ": h.get("title", ""),
                    "カテゴリ": h.get("category", ""),
                    "ステータス": "✅ 完了" if h.get("status") == "posted" else "⏭️ スキップ",
                    "完了日時": h.get("completed_at", "")[:16] if h.get("completed_at") else "",
                })
            st.dataframe(pd.DataFrame(hist_data), use_container_width=True, hide_index=True)
        else:
            st.caption("まだ履歴がありません")

    # ── 手動追加 ──
    with tab_add:
        st.subheader("➕ 投稿スケジュールを手動追加")

        with st.form("add_schedule_form"):
            add_title = st.text_input("テーマ / タイトル", placeholder="例: 朝活ルーティン リール投稿")
            add_col1, add_col2 = st.columns(2)
            with add_col1:
                add_category = st.selectbox("カテゴリ", list(CATEGORIES.keys()))
                add_format = st.selectbox("フォーマット", ["リール", "カルーセル", "リール/カルーセル", "ストーリー"])
            with add_col2:
                add_date = st.date_input("投稿日")
                add_time_col1, add_time_col2 = st.columns(2)
                with add_time_col1:
                    add_hour = st.number_input("時", min_value=0, max_value=23, value=20)
                with add_time_col2:
                    add_minute = st.number_input("分", min_value=0, max_value=59, value=0, step=5)
            add_notes = st.text_area("メモ（任意）", height=80)
            add_reminder = st.number_input("リマインド（投稿の何分前）", min_value=5, max_value=120, value=30, step=5)

            submitted = st.form_submit_button("📅 スケジュールに追加", use_container_width=True)
            if submitted and add_title.strip():
                add_scheduled_post(
                    title=add_title.strip(),
                    category=add_category,
                    format_type=add_format,
                    scheduled_date=add_date.isoformat(),
                    scheduled_hour=add_hour,
                    scheduled_minute=add_minute,
                    notes=add_notes,
                    reminder_minutes=add_reminder,
                )
                st.success(f"「{add_title}」をスケジュールに追加しました！")
                _sync_after_update(["posting_schedule.json"])
                st.rerun()
            elif submitted:
                st.warning("テーマを入力してください")

    # ── 自動生成 ──
    with tab_auto:
        st.subheader("🤖 週間スケジュール自動生成")
        st.markdown("投稿企画（`content_plans_latest.json`）の推奨投稿時間をもとに、今後の具体的な日付のスケジュールを自動生成します。")

        plans = load_content_plans()
        if not plans:
            st.warning("投稿案がありません。先に「📝 投稿企画」で投稿案を生成してください。")
        else:
            st.info(f"利用可能な投稿案: {len(plans)}件")

            auto_col1, auto_col2 = st.columns(2)
            with auto_col1:
                auto_start = st.date_input("スケジュール開始日", value=datetime.now().date())
            with auto_col2:
                auto_count = st.number_input("生成件数", min_value=1, max_value=min(10, len(plans)), value=min(5, len(plans)))

            if st.button("🔄 プレビュー生成", use_container_width=True):
                preview = generate_weekly_schedule(plans, week_start=auto_start, max_posts=auto_count)
                st.session_state["schedule_preview"] = preview

            # プレビュー表示
            if "schedule_preview" in st.session_state and st.session_state["schedule_preview"]:
                preview = st.session_state["schedule_preview"]
                st.markdown("### プレビュー")

                for p in preview:
                    time_str = f"{p['scheduled_hour']:02d}:{p['scheduled_minute']:02d}"
                    st.markdown(
                        f"- **{p['scheduled_date']}** ({p['scheduled_day']}) "
                        f"{time_str} — {p['title']}　`{p['category']}`　{p['format']}"
                    )

                if st.button("✅ このスケジュールを確定", type="primary", use_container_width=True):
                    save_auto_generated_schedule(preview)
                    st.session_state.pop("schedule_preview", None)
                    st.success(f"{len(preview)}件のスケジュールを保存しました！")
                    _sync_after_update(["posting_schedule.json"])
                    st.rerun()

                if st.button("🔄 再生成", use_container_width=True):
                    st.session_state.pop("schedule_preview", None)
                    st.rerun()

    # ── 通知設定 ──
    with tab_settings:
        st.subheader("⚙️ 通知設定")

        settings = get_settings()

        with st.form("notification_settings_form"):
            st.markdown("#### 通知チャネル ON/OFF")
            notif = settings.get("notifications_enabled", {})
            en_dashboard = st.checkbox("📊 ダッシュボード通知", value=notif.get("dashboard", True))
            en_line = st.checkbox("💬 LINE Notify", value=notif.get("line", False))
            en_gmail = st.checkbox("📧 Gmail通知", value=notif.get("gmail", False))

            st.markdown("---")
            st.markdown("#### LINE Notify 設定")
            st.caption("[LINE Notify トークン発行ページ](https://notify-bot.line.me/my/) からトークンを取得してください")
            line_token = st.text_input("LINE Notify Token", value=settings.get("line_notify_token", ""), type="password")

            st.markdown("---")
            st.markdown("#### Gmail 設定")
            st.caption("Googleアカウントの「アプリパスワード」を使用してください")
            gmail_addr = st.text_input("Gmail アドレス", value=settings.get("gmail_address", ""))
            gmail_pass = st.text_input("Gmail アプリパスワード", value=settings.get("gmail_app_password", ""), type="password")
            reminder_email = st.text_input("通知先メールアドレス（空欄=送信元と同じ）", value=settings.get("reminder_to_email", ""))

            st.markdown("---")
            default_minutes = st.number_input(
                "デフォルトリマインド時間（分前）",
                min_value=5, max_value=120,
                value=settings.get("default_reminder_minutes", 30),
                step=5,
            )

            save_btn = st.form_submit_button("💾 設定を保存", use_container_width=True)
            if save_btn:
                update_settings({
                    "line_notify_token": line_token,
                    "gmail_address": gmail_addr,
                    "gmail_app_password": gmail_pass,
                    "reminder_to_email": reminder_email,
                    "default_reminder_minutes": default_minutes,
                    "notifications_enabled": {
                        "dashboard": en_dashboard,
                        "line": en_line,
                        "gmail": en_gmail,
                    },
                })
                st.success("設定を保存しました！")

        # テスト送信
        st.markdown("---")
        st.markdown("#### テスト送信")
        test_col1, test_col2 = st.columns(2)

        test_post = {
            "title": "テスト通知",
            "category": "自分磨き",
            "format": "リール",
            "scheduled_date": datetime.now().date().isoformat(),
            "scheduled_hour": 20,
            "scheduled_minute": 0,
            "content_plan": {"フック（冒頭文）": "これはテスト通知です"},
            "notes": "",
        }

        with test_col1:
            if st.button("💬 LINE テスト送信", use_container_width=True):
                settings = get_settings()
                token = settings.get("line_notify_token", "")
                if not token:
                    st.error("LINE Notify Token が設定されていません")
                else:
                    from notifier import send_line_notify, format_reminder_message
                    msg = format_reminder_message(test_post)
                    if send_line_notify(token, msg):
                        st.success("LINE テスト送信成功！")
                    else:
                        st.error("LINE テスト送信失敗。トークンを確認してください。")

        with test_col2:
            if st.button("📧 Gmail テスト送信", use_container_width=True):
                settings = get_settings()
                gmail_addr = settings.get("gmail_address", "")
                gmail_pass = settings.get("gmail_app_password", "")
                to_email = settings.get("reminder_to_email", "") or gmail_addr
                if not gmail_addr or not gmail_pass:
                    st.error("Gmail アドレスまたはアプリパスワードが設定されていません")
                else:
                    from notifier import send_gmail, format_reminder_message
                    msg = format_reminder_message(test_post)
                    if send_gmail(gmail_addr, gmail_pass, to_email, "📱 テスト通知", msg):
                        st.success("Gmail テスト送信成功！")
                    else:
                        st.error("Gmail テスト送信失敗。設定を確認してください。")

        # デーモン稼働状況
        st.markdown("---")
        st.markdown("#### 🖥️ スケジューラーデーモン稼働状況")
        heartbeat_path = DATA_DIR / "scheduler_heartbeat.json"
        if heartbeat_path.exists():
            with open(heartbeat_path, "r") as f:
                hb = json.load(f)
            status = hb.get("status", "unknown")
            last_check = hb.get("last_check", "不明")
            status_icon = {"running": "🟢", "stopped": "🔴", "error": "🟠"}.get(status, "⚪")
            st.markdown(f"{status_icon} ステータス: **{status}**")
            st.caption(f"最終チェック: {last_check}")
            if hb.get("error"):
                st.error(f"エラー: {hb['error']}")
        else:
            st.warning(
                "スケジューラーデーモンが起動していません。\n\n"
                "起動方法:\n"
                "```bash\npython scheduler_daemon.py\n```\n"
                "または自動起動設定:\n"
                "```bash\npython scheduler_daemon.py --install\nlaunchctl load ~/Library/LaunchAgents/com.sns-analytics.scheduler.plist\n```"
            )


# ── THE SURGE ページ ──

elif page == "⚡ 人生管理":
    from surge import render_surge_page
    render_surge_page()
