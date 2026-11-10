"""桌面应用 - 即时通信 - Lark - DLP 外发 case 集合（Windows 端）。

平台：Windows（本文件位于 cases/desktop_app/im/windows/，仅含 Windows 端 case）。
四类外发的确定性脚手架统一在 dlp_auto/case/im_windows_common.py，本文件只声明 Lark
专有配置与四个 @case。

Lark 专有信息（真机实测/用户确认）：
- 海外版 Lark 与国内飞书是不同产品、不同进程；主程序为 Lark.exe，真机路径
  C:\\Program Files\\Lark\\app\\Lark.exe，主窗口标题稳定包含「lark」。
- 外发目标：群聊「DLP测试」（从 config/contacts.yaml 读，缺省回落）。
- 主界面搜索：复用共享脚手架，AI 视觉搜索并进入目标群聊。
- 自带截图：按用户要求覆盖，用聊天输入区工具栏的截图入口外发。

IM 最低场景覆盖（见 add-case SKILL 二·补充）——Lark Windows 端四类全覆盖：
拖拽 / 自带上传 / 复制粘贴 / 自带截图。
"""
from __future__ import annotations

from dlp_auto.case.contacts import outbound_target
from dlp_auto.case.im_windows_common import (
    ImApp, copy_paste_steps, drag_drop_steps, make_app_teardown,
    screenshot_steps, upload_steps,
)
from dlp_auto.case.spec import Step, case, register_app_teardown
from dlp_auto.core.platform import Platform


_APP = ImApp(
    report_name="Lark",
    app_key="lark",
    contacts_app="lark",
    target=outbound_target("desktop_app.im", "lark", default="DLP测试"),
    target_kind="群聊",
    id_slug="lark",
    # Lark 常驻托盘；真机托盘 UIA Name 为「Lark - 1 个运行窗口」，与飞书可严格区分。
    open_wake_tray=True,
)
_TAGS = ["desktop_app", "im", "lark", "dlp", "outbound", "windows"]

# 整款 Lark 全部 case 跑完后关闭主窗到托盘，不结束进程或退出登录。
register_app_teardown(_APP.report_name, make_app_teardown(_APP))


@case(
    id="desktop_app.im.lark.outbound_file.drag_drop",
    name="桌面应用 - 即时通信 - Lark - 外发文件 - 拖拽文件到对话框",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="拖拽文件到对话框",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return drag_drop_steps(_APP)


@case(
    id="desktop_app.im.lark.outbound_file.upload",
    name="桌面应用 - 即时通信 - Lark - 外发文件 - 对话框文件上传",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="对话框文件上传",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_upload() -> list[Step | None]:
    return upload_steps(_APP)


@case(
    id="desktop_app.im.lark.outbound_file.copy_paste",
    name="桌面应用 - 即时通信 - Lark - 外发文件 - 复制粘贴文件外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="复制粘贴文件外发",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_copy_paste() -> list[Step | None]:
    return copy_paste_steps(_APP)


@case(
    id="desktop_app.im.lark.outbound_screenshot.builtin_capture",
    name="桌面应用 - 即时通信 - Lark - 外发截图 - 自带截图外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发截图（自带截图工具）", action="自带截图外发",
    platforms=[Platform.WINDOWS], tags=[*_TAGS, "screenshot"], reflect=True,
)
def case_screenshot() -> list[Step | None]:
    return screenshot_steps(_APP)
