# AgentCore Memory インタラクティブデモ

このスクリプトは、AgentCore Memoryの短期記憶と長期記憶を**複数回のコマンド実行**で体験するためのデモです。

## 概要

既存の `test_memory_ja.py` は1回の実行で全ステップが自動実行されますが、`test_memory2_ja.py` では受講者が自分のペースで1ステップずつ実行し、メモリの効果を実感できます。

## 使い方

### Step 1: 1つ目の見積もり（短期記憶に保存）

```bash
cd /workshop/03_memory
uv run python test_memory2_ja.py estimate "EC2 t3.microインスタンス1台を24時間稼働"
```

エージェントがコスト見積もりを実行し、結果を**短期記憶**に保存します（`create_event`）。

### Step 2: 2つ目の見積もり（短期記憶に追加）

```bash
uv run python test_memory2_ja.py estimate "S3バケット100GBストレージ"
```

同じセッション内で2つ目の見積もりが短期記憶に追加されます。

### Step 3: 比較（短期記憶から取得）

```bash
uv run python test_memory2_ja.py compare
```

短期記憶から過去の見積もりを取得し（`list_events`）、比較結果を生成します。
ここで「さっき入力した2つの見積もりを覚えている」ことが確認できます。

### Step 4: 提案（長期記憶から検索）

```bash
uv run python test_memory2_ja.py propose
```

長期記憶からユーザーの嗜好を検索し（`retrieve_memories`）、パーソナライズされた提案を生成します。

> **注意**: 長期記憶の抽出はバックグラウンドで非同期に行われるため、Step 2の直後に実行すると「長期記憶が見つからない」場合があります。数分待ってから実行してください。

## セッション管理

### セッションの継続

デフォルトでは、前回のセッションIDが `.session_id` ファイルに保存され、次回実行時に自動的に再利用されます。これにより、複数回の実行で同じ短期記憶にアクセスできます。

### 新しいセッションを開始

短期記憶をリセットして新しいセッションを開始する場合:

```bash
uv run python test_memory2_ja.py estimate "新しい見積もり" --new-session
```

### メモリを完全にリセット

長期記憶も含めて完全にリセットする場合:

```bash
uv run python test_memory2_ja.py estimate "見積もり" --force
```

## 体験のポイント

### 短期記憶の体験（Step 1〜3）

- Step 1とStep 2で入力した内容を、Step 3の比較で「覚えている」ことを確認
- 同じセッションID内でのみ有効（`--new-session` でリセットされる）

### 長期記憶の体験（Step 4）

- Step 1〜2で入力したアーキテクチャの傾向（小規模、特定リージョン等）を学習
- セッションを超えて保持される（`--new-session` でもリセットされない）
- `--force` でのみリセットされる

## Memory APIの対応

| コマンド | Memory API | 記憶の種類 |
|---------|-----------|-----------|
| `estimate` | `create_event()` | 短期記憶に保存 |
| `compare` | `list_events()` | 短期記憶から取得 |
| `propose` | `retrieve_memories()` | 長期記憶から検索 |

## 参考

- 全ステップを自動実行する場合は `test_memory_ja.py` を使用してください
- AgentCore Memory ドキュメント: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html
