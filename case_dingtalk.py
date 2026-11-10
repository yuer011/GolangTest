"""桌面应用 - 即时通信 - 钉钉 - DLP 外发 case 集合（Windows 端）。

平台：Windows（本文件位于 cases/desktop_app/im/windows/，仅含 windows 端 case）。
四类外发的确定性脚手架统一在 dlp_auto/case/im_windows_common.py，本文件只声明钉钉
专有配置 + 四个 @case。

钉钉专有信息（真机实测/用户确认）：
- 可执行文件：DingTalk.exe（Get-CimInstance 实测，装于 DingDing/main/current 下），
  主窗口标题 "钉钉"。
- 外发目标：**群聊「DLP测试」**（从 config/contacts.yaml 读，缺省回落）。
- 全局搜索：不使用快捷键，AI 直接在主界面搜索框输入名字进会话（用户决策）。
- 自带截图：有（用户确认，聊天框工具栏截图按钮）。

IM 最低场景覆盖（见 add-case SKILL 二·补充）——钉钉 Windows 端四类外发全覆盖：
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
    report_name="钉钉",
    app_key="dingtalk",
    contacts_app="dingtalk",
    target=outbound_target("desktop_app.im", "dingtalk", default="DLP测试"),
    target_kind="群聊",
    id_slug="dingtalk",
    # 钉钉发文件带预览，正常窗口一屏挤不下完整气泡导致 Judge 看不全（用户实测）。
    # 故**仅钉钉**在 upload/copy_paste 发送前最大化、收尾还原；其余软件保持默认不最大化。
    maximize_on_send=True,
)
_TAGS = ["desktop_app", "im", "dingtalk", "dlp", "outbound", "windows"]
# 整款钉钉全部 case 跑完后关闭其窗口（不退登录）——app 级 teardown，见 runner。
register_app_teardown(_APP.report_name, make_app_teardown(_APP))


@case(
    id="desktop_app.im.dingtalk.outbound_file.drag_drop",
    name="桌面应用 - 即时通信 - 钉钉 - 外发文件 - 拖拽文件到对话框",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="拖拽文件到对话框",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    # 钉钉真机实测：文件拖进聊天框、松开鼠标即**自动发送**（见 LESSONS #11），其后再点
    # 发送 / 重拖都会重复外发。故走 auto_sends 分支——拖完即止、不挂视觉 verify，
    # 外发验收以 DLP 日志为准（气泡展示由 maximize_on_send 最大化后单独确认）。
    return drag_drop_steps(_APP, auto_sends=True)


@case(
    id="desktop_app.im.dingtalk.outbound_file.upload",
    name="桌面应用 - 即时通信 - 钉钉 - 外发文件 - 对话框文件上传",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="对话框文件上传",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_upload() -> list[Step | None]:
    # 钉钉真机实测：系统文件对话框点『打开』后即自动发送（与拖拽同理，见 LESSONS #11/#12），
    # 无「再点发送」环节。若按默认三段式，AI 会去找不存在的发送键、空转到 max_steps（实测
    # 30 步白烧 8.7 万 token）。故走 auto_sends 分支——不挂视觉 verify，外发验收以 DLP 日志为准。
    return upload_steps(_APP, auto_sends=True)


@case(
    id="desktop_app.im.dingtalk.outbound_file.copy_paste",
    name="桌面应用 - 即时通信 - 钉钉 - 外发文件 - 复制粘贴文件外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="复制粘贴文件外发",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_copy_paste() -> list[Step | None]:
    return copy_paste_steps(_APP)


@case(
    id="desktop_app.im.dingtalk.outbound_screenshot.builtin_capture",
    name="桌面应用 - 即时通信 - 钉钉 - 外发截图 - 自带截图外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发截图（自带截图工具）", action="自带截图外发",
    platforms=[Platform.WINDOWS], tags=[*_TAGS, "screenshot"], reflect=True,
)
def case_screenshot() -> list[Step | None]:
    return screenshot_steps(_APP)
