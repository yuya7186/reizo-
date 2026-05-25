# 冷蔵庫・食材庫 在庫管理アプリ（reizo）進捗メモ

最終更新: 2026-05-26

---

## アプリ概要

中高生ユニットの職員が冷蔵庫・食材庫の在庫を共有・管理するWebアプリ。  
スマホからPWA（ホーム画面アイコン）として使える。

---

## アクセス情報

| 項目 | 内容 |
|---|---|
| 本番URL | https://web-production-a37241.up.railway.app |
| GitHubリポジトリ | https://github.com/yuya7186/reizo- |
| ローカル起動 | `cd ~/Desktop/claudecode/reizo && python3 app.py` → http://localhost:5002 |

---

## ログイン情報

| ID | パスワード | 権限 |
|---|---|---|
| admin | admin1234 | 管理者（スタッフ管理・保管場所管理） |
| staff1 | pass1234 | スタッフ |
| staff2 | pass1234 | スタッフ |
| staff3 | pass1234 | スタッフ |

> ⚠️ 実運用前に管理者アカウントで各職員のアカウントを作成し、staff1〜3は削除推奨

---

## 保管場所（初期設定）

- 冷蔵庫① 🧊
- 冷蔵庫② 🧊
- 冷蔵庫③ 🧊
- 食材庫 📦

管理者画面（⚙️ボタン）から追加・削除可能。

---

## 実装済み機能

- [x] ログイン（ID・パスワード認証）
- [x] 2ロール制（管理者 / スタッフ）
- [x] 在庫一覧・追加・編集・削除
- [x] 写真撮影 → Claude AI自動認識（claude-3-5-sonnet-20241022）
- [x] 必需品リスト（各保管場所ごとに登録）
- [x] 不足品目の自動検出・表示
- [x] 買い物リスト（不足品 + 残り少ない品目を自動表示）
- [x] 「残り少ない」⚠️フラグ機能（在庫画面でボタン1タップ）
- [x] ホーム画面に不足・残り少バッジ表示
- [x] PWA対応（ホーム画面に追加してアプリとして使える）
- [x] 管理者画面（スタッフ追加・削除・PW変更 / 保管場所追加・削除）
- [x] 時刻を日本時間（JST）で表示

---

## 技術構成

| 項目 | 内容 |
|---|---|
| バックエンド | Python / Flask |
| データベース | PostgreSQL（Railway） / SQLite（ローカル） |
| フロントエンド | Bootstrap5 / PWA |
| AI認識 | Anthropic API（claude-3-5-sonnet-20241022） |
| ホスティング | Railway |
| バージョン管理 | GitHub（yuya7186/reizo-） |

---

## 環境変数（Railway）

| キー | 内容 |
|---|---|
| ANTHROPIC_API_KEY | AnthropicのAPIキー |
| DATABASE_URL | RailwayのPostgreSQL接続URL（自動設定） |
| SECRET_KEY | reizo-secret-2026 |

---

## スマホへの入れ方

### iPhone（Safari限定）
1. Safariで本番URLを開く
2. 下の共有ボタン（□↑）をタップ
3. 「ホーム画面に追加」→「追加」

### Android（Chrome）
1. ChromeでURLを開く
2. 右上「⋮」→「ホーム画面に追加」

---

## 今後の課題・検討事項

- [ ] 各職員の実名アカウントに切り替え（管理者画面から作業）
- [ ] パスワードを各職員が自分で変更できる機能
- [ ] 写真認識の精度検証・プロンプト調整
- [ ] データのバックアップ方針
- [ ] 小遣い帳アプリ（kozukai）との将来的な一本化

---

## ローカル開発の起動方法

```bash
cd ~/Desktop/claudecode/reizo
python3 app.py
# → http://localhost:5002
```

## デプロイ方法

```bash
cd ~/Desktop/claudecode/reizo
git add -A
git commit -m "変更内容"
git push
# RailwayがGitHubと連携して自動デプロイ（1〜2分）
```
