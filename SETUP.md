# 池上教習所 空き通知システム セットアップガイド

## 全体の流れ

1. GitHubにリポジトリを作る
2. LINE Messaging API を設定する
3. GitHub Secrets に認証情報を登録する
4. 動作確認する

---

## STEP 1：GitHub リポジトリの作成

1. https://github.com にアクセスしてアカウントを作成（または既存アカウントでログイン）
2. 右上の「+」→「New repository」をクリック
3. 以下の設定でリポジトリを作成：
   - Repository name: `ikegami-slot-checker`（任意）
   - **Private**（公開したくない場合はPrivateを選択）
   - 「Create repository」をクリック

4. このフォルダ内のファイルを全部アップロード：
   - `check_slots.py`
   - `requirements.txt`
   - `.github/workflows/check.yml`

   → GitHub の画面で「uploading an existing file」リンクからドラッグ＆ドロップでOK

---

## STEP 2：LINE Messaging API の設定

### 2-1. LINE Developers でチャネルを作成

1. https://developers.line.biz/ja/ にアクセスしてLINEアカウントでログイン
2. 「Providers」→「Create a new provider」
   - Provider name: 「池上通知」など（なんでもOK）
3. 「Create a new channel」→「Messaging API」を選択
4. 以下を入力して作成：
   - Channel name: 「池上空き通知」
   - Channel description: 適当なテキスト
   - Category / Subcategory: 適当に選ぶ

### 2-2. チャネルアクセストークンを取得

1. 作成したチャネルの「Messaging API」タブを開く
2. 一番下の「Channel access token」→「Issue」ボタンをクリック
3. 表示されたトークン（長い文字列）をコピーして保存しておく
   → これが `LINE_CHANNEL_ACCESS_TOKEN`

### 2-3. 自分のLINE User ID を取得

1. 同じページの「Basic settings」タブを開く
2. 「Your user ID」欄に `Uxxxxxxxxxxxxx` という文字列がある
   → これが `LINE_USER_ID`

### 2-4. ボットを友達追加する

1. 「Messaging API」タブの QR コードをスマホで読み取り
2. ボットを友達追加する（これをしないと通知が届かない）

---

## STEP 3：GitHub Secrets に登録

GitHubのリポジトリページで：「Settings」→「Secrets and variables」→「Actions」→「New repository secret」

| Secret名 | 値 |
|---|---|
| `ELICENSE_LOGIN_ID` | e-licenseのログインID（学籍番号） |
| `ELICENSE_PASSWORD` | e-licenseのパスワード |
| `LINE_CHANNEL_ACCESS_TOKEN` | STEP 2-2 で取得したトークン |
| `LINE_USER_ID` | STEP 2-3 で取得したユーザーID |

---

## STEP 4：動作確認

1. GitHubのリポジトリ →「Actions」タブを開く
2. 左の「池上教習所 空き枠チェック」をクリック
3. 右上の「Run workflow」→「Run workflow」をクリック（手動実行）
4. ログが流れて `空き枠をチェックして通知` のステップが緑なら成功
5. 空きがあればLINEに通知が届く

---

## 注意事項

- **GitHub Actions 無料枠**：月2,000分（プライベートリポジトリ）。
  30分毎 × 約1分/回 = 月約1,440分なので無料枠内に収まります。
- **LINE Messaging API 無料枠**：月200通。空きが出たらすぐ予約する想定であれば十分です。
- ログイン情報は GitHub Secrets に暗号化して保存されます。外部には漏れません。
