"""GitHub同期 - Streamlit CloudからデータファイルをGitHubに自動保存"""
import base64
import json
from pathlib import Path
from typing import Optional

import requests

from config import DATA_DIR


def _get_github_config() -> dict:
    """GitHub設定を取得（st.secrets → 環境変数の順）"""
    try:
        import streamlit as st
        return {
            "token": st.secrets.get("GITHUB_PAT", ""),
            "repo": st.secrets.get("GITHUB_REPO", ""),
        }
    except Exception:
        return {"token": "", "repo": ""}


def sync_file_to_github(filepath: Path, commit_message: str = "") -> bool:
    """ローカルファイルをGitHubリポジトリに同期"""
    config = _get_github_config()
    token = config["token"]
    repo = config["repo"]

    if not token or not repo:
        return False

    # data/xxx.csv → リポジトリ内の相対パス
    try:
        rel_path = filepath.relative_to(DATA_DIR.parent)
    except ValueError:
        rel_path = Path("data") / filepath.name
    repo_path = str(rel_path)

    if not commit_message:
        commit_message = f"Update {filepath.name}"

    api_url = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # 既存ファイルのSHAを取得（更新には必要）
    sha = None
    resp = requests.get(api_url, headers=headers, timeout=30)
    if resp.status_code == 200:
        sha = resp.json().get("sha")

    # ファイル内容を読み込み
    with open(filepath, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "message": commit_message,
        "content": content,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(api_url, headers=headers, json=payload, timeout=30)
    if resp.status_code in (200, 201):
        print(f"[GitHub] 同期成功: {repo_path}")
        return True
    else:
        print(f"[GitHub] 同期失敗: {resp.status_code} {resp.text[:200]}")
        return False


def sync_data_files(filenames: list) -> int:
    """複数のデータファイルをGitHubに同期"""
    config = _get_github_config()
    if not config["token"] or not config["repo"]:
        return 0

    synced = 0
    for name in filenames:
        path = DATA_DIR / name
        if path.exists():
            if sync_file_to_github(path, f"Auto-update {name}"):
                synced += 1
    return synced


def is_cloud_environment() -> bool:
    """Streamlit Cloud上で動作しているか判定"""
    config = _get_github_config()
    return bool(config["token"] and config["repo"])
