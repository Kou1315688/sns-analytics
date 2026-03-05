"""THE SURGE - Gamified Self-Management Engine
アドレナリン駆動型タスク管理システム
"""
import json
import uuid
import time as time_module
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import DATA_DIR, GEMINI_API_KEY

# ══════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════

SURGE_DATA_FILE = DATA_DIR / "surge_data.json"

CATEGORIES = {
    "sns":       {"label": "SNS",      "icon": "📱", "color": "#E91E63"},
    "revenue":   {"label": "収益",     "icon": "💰", "color": "#F5A623"},
    "body":      {"label": "筋肉",     "icon": "💪", "color": "#4CAF50"},
    "lifestyle": {"label": "暮らし",   "icon": "🏠", "color": "#4A90D9"},
    "discovery": {"label": "発見",     "icon": "🔮", "color": "#9C27B0"},
}

DURATION_OPTIONS = {
    3:  {"label": "⚡ 3分 (Quick Match)",  "multiplier": 2},
    15: {"label": "🔥 15分 (Ranked Match)", "multiplier": 5},
    30: {"label": "💀 30分 (Boss Fight)",   "multiplier": 10},
}

LEVEL_THRESHOLDS = [
    (0,    "Rookie",      "🥉"),
    (50,   "Fighter",     "🥈"),
    (150,  "Warrior",     "🥇"),
    (300,  "Gladiator",   "⚔️"),
    (500,  "Champion",    "👑"),
    (800,  "Legend",       "🌟"),
    (1200, "Master",      "💎"),
    (1800, "Grandmaster", "🔱"),
    (2500, "Mythic",      "🏆"),
    (3500, "SUPREME",     "⚡"),
]

# ══════════════════════════════════════════════════════════
#  DATA PERSISTENCE
# ══════════════════════════════════════════════════════════

def _default_data() -> dict:
    return {
        "profile": {
            "total_trophies": 0,
            "stats": {k: 0 for k in CATEGORIES},
            "streak_current": 0,
            "streak_best": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
        },
        "tasks": [],
        "history": [],
    }


def load_surge_data() -> dict:
    if SURGE_DATA_FILE.exists():
        with open(SURGE_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return _default_data()
    return _default_data()


def save_surge_data(data: dict):
    with open(SURGE_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
#  GAME LOGIC
# ══════════════════════════════════════════════════════════

def get_level(trophies: int) -> tuple:
    """(level_number, name, icon, threshold, next_threshold)"""
    level = 1
    name = "Rookie"
    icon = "🥉"
    threshold = 0
    next_threshold = 50

    for i, (t, n, ic) in enumerate(LEVEL_THRESHOLDS):
        if trophies >= t:
            level = i + 1
            name = n
            icon = ic
            threshold = t
            next_threshold = LEVEL_THRESHOLDS[i + 1][0] if i + 1 < len(LEVEL_THRESHOLDS) else t + 1000
        else:
            break

    return level, name, icon, threshold, next_threshold


def get_level_progress(trophies: int) -> float:
    _, _, _, threshold, next_threshold = get_level(trophies)
    span = next_threshold - threshold
    if span <= 0:
        return 1.0
    return min(1.0, (trophies - threshold) / span)


def calculate_trophies(task: dict, early_finish: bool = False) -> int:
    """タスク完了時の獲得トロフィーを算出"""
    impact = task.get("future_impact", 1)
    duration = task.get("duration", 3)
    category = task.get("category", "")

    base = impact * DURATION_OPTIONS.get(duration, {"multiplier": 2})["multiplier"]

    # Discovery bonus: 2x
    if category == "discovery":
        base *= 2

    # Early finish bonus: +20%
    if early_finish:
        base = int(base * 1.2)

    return max(1, int(base))


def calculate_penalty_trophies(task: dict) -> int:
    """失敗時の喪失トロフィーを算出"""
    impact = task.get("future_impact", 1)
    duration = task.get("duration", 3)
    base = impact * DURATION_OPTIONS.get(duration, {"multiplier": 2})["multiplier"]
    return max(1, int(base * 0.5))


def assess_future_impact(task_name: str, category: str) -> Dict[str, Any]:
    """AIがタスクの未来への貢献度(1-5)を自動判定"""
    cat_label = CATEGORIES.get(category, {}).get("label", category)

    # Gemini APIが使えない場合のフォールバック
    if not GEMINI_API_KEY:
        return {"score": 3, "reason": "API未設定のためデフォルト値"}

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""あなたは20歳の法学生インフルエンサーのライフコーチです。
以下のタスクが「5年後の将来」にどれほど貢献するかを1〜5で厳密に評価してください。

タスク: {task_name}
カテゴリ: {cat_label}

評価基準:
1 = 将来への影響ほぼなし（単純作業、娯楽の延長）
2 = わずかに影響（日常維持レベル）
3 = 中程度の影響（スキルが少し伸びる、習慣形成に寄与）
4 = 高い影響（キャリア・収益・健康に直結する成長）
5 = 極めて高い影響（人生の方向を変えうる重要タスク）

ユーザーのプロフィール:
- 20歳の大学生
- Instagram 1.4万フォロワーのインフルエンサー
- 筋トレ・美容・暮らし系コンテンツを発信
- 将来はSNS×ビジネスで稼ぎたい（収益化・ブランド構築が最重要）

必ず以下のJSON形式のみで回答してください:
{{"score": 数値, "reason": "判定理由（1文）"}}"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"temperature": 0.3, "max_output_tokens": 1024},
        )

        import re
        text = response.text.strip()
        # markdownコードブロック除去
        code_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if code_match:
            text = code_match.group(1)
        # JSON抽出
        json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            score = max(1, min(5, int(result.get("score", 3))))
            reason = result.get("reason", "")
            return {"score": score, "reason": reason}

    except Exception as e:
        print(f"AI判定エラー: {e}")

    # フォールバック: カテゴリベースのデフォルト
    defaults = {"sns": 4, "revenue": 4, "body": 3, "lifestyle": 3, "discovery": 4}
    return {"score": defaults.get(category, 3), "reason": "自動判定（フォールバック）"}


def add_task(data: dict, task_name: str, category: str, future_impact: int,
             duration: int, penalty: str) -> dict:
    task = {
        "id": str(uuid.uuid4())[:8],
        "task_name": task_name,
        "category": category,
        "future_impact": future_impact,
        "duration": duration,
        "penalty": penalty,
        "status": "quest",
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "trophies_earned": 0,
    }
    data["tasks"].append(task)
    save_surge_data(data)
    return task


def start_task(data: dict, task_id: str) -> Optional[dict]:
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["status"] = "in_progress"
            task["started_at"] = datetime.now().isoformat()
            save_surge_data(data)
            return task
    return None


def complete_task(data: dict, task_id: str, early_finish: bool = False) -> Optional[dict]:
    for task in data["tasks"]:
        if task["id"] == task_id:
            trophies = calculate_trophies(task, early_finish)

            # Streak bonus
            profile = data["profile"]
            profile["streak_current"] += 1
            if profile["streak_current"] >= 3:
                trophies = int(trophies * 1.5)
            if profile["streak_current"] > profile["streak_best"]:
                profile["streak_best"] = profile["streak_current"]

            task["status"] = "cleared"
            task["completed_at"] = datetime.now().isoformat()
            task["trophies_earned"] = trophies

            profile["total_trophies"] += trophies
            profile["stats"][task["category"]] = profile["stats"].get(task["category"], 0) + task["future_impact"]
            profile["tasks_completed"] += 1

            # Move to history
            data["history"].append(task.copy())
            data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]

            save_surge_data(data)
            return task
    return None


