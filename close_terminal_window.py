"""按唯一标题关闭本次 Mac GUI run 的 Terminal 窗口。"""
from __future__ import annotations

import argparse
import time

import ApplicationServices as ax
from AppKit import NSRunningApplication


def _close_matching_window(title_token: str) -> bool:
    for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_(
        "com.apple.Terminal"
    ):
        root = ax.AXUIElementCreateApplication(int(app.processIdentifier()))
        error, windows = ax.AXUIElementCopyAttributeValue(
            root, ax.kAXWindowsAttribute, None
        )
        if error != 0:
            continue
        for window in list(windows or []):
            error, title = ax.AXUIElementCopyAttributeValue(
                window, ax.kAXTitleAttribute, None
            )
            if error != 0 or title_token not in str(title or ""):
                continue
            error, button = ax.AXUIElementCopyAttributeValue(
                window, ax.kAXCloseButtonAttribute, None
            )
            if error != 0 or button is None:
                continue
            return (
                ax.AXUIElementPerformAction(
                    button, ax.kAXPressAction
                )
                == 0
            )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("title_token")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    time.sleep(max(0.0, args.delay))
    for _attempt in range(20):
        if _close_matching_window(args.title_token):
            return 0
        time.sleep(0.25)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
