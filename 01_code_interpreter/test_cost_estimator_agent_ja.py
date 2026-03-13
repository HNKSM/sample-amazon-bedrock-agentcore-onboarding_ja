#!/usr/bin/env python3
"""AWSコスト見積もりエージェントのシンプルなテスト"""

import asyncio
import argparse
from cost_estimator_agent.cost_estimator_agent_ja import AWSCostEstimatorAgent

async def test_streaming(architecture: str, verbose: bool = True):
    """Strandsのベストプラクティスに従ってストリーミングコスト見積もりをテスト"""
    if verbose:
        print("\n🔄 Testing streaming cost estimation...")
    agent = AWSCostEstimatorAgent()
    
    # 提供されたテストケースまたはデフォルトを使用
    
    try:
        total_chunks = 0
        total_length = 0
        
        async for event in agent.estimate_costs_stream(architecture):
            if "data" in event:
                # Strandsドキュメントによると、各event["data"]には
                # 新しいデルタコンテンツのみが含まれるため、直接出力できます
                chunk_data = str(event["data"])
                if verbose:
                    print(chunk_data, end="", flush=True)
                
                # デバッグ用のメトリクスを追跡
                total_chunks += 1
                total_length += len(chunk_data)
                
            elif "error" in event:
                if verbose:
                    print(f"\n❌ Streaming error: {event['data']}")
                return False
        
        if verbose:
            print(f"\n📊 Streaming completed: {total_chunks} chunks, {total_length} total characters")
        return total_length > 0
        
    except Exception as e:
        if verbose:
            print(f"❌ Streaming test failed: {e}")
        return False

def test_regular(architecture: str = "EC2 t3.microインスタンス1台を24時間365日稼働", verbose: bool = True):
    """通常の（非ストリーミング）コスト見積もりをテスト"""
    if verbose:
        print("📄 Testing regular cost estimation...")
    agent = AWSCostEstimatorAgent()
    
    # 提供されたテストケースまたはデフォルトを使用
    
    try:
        result = agent.estimate_costs(architecture)
        if verbose:
            print(f"📊 Regular response length: {len(result)} characters")
            print(f"Result preview: {result[:150]}...")
        return len(result) > 0
    except Exception as e:
        if verbose:
            print(f"❌ Regular test failed: {e}")
        return False


def parse_arguments():
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(description='Test AWS Cost Estimation Agent')
    
    parser.add_argument(
        '--architecture', 
        type=str, 
        default="EC2 t3.microインスタンス1台を24時間365日稼働",
        help='テストするアーキテクチャの説明 (デフォルト: "EC2 t3.microインスタンス1台を24時間365日稼働")'
    )
    
    parser.add_argument(
        '--tests',
        nargs='+',
        choices=['regular', 'streaming', 'debug'],
        default=['regular'],
        help='Which tests to run (default: regular)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        default=True,
        help='Enable verbose output (default: True)'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Disable verbose output'
    )
    
    return parser.parse_args()

async def main():
    args = parse_arguments()
    
    # verboseフラグを処理
    verbose = args.verbose and not args.quiet
    
    print("🚀 Testing AWS Cost Agent")
    if verbose:
        print(f"Architecture: {args.architecture}")
        print(f"Tests to run: {', '.join(args.tests)}")
    
    results = {}
    
    # 選択されたテストを実行
    if 'regular' in args.tests:
        results['regular'] = test_regular(args.architecture, verbose)
    
    if 'streaming' in args.tests:
        results['streaming'] = await test_streaming(args.architecture, verbose)
    
    # 結果を出力
    if verbose:
        print("\n📋 Test Results:")
        for test_name, success in results.items():
            status = '✅ PASS' if success else '❌ FAIL'
            print(f"   {test_name.capitalize()} implementation: {status}")
        
        if all(results.values()):
            print("🎉 All tests completed successfully!")
        else:
            print("⚠️ Some tests failed - check logs above")
    
    # 結果に基づいて終了コードを返す
    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