def fail_task(data: dict, task_id: str) -> Optional[dict]:
    for task in data["tasks"]:
        if task["id"] == task_id:
            penalty_trophies = calculate_penalty_trophies(task)

            profile = data["profile"]
            profile["total_trophies"] = max(0, profile["total_trophies"] - penalty_trophies)
            profile["streak_current"] = 0
            profile["tasks_failed"] += 1

            task["status"] = "failed"
            task["completed_at"] = datetime.now().isoformat()
            task["trophies_earned"] = -penalty_trophies

            data["history"].append(task.copy())
            data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]

            save_surge_data(data)
            return task
    return None


def get_quest_tasks(data: dict) -> List[dict]:
    return [t for t in data["tasks"] if t["status"] == "quest"]


def get_radar_data(data: dict) -> Dict[str, int]:
    return {k: data["profile"]["stats"].get(k, 0) for k in CATEGORIES}


def calculate_future_debuff(task: dict, data: dict) -> str:
    """タスクをサボった場合のデバフを算出"""
    category = task.get("category", "")
    impact = task.get("future_impact", 1)
    cat_label = CATEGORIES.get(category, {}).get("label", category)

    current_stat = data["profile"]["stats"].get(category, 0)

    debuffs = {
        "sns": f"推定フォロワー増加率が{impact * 12}%鈍化。エンゲージメント低下でアルゴリズム不利に",
        "revenue": f"月間推定収益が¥{impact * 5000:,}減少。収益化の達成が{impact * 2}週間遅延",
        "body": f"筋力維持率が{impact * 10}%低下。体脂肪率+{impact * 0.3:.1f}%の悪化リスク",
        "lifestyle": f"QOL低下リスク。コンテンツのネタ枯渇→SNS更新頻度が{impact * 15}%低下",
        "discovery": f"新しい可能性の発見機会を{impact}件喪失。視野の固定化リスク上昇",
    }

    return debuffs.get(category, f"{cat_label}ステータスが{impact}pt低下する見込み")


