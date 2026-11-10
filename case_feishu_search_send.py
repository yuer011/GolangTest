"""桌面应用 - 即时通信 - 飞书 - AI 流程冒烟 case。

目的：用最小步骤跑通「确定性硬动作 + AI 视觉操作」混合闭环，
不涉及 DLP 拦截断言，仅验证能驱动飞书完成一次搜索 + 发消息。

步骤设计（针对真机联调踩坑做的确定性改造）：
- 打开飞书：hard，用 `open -a` 启动，避免模型从 dock 找图标误点。
- 聚焦搜索框：hard，用 Cmd+K 全局搜索快捷键，避免模型识别左侧放大镜图标。
- 搜索用户 / 发送消息：ai，交给视觉 Agent 完成。

层级对齐 DLP 管理后台分级（详见 docs/stage2_plan.md §4）。
"""
from __future__ import annotations

import time

from dlp_auto.actions import apps, keyboard
from dlp_auto.case.spec import Step, ai, case, hard, step
from dlp_auto.core.platform import Platform

_APP_NAME = "Lark"
_SEARCH_USER = "张永慧"
_MESSAGE = "test"


def _open_feishu(ctx) -> None:
    name = _app_name(ctx)
    apps.open_app(name, wait_sec=4.0)


def _focus_search(ctx) -> None:
    apps.activate_app(_app_name(ctx))
    time.sleep(1.0)
    keyboard.hotkey("command", "e")
    time.sleep(1.0)


def _app_name(ctx) -> str:
    if ctx is None or ctx.settings is None:
        return _APP_NAME
    return ctx.settings.get("platform", "overrides", "mac", "app_names", "im",
                            default=_APP_NAME)


@case(
    id="desktop_app.im.feishu.search_and_send",
    name="桌面应用 - 即时通信 - 飞书 - 搜索用户并发送消息",
    channel="desktop_app.im",
    platforms=[Platform.MAC],
    tags=["desktop_app", "im", "feishu", "smoke", "demo"],
    reflect=True,
)
def define() -> list[Step | None]:
    return [
        step("打开飞书", hard(_open_feishu)),
        step("聚焦全局搜索框（Cmd+E）", hard(_focus_search)),
        step("搜索用户张永慧",
             ai(f"当前焦点在飞书的全局搜索输入框，输入'{_SEARCH_USER}'，"
                f"等待搜索结果出现后，点击结果列表中名为'{_SEARCH_USER}'的用户进入会话")),
        step("发送消息 test",
             ai(f"在聊天底部的消息输入框输入'{_MESSAGE}'，然后按回车发送。"
                f"只发送一次：一旦在聊天记录中看到自己发出的'{_MESSAGE}'气泡、"
                f"且输入框已清空，立即结束（finished），不要重复输入或重复回车")),
    ]
