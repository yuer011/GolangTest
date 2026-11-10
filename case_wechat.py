"""桌面应用 - 即时通信 - 微信 - DLP 外发 case 集合（Windows 端）。

平台：Windows（本文件位于 cases/desktop_app/im/windows/，仅含 windows 端 case）。
四类外发的确定性脚手架统一在 dlp_auto/case/im_windows_common.py，本文件只声明微信
专有配置 + 四个 @case。

微信专有信息（真机实测/用户确认）：
- 可执行文件：**Weixin.exe**（新版微信 4.x；Get-CimInstance 实测。**不是**老版
  WeChat.exe，误用老名会打不开），主窗口标题 "微信"。
- 外发目标：**「文件传输助手」**（微信自带的特殊会话，始终存在；从 config/contacts.yaml
  读，缺省回落）。搜索输入「文件传输助手」即可定位。
- 全局搜索：不使用快捷键，AI 直接在主界面搜索框输入名字进会话（用户决策）。
- 自带截图：有（用户确认，聊天框工具栏截图按钮）。

IM 最低场景覆盖（见 add-case SKILL 二·补充）——微信 Windows 端四类外发全覆盖：
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
    report_name="微信",
    app_key="wechat",
    contacts_app="wechat",
    target=outbound_target("desktop_app.im", "wechat", default="文件传输助手"),
    target_kind="个人/会话",
    id_slug="wechat",
)
_TAGS = ["desktop_app", "im", "wechat", "dlp", "outbound", "windows"]
# 整款微信全部 case 跑完后关闭其窗口（不退登录）——app 级 teardown，见 runner。
register_app_teardown(_APP.report_name, make_app_teardown(_APP))


@case(
    id="desktop_app.im.wechat.outbound_file.drag_drop",
    name="桌面应用 - 即时通信 - 微信 - 外发文件 - 拖拽文件到对话框",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="拖拽文件到对话框",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return drag_drop_steps(_APP)


@case(
    id="desktop_app.im.wechat.outbound_file.upload",
    name="桌面应用 - 即时通信 - 微信 - 外发文件 - 对话框文件上传",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="对话框文件上传",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_upload() -> list[Step | None]:
    return upload_steps(_APP)


@case(
    id="desktop_app.im.wechat.outbound_file.copy_paste",
    name="桌面应用 - 即时通信 - 微信 - 外发文件 - 复制粘贴文件外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="复制粘贴文件外发",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_copy_paste() -> list[Step | None]:
    return copy_paste_steps(_APP)


@case(
    id="desktop_app.im.wechat.outbound_screenshot.builtin_capture",
    name="桌面应用 - 即时通信 - 微信 - 外发截图 - 自带截图外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发截图（自带截图工具）", action="自带截图外发",
    platforms=[Platform.WINDOWS], tags=[*_TAGS, "screenshot"], reflect=True,
)
def case_screenshot() -> list[Step | None]:
    return screenshot_steps(_APP)