def calculate_future_vision(data: dict) -> Dict[str, dict]:
    """各カテゴリの未来予測"""
    vision = {}

    # 直近7日の完了タスク
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    recent = [
        h for h in data["history"]
        if h.get("status") == "cleared" and h.get("completed_at")
        and datetime.fromisoformat(h["completed_at"]) > week_ago
    ]

    for cat_key, cat_info in CATEGORIES.items():
        cat_recent = [h for h in recent if h["category"] == cat_key]
        cat_all_cleared = [h for h in data["history"] if h.get("category") == cat_key and h.get("status") == "cleared"]
        weekly_tasks = len(cat_recent)
        weekly_impact = sum(h.get("future_impact", 0) for h in cat_recent)
        total_stat = data["profile"]["stats"].get(cat_key, 0)

        momentum = "停滞" if weekly_tasks == 0 else "成長中" if weekly_tasks >= 3 else "緩やか"

        # 30日後の予測ステータス
        projected_30d = total_stat + (weekly_impact * 4)

        vision[cat_key] = {
            "label": cat_info["label"],
            "icon": cat_info["icon"],
            "current_stat": total_stat,
            "weekly_tasks": weekly_tasks,
            "weekly_impact": weekly_impact,
            "momentum": momentum,
            "projected_30d": projected_30d,
            "total_completed": len(cat_all_cleared),
        }

    return vision


# ══════════════════════════════════════════════════════════
#  CSS INJECTION - Brawl Stars Aesthetic
# ══════════════════════════════════════════════════════════

