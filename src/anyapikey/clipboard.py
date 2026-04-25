"""剪貼簿操作模組 — 跨平台剪貼簿存取與自動清除。"""

from __future__ import annotations

import threading
import time

import pyperclip


def copy_to_clipboard(text: str, ttl: int = 30) -> None:
    """複製文字到系統剪貼簿，並可選擇在指定秒數後自動清除。

    Args:
        text: 要複製的文字。
        ttl: 自動清除時間（秒），0 表示不清除。
    """
    pyperclip.copy(text)

    if ttl > 0:
        # 啟動背景執行緒進行自動清除
        thread = threading.Thread(
            target=_clear_after_ttl,
            args=(text, ttl),
            daemon=True,
        )
        thread.start()


def _clear_after_ttl(original_text: str, ttl: int) -> None:
    """等待指定秒數後，若剪貼簿內容未被更改則清除。

    只有在剪貼簿中仍然是我們複製的內容時才清除，
    避免覆蓋使用者在這段時間內自行複製的其他內容。

    Args:
        original_text: 原始複製的文字。
        ttl: 等待秒數。
    """
    time.sleep(ttl)
    try:
        current = pyperclip.paste()
        if current == original_text:
            pyperclip.copy("")
    except Exception:
        # 剪貼簿存取失敗時靜默忽略
        pass
