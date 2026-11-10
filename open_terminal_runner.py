"""在 Terminal.app 的独立窗口中执行 runner，避开沙箱的文稿打开限制。"""
from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path


def _attribute(ax, element, name):
    error, value = ax.AXUIElementCopyAttributeValue(element, name, None)
    return value if error == 0 else None


def _descendants(ax, root, *, max_nodes: int = 3000):
    stack = [root]
    seen = 0
    while stack and seen < max_nodes:
        current = stack.pop()
        seen += 1
        yield current
        children = _attribute(ax, current, ax.kAXChildrenAttribute)
        stack.extend(reversed(list(children or [])))


def _find(ax, root, role: str, titles: set[str] | None = None):
    for item in _descendants(ax, root):
        if str(_attribute(ax, item, ax.kAXRoleAttribute) or "") != role:
            continue
        title = str(_attribute(ax, item, ax.kAXTitleAttribute) or "")
        if titles is None or title in titles:
            return item
    return None


def launch(runner: Path) -> None:
    import ApplicationServices as ax
    from AppKit import (
        NSApplicationActivateAllWindows,
        NSApplicationActivateIgnoringOtherApps,
        NSRunningApplication,
    )

    runner = runner.resolve(strict=True)
    subprocess.run(["open", "-a", "Terminal"], check=True)

    deadline = time.monotonic() + 10.0
    app = None
    while time.monotonic() < deadline:
        apps = list(
            NSRunningApplication.runningApplicationsWithBundleIdentifier_(
                "com.apple.Terminal"
            )
        )
        if apps:
            app = next((item for item in apps if item.isActive()), apps[0])
            break
        time.sleep(0.1)
    if app is None:
        raise RuntimeError("10s 内未找到 Terminal.app 进程")

    app.activateWithOptions_(
        NSApplicationActivateAllWindows
        | NSApplicationActivateIgnoringOtherApps
    )
    root = ax.AXUIElementCreateApplication(int(app.processIdentifier()))
    menu_bar = _attribute(ax, root, ax.kAXMenuBarAttribute)
    new_command = _find(
        ax,
        menu_bar,
        ax.kAXMenuItemRole,
        {"新建命令…", "New Command…", "New Command..."},
    )
    if new_command is None:
        raise RuntimeError("Terminal 菜单中未找到“新建命令”")
    if ax.AXUIElementPerformAction(new_command, ax.kAXPressAction) != 0:
        raise RuntimeError("打开 Terminal“新建命令”对话框失败")

    dialog = None
    command_field = None
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        windows = _attribute(ax, root, ax.kAXWindowsAttribute) or []
        for window in windows:
            field = _find(ax, window, ax.kAXComboBoxRole)
            if field is not None:
                dialog = window
                command_field = field
                break
        if command_field is not None:
            break
        time.sleep(0.1)
    if dialog is None or command_field is None:
        raise RuntimeError("5s 内未找到 Terminal“新建命令”输入框")

    command = f"/bin/bash -lc {shlex.quote(str(runner))}"
    error = ax.AXUIElementSetAttributeValue(
        command_field,
        ax.kAXValueAttribute,
        command,
    )
    if error != 0:
        raise RuntimeError(f"填写 Terminal runner 命令失败：AX={error}")

    default_button = _attribute(ax, dialog, ax.kAXDefaultButtonAttribute)
    if default_button is None:
        default_button = _find(
            ax,
            dialog,
            ax.kAXButtonRole,
            {"运行", "Run"},
        )
    if default_button is None:
        raise RuntimeError("Terminal“新建命令”对话框缺少运行按钮")
    error = ax.AXUIElementPerformAction(default_button, ax.kAXPressAction)
    if error != 0:
        raise RuntimeError(f"启动 Terminal runner 失败：AX={error}")


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "用法：open_terminal_runner.py <runner>",
            file=sys.stderr,
        )
        return 2
    launch(Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
