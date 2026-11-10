"""桌面应用 - 即时通信 - WeLink - DLP 外发 case 集合（Windows 端）。

平台：Windows（本文件位于 cases/desktop_app/im/windows/，仅含 windows 端 case）。
四类外发的确定性脚手架统一在 dlp_auto/case/im_windows_common.py，本文件只声明 WeLink
专有配置（app 名/进程名/外发目标）+ 四个 @case。

WeLink 专有信息（真机实测/用户确认）：
- 可执行文件：WeLink.exe（Get-CimInstance 实测），主窗口标题 "WeLink"。
- 每次 run 前均为冷启动；`scripts/run_case.ps1` 父进程先用 Start-Process 拉起，不走托盘。
- 冷启动主窗出现较慢，本 case 等待 10 秒后再做强制前台确认。
- 外发目标：**个人联系人「李灵云」**（从 config/contacts.yaml 读，缺省回落）。
- 全局搜索：不使用快捷键，AI 直接在主界面搜索框输入名字进会话（用户决策）。
- 自带截图：有（用户确认，聊天框工具栏截图按钮）。

IM 最低场景覆盖（见 add-case SKILL 二·补充）——WeLink Windows 端四类外发全覆盖：
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
    report_name="WeLink",
    app_key="welink",
    contacts_app="welink",
    target=outbound_target("desktop_app.im", "welink", default="李灵云"),
    target_kind="个人/会话",
    id_slug="welink",
    open_wait_sec=10.0,
)
_TAGS = ["desktop_app", "im", "welink", "dlp", "outbound", "windows"]
# 兼容 teardown 总开关关闭时的老路径；主配置启用时 WeLink: quit 会绕过此 close 闭包，
# 关闭窗口并清零安装根目录下的残留进程。
register_app_teardown(_APP.report_name, make_app_teardown(_APP))


@case(
    id="desktop_app.im.welink.outbound_file.drag_drop",
    name="桌面应用 - 即时通信 - WeLink - 外发文件 - 拖拽文件到对话框",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="拖拽文件到对话框",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return drag_drop_steps(_APP)


@case(
    id="desktop_app.im.welink.outbound_file.upload",
    name="桌面应用 - 即时通信 - WeLink - 外发文件 - 对话框文件上传",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="对话框文件上传",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_upload() -> list[Step | None]:
    # WeLink 真机实测：系统文件对话框点『打开』后即自动发送（见 LESSONS #11），
    # 故走 auto_sends 分支——不挂视觉 verify，外发验收以 DLP 日志为准。
    return upload_steps(_APP, auto_sends=True)


@case(
    id="desktop_app.im.welink.outbound_file.copy_paste",
    name="桌面应用 - 即时通信 - WeLink - 外发文件 - 复制粘贴文件外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发文件（默认任意文件）", action="复制粘贴文件外发",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_copy_paste() -> list[Step | None]:
    return copy_paste_steps(_APP)


@case(
    id="desktop_app.im.welink.outbound_screenshot.builtin_capture",
    name="桌面应用 - 即时通信 - WeLink - 外发截图 - 自带截图外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发截图（自带截图工具）", action="自带截图外发",
    platforms=[Platform.WINDOWS], tags=[*_TAGS, "screenshot"], reflect=True,
)
def case_screenshot() -> list[Step | None]:
    return screenshot_steps(_APP)