def inject_surge_css():
    st.markdown("""
    <style>
    /* ── SURGE Global Theme ── */
    .surge-title {
        font-size: 2.8rem;
        font-weight: 900;
        text-align: center;
        background: linear-gradient(135deg, #FF6B35, #FFD700, #FF4444);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: none;
        letter-spacing: 2px;
        margin-bottom: 0;
    }
    .surge-subtitle {
        text-align: center;
        color: #888;
        font-size: 0.9rem;
        margin-top: -10px;
        margin-bottom: 20px;
    }

    /* ── Profile Card ── */
    .profile-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 2px solid #FFD700;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 0 20px rgba(255, 215, 0, 0.15);
    }
    .profile-level {
        font-size: 2rem;
        font-weight: 900;
        color: #FFD700;
        text-align: center;
    }
    .profile-name {
        font-size: 1.1rem;
        color: #FFD700;
        text-align: center;
        font-weight: 700;
    }
    .trophy-count {
        font-size: 1.5rem;
        font-weight: 800;
        color: #FFD700;
        text-align: center;
    }

    /* ── Progress Bar ── */
    .xp-bar-outer {
        background: #1a1a2e;
        border-radius: 10px;
        height: 16px;
        border: 1px solid #333;
        overflow: hidden;
        margin: 8px 0;
    }
    .xp-bar-inner {
        height: 100%;
        border-radius: 10px;
        background: linear-gradient(90deg, #FF6B35, #FFD700);
        transition: width 0.5s ease;
    }

    /* ── Boss Card ── */
    .boss-card {
        background: linear-gradient(145deg, #1a0000, #2d0000);
        border: 2px solid #FF4444;
        border-radius: 16px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 0 25px rgba(255, 68, 68, 0.2);
        transition: transform 0.2s;
    }
    .boss-card:hover {
        transform: scale(1.02);
    }
    .boss-card-s {
        background: linear-gradient(145deg, #0a0a1a, #1a1a2e);
        border: 1px solid #444;
        border-radius: 12px;
        padding: 15px;
        margin: 8px 0;
    }
    .boss-name {
        font-size: 1.3rem;
        font-weight: 800;
        color: #FF6B35;
    }
    .boss-name-s {
        font-size: 1.1rem;
        font-weight: 700;
        color: #ddd;
    }
    .impact-stars {
        color: #FFD700;
        font-size: 1.2rem;
        letter-spacing: 2px;
    }

    /* ── HP Bar ── */
    .hp-bar-outer {
        background: #1a1a1a;
        border-radius: 8px;
        height: 24px;
        border: 2px solid #FF4444;
        overflow: hidden;
        margin: 8px 0;
    }
    .hp-bar-inner {
        height: 100%;
        border-radius: 6px;
        background: linear-gradient(90deg, #FF0000, #FF6600, #00FF88);
        transition: width 0.3s ease;
    }

    /* ── Trophy Badge ── */
    .trophy-badge {
        display: inline-block;
        background: linear-gradient(135deg, #FFD700, #FF8C00);
        color: #000;
        font-weight: 900;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.9rem;
    }

    /* ── Category Badge ── */
    .cat-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-weight: 700;
        font-size: 0.8rem;
        color: #fff;
    }

    /* ── Streak Badge ── */
    .streak-badge {
        display: inline-block;
        background: linear-gradient(135deg, #FF4444, #FF6B35);
        color: #fff;
        font-weight: 800;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
    }

    /* ── Penalty Box ── */
    .penalty-box {
        background: linear-gradient(135deg, #2d0000, #1a0000);
        border: 2px solid #FF0000;
        border-radius: 12px;
        padding: 15px;
        margin: 10px 0;
        color: #FF6666;
        font-weight: 600;
    }

    /* ── Debuff Warning ── */
    .debuff-warning {
        background: linear-gradient(135deg, #1a0a00, #2d1500);
        border-left: 4px solid #FF6600;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
        color: #FFaa66;
    }

    /* ── Victory Card ── */
    .victory-card {
        background: linear-gradient(135deg, #001a00, #002d00);
        border: 2px solid #00FF88;
        border-radius: 16px;
        padding: 25px;
        text-align: center;
        box-shadow: 0 0 30px rgba(0, 255, 136, 0.2);
    }
    .victory-title {
        font-size: 2rem;
        font-weight: 900;
        color: #00FF88;
    }
    .victory-trophies {
        font-size: 2.5rem;
        font-weight: 900;
        color: #FFD700;
    }

    /* ── Sidebar Surge ── */
    .sidebar-surge-box {
        background: linear-gradient(135deg, #1a1a2e, #0d1117);
        border: 1px solid #FFD700;
        border-radius: 12px;
        padding: 12px;
        margin: 8px 0;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
#  UI COMPONENTS
# ══════════════════════════════════════════════════════════

def render_sidebar_surge(data: dict):
    """サイドバーにトロフィー・ロードを表示"""
    profile = data["profile"]
    trophies = profile["total_trophies"]
    level, name, icon, _, next_thresh = get_level(trophies)
    progress = get_level_progress(trophies)
    streak = profile["streak_current"]

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f'<div class="sidebar-surge-box">'
        f'<div style="font-size:1.4rem;font-weight:900;color:#FFD700;">{icon} Lv.{level} {name}</div>'
        f'<div style="color:#FFD700;font-size:1.2rem;font-weight:800;">🏆 {trophies}</div>'
        f'<div class="xp-bar-outer"><div class="xp-bar-inner" style="width:{progress*100:.0f}%"></div></div>'
        f'<div style="color:#888;font-size:0.75rem;">{trophies} / {next_thresh}</div>'
        + (f'<div class="streak-badge">🔥 {streak} STREAK</div>' if streak > 0 else '')
        + '</div>',
        unsafe_allow_html=True,
    )


def _render_profile_card(data: dict):
    """プロフィールカード"""
    profile = data["profile"]
    trophies = profile["total_trophies"]
    level, name, icon, _, next_thresh = get_level(trophies)
    progress = get_level_progress(trophies)

    st.markdown(
        f'<div class="profile-card">'
        f'<div class="profile-level">{icon} Lv.{level}</div>'
        f'<div class="profile-name">{name}</div>'
        f'<div class="trophy-count">🏆 {trophies} TROPHIES</div>'
        f'<div class="xp-bar-outer"><div class="xp-bar-inner" style="width:{progress*100:.0f}%"></div></div>'
        f'<div style="text-align:center;color:#888;font-size:0.8rem;">Next: {next_thresh} 🏆</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_radar_chart(data: dict):
    """5角形レーダーチャート"""
    stats = get_radar_data(data)

    categories_list = []
    values = []
    for k, v in CATEGORIES.items():
        categories_list.append(f"{v['icon']} {v['label']}")
        values.append(stats.get(k, 0))

    # Close the polygon
    categories_list.append(categories_list[0])
    values.append(values[0])

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories_list,
        fill='toself',
        fillcolor='rgba(255, 107, 53, 0.3)',
        line=dict(color='#FFD700', width=3),
        marker=dict(size=8, color='#FFD700'),
    ))

    max_val = max(max(values), 10)
    fig.update_layout(
        polar=dict(
            bgcolor='rgba(13, 17, 23, 0.8)',
            radialaxis=dict(
                visible=True, range=[0, max_val],
                gridcolor='rgba(255,255,255,0.1)',
                tickfont=dict(color='#888'),
            ),
            angularaxis=dict(
                gridcolor='rgba(255,255,255,0.1)',
                tickfont=dict(color='#ddd', size=13),
            ),
        ),
        showlegend=False,
        height=350,
        margin=dict(t=30, b=30, l=60, r=60),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_boss_card(task: dict, show_debuff: bool = False, data: Optional[dict] = None):
    """ボスカード表示"""
    cat = task.get("category", "discovery")
    cat_info = CATEGORIES.get(cat, CATEGORIES["discovery"])
    impact = task.get("future_impact", 1)
    duration = task.get("duration", 3)
    dur_info = DURATION_OPTIONS.get(duration, DURATION_OPTIONS[3])
    stars = "★" * impact + "☆" * (5 - impact)
    trophies = calculate_trophies(task)
    bonus_text = " (Discovery 2x!)" if cat == "discovery" else ""

    is_boss = impact >= 4
    card_class = "boss-card" if is_boss else "boss-card-s"
    name_class = "boss-name" if is_boss else "boss-name-s"
    size = f"font-size: {1.0 + impact * 0.3:.1f}rem;" if is_boss else ""

    st.markdown(
        f'<div class="{card_class}">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<div>'
        f'<span class="cat-badge" style="background:{cat_info["color"]}">{cat_info["icon"]} {cat_info["label"]}</span>'
        f' <span style="color:#888;">{dur_info["label"]}</span>'
        f'</div>'
        f'<div class="impact-stars">{stars}</div>'
        f'</div>'
        f'<div class="{name_class}" style="{size}">{task["task_name"]}</div>'
        f'<div style="color:#FFD700;font-weight:700;margin-top:4px;">🏆 +{trophies}{bonus_text}</div>'
        + (f'<div class="penalty-box">⚠️ PENALTY: {task["penalty"]}</div>' if task.get("penalty") else '')
        + '</div>',
        unsafe_allow_html=True,
    )

    if show_debuff and data:
        debuff = calculate_future_debuff(task, data)
        st.markdown(
            f'<div class="debuff-warning">⚠️ サボった場合: {debuff}</div>',
            unsafe_allow_html=True,
        )


def _render_arena_timer(task: dict):
    """JavaScriptベースのカウントダウンタイマー"""
    duration_ms = task["duration"] * 60 * 1000
    started_at = datetime.fromisoformat(task["started_at"])
    end_time_ms = int((started_at + timedelta(minutes=task["duration"])).timestamp() * 1000)
    cat_info = CATEGORIES.get(task["category"], CATEGORIES["discovery"])
    impact = task.get("future_impact", 1)

    html = f"""
    <div id="arena-wrap" style="
        background: linear-gradient(135deg, #1a0000, #0d0000);
        border: 3px solid #FF4444;
        border-radius: 20px;
        padding: 30px;
        text-align: center;
        box-shadow: 0 0 40px rgba(255,68,68,0.3);
    ">
        <div style="font-size:1.2rem;color:#FF6B35;font-weight:800;letter-spacing:3px;">
            ⚔️ ARENA MODE ⚔️
        </div>
        <div style="font-size:1.5rem;color:#fff;font-weight:800;margin:10px 0;">
            {cat_info['icon']} {task['task_name']}
        </div>
        <div style="margin:15px 0;">
            <div style="background:#1a1a1a;border-radius:10px;height:28px;border:2px solid #FF4444;overflow:hidden;">
                <div id="hp-fill" style="height:100%;border-radius:8px;
                    background:linear-gradient(90deg,#FF0000,#FF6600,#00FF88);width:100%;
                    transition:width 0.5s linear;"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:4px;">
                <span style="color:#FF6666;font-size:0.8rem;">BOSS HP</span>
                <span id="hp-pct" style="color:#FF6666;font-size:0.8rem;">100%</span>
            </div>
        </div>
        <div id="countdown" style="
            font-size: 4.5rem;
            font-weight: 900;
            color: #FF4444;
            text-shadow: 0 0 30px rgba(255,68,68,0.5);
            font-family: monospace;
            margin: 10px 0;
        ">--:--</div>
        <div id="arena-msg" style="color:#FF6B35;font-weight:700;font-size:1rem;">
            DESTROY THE BOSS!
        </div>
    </div>
    <script>
    (function() {{
        var endTime = {end_time_ms};
        var totalDuration = {duration_ms};
        var countdownEl = document.getElementById('countdown');
        var hpFill = document.getElementById('hp-fill');
        var hpPct = document.getElementById('hp-pct');
        var msgEl = document.getElementById('arena-msg');
        var wrap = document.getElementById('arena-wrap');

        function update() {{
            var now = Date.now();
            var remaining = Math.max(0, endTime - now);
            var progress = remaining / totalDuration;
            var mins = Math.floor(remaining / 60000);
            var secs = Math.floor((remaining % 60000) / 1000);

            countdownEl.textContent =
                String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
            hpFill.style.width = (progress * 100) + '%';
            hpPct.textContent = Math.round(progress * 100) + '%';

            if (progress < 0.15) {{
                countdownEl.style.color = '#FF0000';
                countdownEl.style.textShadow = '0 0 50px #FF0000';
                wrap.style.borderColor = '#FF0000';
                msgEl.textContent = '⚡ FINISH HIM! ⚡';
            }} else if (progress < 0.4) {{
                countdownEl.style.color = '#FF6600';
                msgEl.textContent = '🔥 KEEP PUSHING!';
            }}

            if (remaining <= 0) {{
                countdownEl.textContent = '00:00';
                msgEl.textContent = '🏆 TIME UP - MISSION COMPLETE!';
                msgEl.style.color = '#00FF88';
                countdownEl.style.color = '#00FF88';
                countdownEl.style.textShadow = '0 0 30px #00FF88';
                wrap.style.borderColor = '#00FF88';
                wrap.style.boxShadow = '0 0 40px rgba(0,255,136,0.3)';
                clearInterval(interval);
                setTimeout(function() {{
                    window.parent.location.reload();
                }}, 2000);
            }}
        }}

        var interval = setInterval(update, 200);
        update();
    }})();
    </script>
    """
    st.components.v1.html(html, height=320)


def _render_victory(task: dict, data: dict):
    """勝利演出"""
    st.balloons()
    trophies = task.get("trophies_earned", 0)
    streak = data["profile"]["streak_current"]

    st.markdown(
        f'<div class="victory-card">'
        f'<div class="victory-title">🎉 MISSION CLEARED! 🎉</div>'
        f'<div style="font-size:1.2rem;color:#ccc;margin:10px 0;">{task["task_name"]}</div>'
        f'<div class="victory-trophies">🏆 +{trophies}</div>'
        + (f'<div class="streak-badge" style="margin-top:10px;">🔥 {streak} STREAK BONUS!</div>' if streak >= 3 else '')
        + f'</div>',
        unsafe_allow_html=True,
    )


def _render_defeat(task: dict):
    """敗北演出"""
    lost = abs(task.get("trophies_earned", 0))
    penalty = task.get("penalty", "")

    st.markdown(
        f'<div class="penalty-box" style="text-align:center;padding:25px;">'
        f'<div style="font-size:2rem;font-weight:900;color:#FF0000;">💀 MISSION FAILED 💀</div>'
        f'<div style="font-size:1.2rem;color:#FF6666;margin:10px 0;">{task["task_name"]}</div>'
        f'<div style="font-size:1.8rem;font-weight:900;color:#FF4444;">🏆 -{lost}</div>'
        + (f'<div style="margin-top:15px;font-size:1.1rem;color:#FF0000;font-weight:800;">'
           f'⚖️ PENALTY発動: {penalty}</div>' if penalty else '')
        + f'<div style="color:#FF6666;margin-top:8px;">STREAK RESET → 0</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════
#  MAIN PAGE RENDERER
# ══════════════════════════════════════════════════════════

def render_surge_page():
    """THE SURGE メインページ"""
    inject_surge_css()

    data = load_surge_data()

    # Init session state
    if "surge_arena_task_id" not in st.session_state:
        st.session_state["surge_arena_task_id"] = None
    if "surge_last_result" not in st.session_state:
        st.session_state["surge_last_result"] = None

    # Check if arena task timer has expired
    arena_task_id = st.session_state.get("surge_arena_task_id")
    if arena_task_id:
        arena_task = None
        for t in data["tasks"]:
            if t["id"] == arena_task_id and t["status"] == "in_progress":
                arena_task = t
                break

        if arena_task:
            started = datetime.fromisoformat(arena_task["started_at"])
            end_time = started + timedelta(minutes=arena_task["duration"])
            if datetime.now() >= end_time:
                result = complete_task(data, arena_task_id, early_finish=False)
                data = load_surge_data()
                st.session_state["surge_arena_task_id"] = None
                st.session_state["surge_last_result"] = {"type": "victory", "task": result}

    # Title
    st.markdown('<div class="surge-title">⚡ 人生管理 ⚡</div>', unsafe_allow_html=True)
    st.markdown('<div class="surge-subtitle">Contract with Your Future Self</div>', unsafe_allow_html=True)

    # Show last result (victory/defeat)
    last_result = st.session_state.get("surge_last_result")
    if last_result:
        if last_result["type"] == "victory":
            _render_victory(last_result["task"], data)
        elif last_result["type"] == "defeat":
            _render_defeat(last_result["task"])
        if st.button("OK", use_container_width=True):
            st.session_state["surge_last_result"] = None
            st.rerun()
        return

    # Active arena?
    if arena_task_id:
        arena_task = None
        for t in data["tasks"]:
            if t["id"] == arena_task_id and t["status"] == "in_progress":
                arena_task = t
                break

        if arena_task:
            _render_arena_mode(arena_task, data)
            return
        else:
            st.session_state["surge_arena_task_id"] = None

    # Normal view: tabs
    tab_arena, tab_quest, tab_status, tab_vision = st.tabs([
        "⚔️ Arena", "📋 Quest Board", "📊 Status", "🔮 Future Vision"
    ])

    with tab_arena:
        _render_arena_tab(data)

    with tab_quest:
        _render_quest_board_tab(data)

    with tab_status:
        _render_status_tab(data)

    with tab_vision:
        _render_future_vision_tab(data)


def _render_arena_mode(task: dict, data: dict):
    """アリーナモード（タスク実行中）"""
    # Countdown timer (JavaScript)
    _render_arena_timer(task)

    st.markdown("")  # spacing

    col1, col2 = st.columns(2)
    with col1:
        early_trophies = calculate_trophies(task, early_finish=True)
        if st.button(f"🏆 MISSION COMPLETE (+{early_trophies}🏆)", use_container_width=True, type="primary"):
            result = complete_task(data, task["id"], early_finish=True)
            st.session_state["surge_arena_task_id"] = None
            st.session_state["surge_last_result"] = {"type": "victory", "task": result}
            st.rerun()

    with col2:
        if st.button("💀 GIVE UP", use_container_width=True):
            result = fail_task(data, task["id"])
            st.session_state["surge_arena_task_id"] = None
            st.session_state["surge_last_result"] = {"type": "defeat", "task": result}
            st.rerun()

    # Debuff warning
    st.markdown("")
    debuff = calculate_future_debuff(task, data)
    st.markdown(
        f'<div class="debuff-warning">💀 ここで逃げた場合: {debuff}</div>',
        unsafe_allow_html=True,
    )


def _render_arena_tab(data: dict):
    """Arena タブ: クエスト一覧からマッチ選択"""
    st.subheader("⚔️ Match Select")

    quests = get_quest_tasks(data)

    if not quests:
        st.info("クエストがありません。「Quest Board」タブで新しいタスクを登録してください。")
        return

    # Sort by future_impact descending (bosses first)
    quests.sort(key=lambda t: t.get("future_impact", 0), reverse=True)

    for task in quests:
        _render_boss_card(task, show_debuff=True, data=data)

        col1, col2 = st.columns([3, 1])
        with col1:
            trophies = calculate_trophies(task)
            st.caption(
                f"⏱️ {task['duration']}分 | 🏆 +{trophies} | "
                f"{'🔥 Discovery 2x!' if task['category'] == 'discovery' else ''}"
            )
        with col2:
            if st.button("⚔️ START", key=f"start_{task['id']}", use_container_width=True, type="primary"):
                started = start_task(data, task["id"])
                if started:
                    st.session_state["surge_arena_task_id"] = task["id"]
                    st.rerun()

        # Delete option
        if st.button("🗑️ 削除", key=f"del_{task['id']}", type="secondary"):
            data["tasks"] = [t for t in data["tasks"] if t["id"] != task["id"]]
            save_surge_data(data)
            st.rerun()


def _render_quest_board_tab(data: dict):
    """Quest Board タブ: タスク登録"""
    st.subheader("📋 New Quest Registration")
    st.markdown("自分との**契約**を締結する。")

    task_name = st.text_input("🎯 Quest Name (タスク名)", placeholder="例: 民法総則の判例を5件読む")

    col1, col2 = st.columns(2)
    with col1:
        category = st.selectbox(
            "📂 Category",
            options=list(CATEGORIES.keys()),
            format_func=lambda k: f"{CATEGORIES[k]['icon']} {CATEGORIES[k]['label']}"
            + (" ← 2x BONUS!" if k == "discovery" else ""),
        )
    with col2:
        duration = st.radio(
            "⏱️ Match Duration",
            options=list(DURATION_OPTIONS.keys()),
            format_func=lambda k: DURATION_OPTIONS[k]["label"],
        )

    st.markdown("---")
    st.markdown("**⚖️ Penalty Clause (ペナルティ規定)**")
    st.caption("∀x (Task(x) ∧ ¬Completed(x) → Penalty) — 未達成時に発動する罰則を定めよ")
    penalty = st.text_input(
        "Penalty",
        placeholder="例: ブロスタ24時間禁止 / スタバ1杯奢り / 腕立て100回",
    )

    # AI Impact Assessment
    st.markdown("---")

    # session_stateでAI判定結果を保持
    if "surge_ai_assessment" not in st.session_state:
        st.session_state["surge_ai_assessment"] = None
    if "surge_ai_assessed_name" not in st.session_state:
        st.session_state["surge_ai_assessed_name"] = ""

    # タスク名が変わったらリセット
    if task_name.strip() != st.session_state["surge_ai_assessed_name"]:
        st.session_state["surge_ai_assessment"] = None

    assess_btn = st.button(
        "🤖 AIで未来貢献度を判定",
        disabled=not task_name.strip(),
        use_container_width=True,
    )

    if assess_btn and task_name.strip():
        with st.spinner("AIが未来への貢献度を分析中..."):
            assessment = assess_future_impact(task_name.strip(), category)
            st.session_state["surge_ai_assessment"] = assessment
            st.session_state["surge_ai_assessed_name"] = task_name.strip()
            st.rerun()

    assessment = st.session_state.get("surge_ai_assessment")
    if assessment:
        score = assessment["score"]
        reason = assessment["reason"]
        stars = "★" * score + "☆" * (5 - score)
        star_color = {1: "#888", 2: "#4A90D9", 3: "#F5A623", 4: "#FF6B35", 5: "#FF0000"}

        st.markdown(
            f'<div style="background:linear-gradient(135deg,#1a1a2e,#0d1117);'
            f'border:2px solid {star_color.get(score, "#FFD700")};border-radius:12px;padding:16px;">'
            f'<div style="text-align:center;">'
            f'<div style="font-size:0.9rem;color:#888;">AI FUTURE IMPACT ASSESSMENT</div>'
            f'<div style="font-size:2rem;color:#FFD700;letter-spacing:4px;margin:8px 0;">{stars}</div>'
            f'<div style="font-size:1.5rem;font-weight:900;color:{star_color.get(score, "#FFD700")};">'
            f'IMPACT LEVEL {score}</div>'
            f'<div style="color:#ccc;margin-top:8px;font-size:0.9rem;">💡 {reason}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        # Preview trophies
        preview_trophies = score * DURATION_OPTIONS[duration]["multiplier"]
        if category == "discovery":
            preview_trophies *= 2
        st.markdown(
            f"**獲得予定:** 🏆 +{preview_trophies} "
            f"{'(Discovery 2x!)' if category == 'discovery' else ''}"
        )

        # Register button
        if st.button("📜 契約締結 (Register Quest)", type="primary", use_container_width=True):
            task = add_task(data, task_name.strip(), category, score, duration, penalty.strip())
            st.session_state["surge_ai_assessment"] = None
            st.session_state["surge_ai_assessed_name"] = ""
            st.success(f"Quest 登録完了: {task_name} (Impact Lv.{score})")
            st.rerun()
    elif not assess_btn:
        st.info("タスク名を入力して「🤖 AIで未来貢献度を判定」を押してください。")


def _render_status_tab(data: dict):
    """Status タブ: ステータス表示"""
    profile = data["profile"]

    col1, col2 = st.columns([1, 1])

    with col1:
        _render_profile_card(data)

        # Stats
        st.markdown("**📊 Battle Record**")
        rec_cols = st.columns(3)
        rec_cols[0].metric("Cleared", profile["tasks_completed"])
        rec_cols[1].metric("Failed", profile["tasks_failed"])
        rec_cols[2].metric("Best Streak", f"🔥 {profile['streak_best']}")

    with col2:
        st.markdown("**🎯 Status Radar**")
        _render_radar_chart(data)

    # Category breakdown
    st.markdown("---")
    st.markdown("**📈 Category Stats**")
    stats = get_radar_data(data)

    stat_cols = st.columns(len(CATEGORIES))
    for i, (key, info) in enumerate(CATEGORIES.items()):
        with stat_cols[i]:
            val = stats.get(key, 0)
            st.markdown(
                f'<div style="text-align:center;">'
                f'<div style="font-size:2rem;">{info["icon"]}</div>'
                f'<div style="color:{info["color"]};font-weight:800;font-size:1.3rem;">{val}</div>'
                f'<div style="color:#888;font-size:0.8rem;">{info["label"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Trophy Road
    st.markdown("---")
    st.markdown("**🏆 Trophy Road**")
    trophies = profile["total_trophies"]
    for threshold, name, icon in LEVEL_THRESHOLDS:
        reached = trophies >= threshold
        color = "#FFD700" if reached else "#333"
        marker = "✅" if reached else "🔒"
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;padding:4px 0;">'
            f'<span style="color:{color};font-weight:800;">{marker} {icon} {name}</span>'
            f'<span style="color:#888;font-size:0.8rem;">{threshold}🏆</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_future_vision_tab(data: dict):
    """Future Vision タブ: 未来予測"""
    st.subheader("🔮 Future Vision Simulator")
    st.markdown("今の行動が、30日後の自分をどう変えるか。")

    vision = calculate_future_vision(data)

    for cat_key, v in vision.items():
        cat_info = CATEGORIES[cat_key]
        momentum_color = {"停滞": "#FF4444", "緩やか": "#FF8C00", "成長中": "#00FF88"}

        with st.expander(f"{v['icon']} {v['label']} — {v['momentum']}", expanded=True):
            col1, col2, col3 = st.columns(3)
            col1.metric("現在のステータス", v["current_stat"])
            col2.metric("今週の完了タスク", v["weekly_tasks"])
            col3.metric("30日後の予測", v["projected_30d"])

            # Momentum bar
            momentum_pct = min(100, v["weekly_tasks"] * 20)
            m_color = momentum_color.get(v["momentum"], "#888")
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;">'
                f'<span style="color:#888;font-size:0.8rem;min-width:60px;">勢い</span>'
                f'<div style="flex:1;background:#1a1a2e;border-radius:8px;height:12px;overflow:hidden;">'
                f'<div style="width:{momentum_pct}%;height:100%;background:{m_color};'
                f'border-radius:8px;"></div></div>'
                f'<span style="color:{m_color};font-weight:700;">{v["momentum"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if v["weekly_tasks"] == 0:
                st.markdown(
                    f'<div class="debuff-warning">⚠️ 今週の{v["label"]}タスク: 0件。'
                    f'このまま放置すると30日後もステータス変化なし。</div>',
                    unsafe_allow_html=True,
                )

    # Overall projection
    st.markdown("---")
    st.markdown("### 📈 30日後の総合ステータス予測")
    total_now = sum(data["profile"]["stats"].get(k, 0) for k in CATEGORIES)
    total_projected = sum(v["projected_30d"] for v in vision.values())

    col1, col2, col3 = st.columns(3)
    col1.metric("現在の総合力", total_now)
    col2.metric("30日後の予測", total_projected, delta=total_projected - total_now)

    level_now = get_level(data["profile"]["total_trophies"])
    # Rough trophy projection
    weekly_trophies = sum(
        h.get("trophies_earned", 0) for h in data["history"]
        if h.get("status") == "cleared" and h.get("completed_at")
        and datetime.fromisoformat(h["completed_at"]) > datetime.now() - timedelta(days=7)
    )
    projected_trophies = data["profile"]["total_trophies"] + weekly_trophies * 4
    projected_level = get_level(projected_trophies)
    col3.metric("30日後の予測レベル", f"Lv.{projected_level[0]} {projected_level[1]}")
