"""桌面应用 - 即时通信 - 飞书 - DLP 外发 case 集合。

平台：macOS（本文件位于 cases/desktop_app/im/mac/，仅含 mac 端 case；
      Windows 端请放 cases/desktop_app/im/windows/）。
迁移标注：每个 @case 均显式声明 platforms=[Platform.MAC]，目录与声明双重标注，
      便于后续整体迁移目录时核对。

本文件汇总「飞书」mac 端的正式测试 case，便于 `--filter feishu` 单独跑整个 app。
每个 @case 对应报告里的一行「软件 × 测试场景 × 具体外发动作」：
- app      固定为「飞书」，报告按软件聚合通过率。
- scenario 测试场景，如「外发文件（默认任意文件）」。
- action   具体外发动作，如「拖拽文件到对话框」。

注：敏感测试文件暂从 ~/Documents/test 选取（后续跑通可能调整）。
冒烟 demo 见同目录 case_feishu_search_send.py。
"""
from __future__ import annotations

import os
import subprocess
import time

from dlp_auto.actions import apps, keyboard
from dlp_auto.case.contacts import outbound_target
from dlp_auto.case.spec import Step, ai, case, hard, step
from dlp_auto.core.platform import Platform

_APP = "飞书"
_APP_NAME = "Lark"
# 外发目标会话（联系人）。默认 "石萍萍"，可在不入库的 config/contacts.yaml 里
# 按平台覆盖（换人/换机时改配置即可，无需动 case）。
_PEER = outbound_target("desktop_app.im", "feishu", default="石萍萍")
_SENSITIVE_DIR = "~/Documents/test"  # 敏感测试文件来源目录（暂定）


def _app_name(ctx) -> str:
    if ctx is None or ctx.settings is None:
        return _APP_NAME
    return ctx.settings.get("platform", "overrides", "mac", "app_names", "im",
                            default=_APP_NAME)


def _open_feishu(ctx) -> None:
    apps.open_app(_app_name(ctx), wait_sec=4.0)


def _focus_search(ctx) -> None:
    apps.activate_app(_app_name(ctx))
    time.sleep(1.0)
    keyboard.hotkey("command", "e")
    time.sleep(1.0)


def _open_sensitive_dir(ctx) -> None:
    """用访达打开敏感文件目录（确定性步骤）。

    AI 不擅长从『文稿』里逐级双击进入 test 子目录（易停在选中文件夹层级），
    故此处直接 `open` 该目录，让 AI 只需专注『选文件 + 拖拽』。
    """
    target = os.path.expanduser(_SENSITIVE_DIR)
    subprocess.run(["open", target], check=False)
    time.sleep(2.0)


@case(
    id="desktop_app.im.feishu.outbound_file.drag_drop",
    name="桌面应用 - 即时通信 - 飞书 - 外发文件 - 拖拽文件到对话框",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发文件（默认任意文件）",
    action="拖拽文件到对话框",
    platforms=[Platform.MAC],
    tags=["desktop_app", "im", "feishu", "dlp", "outbound", "mac"],
    reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return [
        step("打开飞书", hard(_open_feishu)),
        step("聚焦全局搜索框（Cmd+E）", hard(_focus_search)),
        step(f"搜索并进入与「{_PEER}」的会话",
             ai(f"当前焦点在飞书全局搜索框，输入'{_PEER}'，等待搜索结果出现后，"
                f"**必须点击**结果中名为'{_PEER}'的联系人，进入与 TA 的聊天会话。"
                f"只有当右侧出现与'{_PEER}'的聊天对话区（顶部显示对方名字、"
                f"下方是聊天记录和输入框）时才算完成；仅输入文字不算完成，"
                f"务必点击结果进入会话后再 finished",
                verify=f"飞书右侧已打开与'{_PEER}'的聊天会话：顶部显示'{_PEER}'，"
                       f"下方有聊天记录区与底部输入框（不再是搜索结果列表）")),
        step("用访达打开 ~/Documents/test 目录", hard(_open_sensitive_dir)),
        step("从访达拖拽一个文件到飞书对话框发送",
             ai(f"屏幕上现在有一个访达(Finder)窗口已经打开了 test 文件夹（通常在"
                f"屏幕右侧或前台），里面是若干文件（不是文件夹）；飞书与'{_PEER}'的"
                f"聊天窗口在另一侧。请直接执行，**不要去点 Dock 栏图标反复切换窗口**："
                f"1) 在访达窗口中单击选中其中任意一个文件（不要双击打开它）；"
                f"2) 把这个被选中的文件拖拽到飞书与'{_PEER}'的聊天输入框区域内并释放；"
                f"3) 若飞书弹出文件发送预览/确认框，点击其中的『发送』按钮。"
                f"注意：目标是把文件发到飞书聊天里。一旦在'{_PEER}'的聊天记录中"
                f"看到该文件已发出，立即结束（finished），不要重复拖拽或重复发送",
                verify=f"与'{_PEER}'的聊天记录中，相比操作前**新增了一条刚发出的文件消息**"
                       f"（文件卡片，显示在对话区最底部、由我方发出）。"
                       f"若操作前后聊天记录没有新增文件消息，或文件在操作前就已存在，"
                       f"则判不通过")),
    ]
