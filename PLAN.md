# Teams Mention Aggregator - Implementation Plan

## Context
複数の別組織ノートPC上のTeamsメンション通知を、代表PC1台に集約表示するシステム。
各PCはネットワーク分離されているため、インターネット上のリレーサーバを経由して通知を転送する。

## Architecture

```
                                                         ┌── HTTPS GET ── [代表PC Collector (Tkinter)]
[PC-A 組織X] ──HTTPS POST──┐                             │
[PC-B 組織Y] ──HTTPS POST──┼──→ Cloudflare Workers + KV ─┤
[PC-C 組織Z] ──HTTPS POST──┘       (リレーサーバ)         │
[PC-D 組織W] ──HTTPS POST──┘       + PWA配信             └── HTTPS GET ── [スマートフォン (PWA)]
```

4コンポーネント: Relay Server (TypeScript), Agent (Python), Collector (Python+Tkinter), PWA (HTML/JS)

## Project Structure

```
teams_mention_to_email/
├── relay-server/
│   ├── src/
│   │   ├── index.ts          # Worker: ルーティング、認証、KV操作、PWA配信
│   │   └── pwa.ts            # PWA: HTML/JS/CSS、manifest、Service Worker
│   ├── wrangler.toml         # Cloudflare設定
│   ├── tsconfig.json
│   └── package.json
├── agent/
│   ├── agent.py              # メインエントリポイント
│   ├── notification_listener.py  # Windows通知監視 (WinRT)
│   ├── relay_client.py       # HTTPクライアント (POST、リトライ、ローカルキュー)
│   └── config.py             # TOML設定読み込み
├── collector/
│   ├── collector.py          # メインエントリポイント
│   ├── ui.py                 # Tkinter UI (Treeview一覧、フィルタ、ポーリング)
│   ├── tray.py               # システムトレイ (pystray)
│   ├── relay_client.py       # HTTPクライアント (GET、PATCH)
│   └── config.py             # TOML設定読み込み
├── config.example.toml       # 設定テンプレート
└── requirements.txt          # Python依存パッケージ
```

## Implementation Steps

### Step 1: プロジェクト基盤
- `config.example.toml` 作成 (全設定項目のテンプレート)
- `requirements.txt` 作成
- ディレクトリ構成作成

### Step 2: Relay Server (Cloudflare Workers + KV)
- `relay-server/` をCloudflare Workers projectとして初期化
- `src/index.ts` に以下のAPIを実装:
  - `POST /api/notifications` — Agent→通知送信。KVに保存 (`expirationTtl: 86400` で24h自動削除)
  - `GET /api/notifications` — Collector→通知取得。`since`, `status`, `pc_name` でフィルタ
  - `PATCH /api/notifications/:id` — 既読化
- 認証: `Authorization: Bearer <API_KEY>` ヘッダ
- KVキー形式: `notif:{timestamp_ms}:{uuid}` (時系列ソート可能)
- 逆引きインデックス: `idx:{uuid}` → KVキー名 (PATCH用)
- メッセージプレビューはサーバ側でも80文字に切り詰め

### Step 3: Agent設定・HTTPクライアント
- `agent/config.py` — TOML読み込み (`tomllib`)
- `agent/relay_client.py` — POST送信、指数バックオフリトライ、インメモリ再送キュー

### Step 4: Agent通知リスナー
- `agent/notification_listener.py` — WinRT `UserNotificationListener` を使用
  - `request_access_async()` で通知アクセス許可を取得
  - `get_notifications_async(NotificationKinds.TOAST)` でトースト通知をポーリング (3秒間隔)
  - Teams AppId でフィルタ (`MSTeams_8wekyb3d8bbwe!MSTeams` + `com.squirrel.Teams.Teams`)
  - トーストバインディングからテキスト要素を抽出 (送信者名、チャネル、メッセージ)
  - `seen_ids` セットで重複検知を防止

