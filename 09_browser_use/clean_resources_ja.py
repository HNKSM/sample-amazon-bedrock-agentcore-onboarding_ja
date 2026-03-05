"""
09_browser_useワークショップで作成されたブラウザセッションをクリーンアップ

ブラウザセッションは一時的で、タイムアウト後に自動的に期限切れになります。
このスクリプトはまだアクティブなセッションをリストアップし、
リソースを即座に解放するためにそれらを停止します。
"""

import logging

import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def clean_resources():
    """アクティブなブラウザセッションをリストアップして停止"""
    region = boto3.Session().region_name
    cp_client = boto3.client("bedrock-agentcore-control", region_name=region)
    dp_client = boto3.client("bedrock-agentcore", region_name=region)

    # --- 1. ブラウザツールをリスト（ブラウザIDを見つけるため） ---
    logger.info("Listing browser tools in %s...", region)
    try:
        browsers_resp = cp_client.list_browsers()
        browsers = browsers_resp.get("browsers", [])
    except Exception:
        logger.exception("Failed to list browsers")
        return

    if not browsers:
        logger.info("No browser tools found — nothing to clean up.")
        return

    stopped = 0
    for browser in browsers:
        browser_id = browser["browserId"]
        browser_name = browser.get("name", browser_id)
        logger.info("Browser: %s (%s)", browser_name, browser_id)

        # --- 2. 各ブラウザのセッションをリスト ---
        try:
            sessions_resp = dp_client.list_browser_sessions(browserId=browser_id)
            sessions = sessions_resp.get("browserSessions", [])
        except Exception:
            logger.exception("  Failed to list sessions for %s", browser_id)
            continue

        active_sessions = [
            s for s in sessions if s.get("status") in ("READY", "STARTING")
        ]

        if not active_sessions:
            logger.info("  No active sessions.")
            continue

        for session in active_sessions:
            session_id = session["browserSessionId"]
            status = session.get("status", "UNKNOWN")
            logger.info("  Stopping session %s (status: %s)...", session_id, status)
            try:
                dp_client.stop_browser_session(
                    browserId=browser_id,
                    browserSessionId=session_id,
                )
                stopped += 1
                logger.info("  Stopped session %s", session_id)
            except Exception:
                logger.exception("  Failed to stop session %s", session_id)

    logger.info("Done. Stopped %d session(s).", stopped)


if __name__ == "__main__":
    clean_resources()
