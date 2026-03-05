#!/usr/bin/env python3
"""
ハンズオン生成ファイルのクリーンアップスクリプト

ハンズオンで生成されたファイル・ディレクトリを削除し、
日本語化されたPythonファイル（*_ja.py）は保持します。
"""

import os
import shutil
from pathlib import Path

# クリーンアップ対象のディレクトリ
TARGET_DIRS = [
    "01_code_interpreter",
    "02_runtime",
    "03_memory",
    "04_observability",
]

# 削除対象のパターン
PATTERNS_TO_DELETE = [
    "__pycache__",  # Pythonキャッシュ
    ".bedrock_agentcore",  # AgentCore設定
    ".bedrock_agentcore.yaml",  # AgentCore設定ファイル
    "deployment",  # デプロイメントディレクトリ（02_runtimeのみ）
]

# 保持するファイルパターン
KEEP_PATTERNS = [
    "_ja.py",  # 日本語化されたPythonファイル
    "README",  # READMEファイル
    ".gitignore",  # Git設定
]


def should_keep(path: Path) -> bool:
    """ファイル/ディレクトリを保持すべきか判定"""
    name = path.name
    
    # 保持パターンに一致するか確認
    for pattern in KEEP_PATTERNS:
        if pattern in name:
            return True
    
    # 元のソースファイルは保持
    if path.is_file() and path.suffix == ".py" and not name.endswith("_ja.py"):
        # オリジナルのPythonファイルは保持
        return True
    
    return False


def clean_directory(base_path: Path, dir_name: str):
    """指定ディレクトリをクリーンアップ"""
    dir_path = base_path / dir_name
    
    if not dir_path.exists():
        print(f"⏭️  スキップ: {dir_name} (存在しません)")
        return
    
    print(f"\n🔍 クリーンアップ中: {dir_name}")
    deleted_count = 0
    kept_count = 0
    
    # __pycache__ディレクトリを削除
    for pycache in dir_path.rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache)
            print(f"  ✅ 削除: {pycache.relative_to(dir_path)}")
            deleted_count += 1
    
    # .bedrock_agentcoreディレクトリを削除
    bedrock_dir = dir_path / ".bedrock_agentcore"
    if bedrock_dir.exists():
        shutil.rmtree(bedrock_dir)
        print(f"  ✅ 削除: .bedrock_agentcore/")
        deleted_count += 1
    
    # .bedrock_agentcore.yamlファイルを削除
    yaml_file = dir_path / ".bedrock_agentcore.yaml"
    if yaml_file.exists():
        yaml_file.unlink()
        print(f"  ✅ 削除: .bedrock_agentcore.yaml")
        deleted_count += 1
    
    # 02_runtimeの特別処理: deploymentディレクトリ内の生成ファイルを削除
    if dir_name == "02_runtime":
        deployment_dir = dir_path / "deployment"
        if deployment_dir.exists():
            # deployment内の生成されたファイルを削除（オリジナルと日本語版は保持）
            for item in deployment_dir.iterdir():
                if item.is_dir():
                    # cost_estimator_agentなどのコピーされたディレクトリを削除
                    if item.name not in ["__pycache__"]:
                        shutil.rmtree(item)
                        print(f"  ✅ 削除: deployment/{item.name}/")
                        deleted_count += 1
                elif item.is_file():
                    # requirements.txtなどの生成ファイルを削除（オリジナルと_ja.pyは保持）
                    if not should_keep(item):
                        item.unlink()
                        print(f"  ✅ 削除: deployment/{item.name}")
                        deleted_count += 1
                    else:
                        kept_count += 1
    
    # 保持されたファイルをカウント
    for item in dir_path.rglob("*_ja.py"):
        if item.is_file():
            kept_count += 1
    
    print(f"  📊 削除: {deleted_count}件, 保持: {kept_count}件の日本語ファイル")


def main():
    """メイン処理"""
    print("=" * 60)
    print("🧹 ハンズオン生成ファイルのクリーンアップ")
    print("=" * 60)
    print("\n📝 以下を削除します:")
    print("  - __pycache__/ (Pythonキャッシュ)")
    print("  - .bedrock_agentcore/ (AgentCore設定)")
    print("  - .bedrock_agentcore.yaml (AgentCore設定ファイル)")
    print("  - deployment内の生成ファイル (02_runtimeのみ)")
    print("\n✅ 以下を保持します:")
    print("  - *_ja.py (日本語化されたPythonファイル)")
    print("  - README*.md (ドキュメント)")
    print("  - オリジナルのソースファイル")
    print("  - .gitignore")
    
    base_path = Path("/workshop")
    
    for dir_name in TARGET_DIRS:
        clean_directory(base_path, dir_name)
    
    print("\n" + "=" * 60)
    print("✅ クリーンアップ完了！")
    print("=" * 60)
    print("\n💡 日本語化ファイル（*_ja.py）は保持されています。")


if __name__ == "__main__":
    main()
