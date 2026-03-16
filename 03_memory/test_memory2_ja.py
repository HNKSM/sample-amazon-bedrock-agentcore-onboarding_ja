#!/usr/bin/env python3
"""
AgentCore Memory インタラクティブデモ

コマンドライン引数でモードを切り替えて、短期記憶・長期記憶を体験するスクリプト。
test_memory_ja.pyのAgentWithMemoryクラスを再利用します。

使用例:
  # Step 1: 見積もり（短期記憶に保存）
  uv run python test_memory2_ja.py estimate "EC2 t3.microインスタンス1台"

  # Step 2: 別の見積もり（短期記憶に追加）
  uv run python test_memory2_ja.py estimate "S3バケット100GB"

  # Step 3: 比較（短期記憶から取得 → 記憶していることを確認）
  uv run python test_memory2_ja.py compare

  # Step 4: 提案（長期記憶から嗜好を検索 → 学習していることを確認）
  uv run python test_memory2_ja.py propose

  # セッションをリセットしたい場合
  uv run python test_memory2_ja.py estimate "新しい見積もり" --new-session

  # メモリを完全に再作成したい場合
  uv run python test_memory2_ja.py estimate "見積もり" --force
"""

import argparse
import logging
import json
from pathlib import Path
from test_memory_ja import AgentWithMemory

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

SESSION_FILE = Path(".session_id")


def load_session_id() -> str:
    """保存されたセッションIDを読み込む"""
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return ""


def save_session_id(session_id: str):
    """セッションIDをファイルに保存"""
    SESSION_FILE.write_text(session_id)


def main():
    parser = argparse.ArgumentParser(
        description="AgentCore Memory インタラクティブデモ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  uv run python test_memory2_ja.py estimate "EC2 t3.microインスタンス1台"
  uv run python test_memory2_ja.py estimate "S3バケット100GB"
  uv run python test_memory2_ja.py compare
  uv run python test_memory2_ja.py propose
  uv run python test_memory2_ja.py estimate "新しい見積もり" --new-session
        """
    )
    parser.add_argument(
        'mode',
        choices=['estimate', 'compare', 'propose'],
        help='実行モード: estimate=見積もり, compare=比較, propose=提案'
    )
    parser.add_argument(
        'description',
        nargs='?',
        default='',
        help='見積もり対象のアーキテクチャ説明（estimateモード時に必要）'
    )
    parser.add_argument(
        '--new-session',
        action='store_true',
        help='新しいセッションを開始（短期記憶をリセット）'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='メモリを完全に再作成（長期記憶もリセット）'
    )

    args = parser.parse_args()

    if args.mode == 'estimate' and not args.description:
        parser.error("estimateモードではアーキテクチャの説明が必要です")

    print("=" * 60)
    print("🧠 AgentCore Memory インタラクティブデモ")
    print("=" * 60)

    memory_agent = AgentWithMemory(
        actor_id="user123",
        force_recreate=args.force
    )

    # セッションIDの管理
    if args.new_session or args.force:
        print("🔄 新しいセッションを開始します")
    else:
        saved_session = load_session_id()
        if saved_session:
            memory_agent.session_id = saved_session
            print(f"📎 既存セッションを再利用: {saved_session}")

    # セッションIDを保存
    save_session_id(memory_agent.session_id)

    with memory_agent as agent:
        if args.mode == 'estimate':
            print(f"\n📝 見積もり: {args.description}")
            print("   → 短期記憶に保存されます（create_event）")
            print("-" * 60)
            result = agent(f"見積もりしてください: {args.description}")
            result_text = result.message["content"] if result.message else ""
            print(f"\n{result_text}")
            print("\n✅ 見積もりが短期記憶に保存されました")
            print("💡 次のコマンドで別の見積もりを追加できます:")
            print('   uv run python test_memory2_ja.py estimate "別のアーキテクチャ"')

        elif args.mode == 'compare':
            print("\n📊 短期記憶から見積もりを取得して比較します（list_events）")
            print("-" * 60)
            result = agent("これまでの見積もりを比較してください")
            result_text = result.message["content"] if result.message else ""
            print(f"\n{result_text}")
            if not result_text:
                print("⚠️ 比較する見積もりがありません。先にestimateを実行してください。")

        elif args.mode == 'propose':
            print("\n💡 長期記憶からユーザーの嗜好を検索して提案します（retrieve_memories）")
            print("   ※ 長期記憶の抽出には時間がかかる場合があります")
            print("-" * 60)
            result = agent("私の好みに基づいて最適なアーキテクチャを提案してください")
            result_text = result.message["content"] if result.message else ""
            print(f"\n{result_text}")

    print("\n" + "=" * 60)
    print(f"セッションID: {memory_agent.session_id}")
    print("=" * 60)


if __name__ == "__main__":
    main()
