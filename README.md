# Teams Mention Aggregator

複数の別組織PC上のTeamsメンション通知を、代表PCまたはスマートフォンに集約表示するシステム。

```
                                                         ┌── HTTPS GET ── [代表PC Collector (Tkinter)]
[PC-A 組織X] ──HTTPS POST──┐                             │
[PC-B 組織Y] ──HTTPS POST──┼──→ Cloudflare Workers + KV ─┤
[PC-C 組織Z] ──HTTPS POST──┘       (リレーサーバ)         │
                                    + PWA配信             └── HTTPS GET ── [スマートフォン (PWA)]
```

## 構成

| コンポーネント | 言語 | 説明 |
|---|---|---|
| **Relay Server** | TypeScript | Cloudflare Workers + KV。通知の中継・保存 (24h自動削除) + PWA配信 |
| **Agent** | Python | 各PCで動作。Teamsの通知を監視しリレーサーバへ送信 |
| **Collector** | Python + Tkinter | 代表PCで動作。リレーサーバから通知を取得しGUI表示 |
| **PWA** | HTML/JS/CSS | スマートフォンのブラウザで動作。Collector の代替 |

Collector (Windows PC) と PWA (スマートフォン) は併用可能。用途に応じて片方のみでもよい。

## 前提条件

- **Relay Server**: Node.js 18+, Cloudflareアカウント
- **Agent**: Python 3.11+, Windows 10/11
- **Collector**: Python 3.11+, Windows 10/11
- **PWA**: iOS 16.4+ / Android のモダンブラウザ (Safari, Chrome)
- Agent を動かすPCでは「通知とアクション」設定で通知アクセスを許可しておくこと

## セットアップ

### 1. Cloudflare アカウント準備

1. [Cloudflare ダッシュボード](https://dash.cloudflare.com/sign-up) でアカウントを作成 (無料プランで可)
2. ダッシュボード左メニューの **Compute** → **Workers & Pages** を開き、Workers のサブドメイン (`<subdomain>.workers.dev`) を設定する

### 2. Relay Server (Cloudflare Workers)

```bash
cd relay-server
npm install
```

`wrangler.example.toml` をコピーして `wrangler.toml` を作成:

```bash
cp wrangler.example.toml wrangler.toml
```

Cloudflare にログイン (ブラウザが開くので認証する):

```bash
npx wrangler login
```

KV名前空間を作成し、`wrangler.toml` の `id` を更新する:

```bash
npx wrangler kv namespace create NOTIFICATIONS
# 出力された id を wrangler.toml に貼り付け
```

APIキーをシークレットとして設定:

```bash
npx wrangler secret put API_KEY
# プロンプトに任意の文字列を入力
```

ローカルで動作確認:

```bash
npm run dev
```

デプロイ:

```bash
npm run deploy
```

デプロイ後のURLが `https://teams-mention-relay.<subdomain>.workers.dev` のような形式で表示される。

### 3. 設定ファイル

`config.example.toml` をコピーして `config.toml` を作成:

```bash
cp config.example.toml config.toml
```

`config.toml` を編集:

```toml
[relay]
url = "https://teams-mention-relay.<subdomain>.workers.dev"
api_key = "上で設定したAPIキーと同じ値"

[agent]
pc_name = "PC-A"       # このPCの識別名 (PC毎に変える)

[collector]
poll_interval = 10     # ポーリング間隔 (秒)
```

Agent用PC、Collector用PCそれぞれに `config.toml` を配置する。

### 4. Python依存パッケージ

```bash
pip install -r requirements.txt
```

> **Agent のみ使うPC**: `pystray`, `Pillow`, `win11toast` は不要。
> **Collector のみ使うPC**: `winsdk` は不要。

### 5. Agent (通知監視側PC)

```bash
cd agent
python agent.py
```

バックグラウンドで動作させる場合:

```bash
pythonw agent.py
```

Windows起動時に自動実行する:

```bash
python agent.py --install
```

自動実行を解除する:

```bash
python agent.py --uninstall
```

### 6. Collector (集約表示PC — Windows)

```bash
cd collector
python collector.py
```

起動するとTkinterウィンドウとシステムトレイアイコンが表示される。

### 7. PWA (集約表示 — スマートフォン)

Collector の代わりにスマートフォンで通知を確認する場合。追加のインストールは不要。

1. スマートフォンのブラウザでリレーサーバのURLを開く:
   ```
   https://teams-mention-relay.<subdomain>.workers.dev
   ```
2. 初回アクセス時にAPIキーの入力を求められるので、`config.toml` と同じ値を入力
3. 通知の一覧が表示される

**ホーム画面に追加 (推奨):**
- **iOS**: Safari で開く → 共有ボタン → 「ホーム画面に追加」
- **Android**: Chrome で開く → メニュー → 「ホーム画面に追加」

ホーム画面から起動するとフルスクリーンのアプリとして動作する (PWA)。

**ブラウザ通知:**
- 初回アクセス時に通知許可を求められる。許可すると新着メンション時にブラウザ通知が表示される
- iOS では Safari 16.4 以降 + ホーム画面に追加した状態で動作

## 使い方

### Collector UI (Windows)

- **通知一覧**: PC名、送信者、チャネル、メッセージプレビュー、時刻、状態を表示
- **フィルタ**: 上部のドロップダウンでPC別に絞り込み。「未読のみ」チェックボックスで切り替え
- **既読化**: 行をクリックすると既読になる
- **新着通知**: 未読の新着があるとトースト通知とサウンドで通知
- **トレイアイコン**: 未読ありで赤丸、なしで灰色丸。右クリックで「表示」「終了」
- **ウィンドウを閉じる**: トレイに最小化される (終了はトレイの右クリックメニューから)

### PWA (スマートフォン)

- **通知一覧**: カード形式で PC名バッジ、送信者、チャネル、メッセージ、時刻を表示
- **フィルタ**: PC別ドロップダウン、未読/全件ボタンで切り替え
- **既読化**: カードをタップすると既読になる
- **新着通知**: ブラウザ通知で新着を表示 (通知許可が必要)
- **未読バッジ**: ヘッダに未読件数を表示
- **APIキー変更**: ブラウザの `localStorage` をクリアして再読み込み

### デバッグ

通知のAppIDを確認する (Agentで使用するTeams AppIDの特定に便利):

```bash
cd agent
python agent.py --discover-apps
```

### ログ

- Agent: `%APPDATA%\teams-mention-agent\agent.log`
- Collector: `%APPDATA%\teams-mention-collector\collector.log`

## API リファレンス

すべてのリクエストに `Authorization: Bearer <API_KEY>` ヘッダが必要。

### POST /api/notifications

通知を送信する (Agent → Relay)。

```json
{
  "pc_name": "PC-A",
  "sender": "山田太郎",
  "channel": "プロジェクトX - General",
  "message": "メンションのプレビューテキスト"
}
```

### GET /api/notifications

通知を取得する (Collector → Relay)。

| パラメータ | 説明 |
|---|---|
| `since` | ISO 8601タイムスタンプ。これ以降の通知のみ返す |
| `status` | `unread` または `read` |
| `pc_name` | PC名で絞り込み |

### PATCH /api/notifications/:id

通知を既読にする。

## プロキシ設定

企業プロキシ環境では `config.toml` に以下を追加:

```toml
[proxy]
http = "http://proxy.example.com:8080"
https = "http://proxy.example.com:8080"
```
