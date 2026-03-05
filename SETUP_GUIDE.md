# Instagram API セットアップガイド

## 前提条件
- Instagramプロアカウント or クリエイターアカウント（@k_slf_imp）
- Facebookページとの連携済み

---

## ステップ1: Facebookページの作成・連携

### Facebookページの作成（まだない場合）
1. Facebook にログイン
2. 左メニュー「ページ」→「新しいページを作成」
3. ページ名を入力して作成

### InstagramアカウントとFacebookページの連携
1. **Instagramアプリ** → プロフィール → 設定
2. 「アカウント」→「リンク済みのアカウント」→「Facebook」
3. Facebookページを選択して連携

---

## ステップ2: Meta開発者アカウント作成

1. https://developers.facebook.com/ にアクセス
2. 「スタートガイド」をクリック
3. Facebookアカウントでログイン
4. 開発者登録を完了

---

## ステップ3: Metaアプリ作成

1. https://developers.facebook.com/apps/ にアクセス
2. 「アプリを作成」をクリック
3. **ユースケース**: 「その他」を選択
4. **アプリタイプ**: 「ビジネス」を選択
5. アプリ名を入力（例: 「SNS分析ツール」）
6. 作成完了

---

## ステップ4: Instagram Graph API を追加

1. アプリダッシュボード → 左メニュー「製品を追加」
2. 「Instagram Graph API」を見つけて「設定」をクリック
3. セットアップ完了

---

## ステップ5: アクセストークン取得

### 方法A: Graph API Explorer（推奨・簡単）

1. https://developers.facebook.com/tools/explorer/ にアクセス
2. 右上で作成したアプリを選択
3. 「ユーザーアクセストークンを生成」をクリック
4. 以下のパーミッションを選択:
   - `instagram_basic`
   - `instagram_manage_insights`
   - `pages_show_list`
   - `pages_read_engagement`
   - `business_management`
5. 「Generate Access Token」をクリック
6. Facebookログイン → 権限を許可
7. 表示されたトークンをコピー

### 短期トークン → 長期トークンへ変換

短期トークン（1時間）を長期トークン（60日）に変換:

```bash
# プロジェクトディレクトリで実行
cd ~/sns-analytics
source venv/bin/activate
python3 -c "
from config import refresh_token, save_initial_token
# ↓ Graph API Explorer で取得した短期トークンを貼り付け
SHORT_TOKEN = 'ここに短期トークンを貼り付け'
save_initial_token(SHORT_TOKEN)
"
```

※ もしくは `.env` に直接記入して `config.py` の自動リフレッシュ機能に任せる

---

## ステップ6: ユーザーID取得

### Graph API Explorer で取得
1. Graph API Explorer で `me/accounts` を実行
2. レスポンスからFacebookページのIDを取得
3. 次に `{ページID}?fields=instagram_business_account` を実行
4. 返ってきた `instagram_business_account.id` がInstagramユーザーID

### もしくはcurlで取得
```bash
# ページ一覧取得
curl "https://graph.facebook.com/v21.0/me/accounts?access_token=YOUR_TOKEN"

# ページIDからInstagramビジネスアカウントID取得
curl "https://graph.facebook.com/v21.0/{PAGE_ID}?fields=instagram_business_account&access_token=YOUR_TOKEN"
```

---

## ステップ7: .env ファイル設定

```bash
cd ~/sns-analytics
cp .env.example .env
```

`.env` を編集:
```
INSTAGRAM_ACCESS_TOKEN=取得した長期トークン
INSTAGRAM_USER_ID=取得したInstagramユーザーID
INSTAGRAM_APP_ID=アプリダッシュボードのアプリID
INSTAGRAM_APP_SECRET=アプリダッシュボードのアプリシークレット
```

**アプリIDとシークレットの場所:**
- アプリダッシュボード → 設定 → ベーシック

---

## ステップ8: 動作確認

```bash
cd ~/sns-analytics
source venv/bin/activate

# データ取得テスト
python instagram/fetch.py

# 分析実行
python instagram/analyze.py

# ダッシュボード起動
streamlit run dashboard.py
```

---

## トラブルシューティング

### 「Invalid OAuth access token」エラー
- トークンの有効期限切れ → Graph API Explorer で再取得
- コピー時に余計な空白が含まれていないか確認

### 「Unsupported get request」エラー
- ユーザーIDが正しいか確認（FacebookページIDではなく、InstagramビジネスアカウントID）
- パーミッションが正しく付与されているか確認

### インサイトが取得できない
- プロ/クリエイターアカウントでないと取得不可
- 投稿後24時間以上経過している必要がある場合あり

### トークン自動リフレッシュについて
- 長期トークンは60日有効
- `config.py` の `get_access_token()` が残り7日を切ると自動リフレッシュ
- `INSTAGRAM_APP_ID` と `INSTAGRAM_APP_SECRET` が必要