### Step 5: Agentメインループ
- `agent/agent.py` — 通知リスナー + リレークライアントを結合
- `--install` / `--uninstall` フラグでWindows起動時自動実行を登録
- `pythonw.exe` でコンソールウィンドウなし実行
- ログ: `%APPDATA%/teams-mention-agent/agent.log` (RotatingFileHandler)

### Step 6: Collector HTTPクライアント
- `collector/config.py` — TOML読み込み
- `collector/relay_client.py` — GET (ポーリング) + PATCH (既読化)

### Step 7: Collectorシステムトレイ
- `collector/tray.py` — `pystray` でトレイアイコン
  - 未読あり=赤丸、未読なし=灰色丸 (PIL.ImageDrawで動的生成)
  - 右クリックメニュー: 表示 / 設定 / 終了

### Step 8: Collector UI
- `collector/ui.py` — Tkinter メインウィンドウ
  - `ttk.Treeview` で通知一覧 (PC名, 送信者, チャネル, プレビュー, 時刻, 状態)
  - フィルタバー: PC別、未読/全件
  - ポーリング: バックグラウンドスレッド + `queue.Queue` + `root.after()` パターン
  - 行クリックで既読化
  - 新着時に `win11toast` でトースト通知 + `winsound` で通知音
  - ウィンドウ閉じる→トレイに最小化

### Step 9: Collector統合
- `collector/collector.py` — 全コンポーネントを結合

### Step 10: PWA (スマートフォン対応)
- `relay-server/src/pwa.ts` — Worker内にインラインでHTML/JS/CSSを保持
  - モバイルファーストのダークテーマUI
  - カード形式の通知一覧 (PC名バッジ、送信者、チャネル、メッセージ、時刻)
  - フィルタ: PC別、未読/全件
  - タップで既読化 (PATCH API)
  - 10秒間隔のポーリング
  - 初回アクセス時にAPIキーをプロンプト入力 → `localStorage` に保存
  - Web Notification API でブラウザ通知 (iOS 16.4+, Android対応)
  - `manifest.json` + Service Worker でホーム画面追加可能 (PWA)
- `relay-server/src/index.ts` — PWA静的ルート (`/`, `/manifest.json`, `/sw.js`, `/icon-*.png`) は認証不要
- Agent / Collector の既存コードは変更なし

### Step 11: 仕上げ
- エラーハンドリング全体見直し
- `--discover-apps` CLIフラグ (全通知アプリIDを列挙するデバッグ用)

## Key Technical Details

- **WinRT通知監視**: プッシュベースのコールバックはPythonバインディングにないため、2-3秒間隔のポーリング方式
- **クラムシェルモード**: ユーザセッションがアクティブであれば通知は到着し続ける。Teams通知は通知センターに蓄積されるためポーリングで取得可能
- **KV自動削除**: `expirationTtl: 86400` で24h後に自動消去。CronTrigger不要
- **プロキシ対応**: `requests` ライブラリの `proxies` パラメータで企業プロキシに対応
- **PWA**: Worker内にHTML/JS/CSSをインラインで保持し静的ファイルホスティング不要。APIキーはクライアント側 `localStorage` に保存し、`Authorization` ヘッダで送信。PWA静的ルートは認証不要、API呼び出しはBearer認証必須

## Verification
1. Relay Server: `wrangler dev` でローカルテスト → `curl` でPOST/GET/PATCH確認
2. Agent: 実機でTeamsメッセージ送信 → リレーサーバに通知が到達するか確認
3. Collector: リレーサーバにテストデータ投入 → UI表示・既読化・トースト通知を確認
4. PWA: スマートフォンのブラウザでリレーサーバURLにアクセス → APIキー入力 → 通知一覧・既読化・ブラウザ通知を確認 → ホーム画面に追加してPWA動作を確認
5. E2E: Agent (PC-A) + Collector (代表PC) or PWA (スマートフォン) で実際のTeamsメンションが集約されるか確認
