"""桌面应用 - AI应用 - Kimi - DLP 对话外发 case 集合（Windows）。

真机与产品语义（均经真机核对）：
- 主程序/主窗：Kimi.exe /「Kimi」（Electron 应用，安装于当前用户 LocalAppData）；
  关窗即缩托盘（进程存活、主窗销毁），托盘态再次启动 exe 可恢复原单实例主窗
  （故 relaunch_if_hidden=True）。
- Kimi 无「办公模式/日常模式」之分，进入对话即可外发，不需要 required_mode 前置切换。
- 进入对话：左侧存在历史对话时进入第一条；左侧没有历史对话时沿用当前对话页。
- 每次先在输入区写入“这是测试文件，收到后回复收到即可，无需解析”及本次唯一标识，
  再加入附件/截图；文档 hard 回车一次，截图只点击一次发送按钮，声明不单独发送。
- Kimi 会回复消息，视觉验收只认我方最新消息中的声明 + 唯一标识 + 附件，不拿“收到”回复
  代替外发成功。
- 附件入口与千问/元宝不同（真机核对）：点“+”后文件与图片是**同一个入口**「添加文件和图片」，
  故只做一条“上传文件”case（不再单列上传图片）。
- 截图入口在“+”菜单里、文字含「截图」（可能后跟软件名）；与千问/元宝不同，Kimi 点该行后
  **自动完成截图**（自动截取上一个前台窗口），无需框选区域、无需点对勾
  （screenshot_auto_capture=True）。
- 共 4 条：拖拽文档、上传文件、复制粘贴文档、截屏提问。

该类软件使用独立的 desktop_app.ai_chat 通道和 ai_chat_windows_common 脚手架，不放入 IM
目录，也不复用 IM 的联系人/群聊提示词。
"""
from __future__ import annotations

import os

from dlp_auto.case.ai_chat_windows_common import (
    AiChatApp, copy_paste_document_steps, drag_document_steps,
    make_app_teardown, screenshot_steps, upload_document_steps,
)
from dlp_auto.case.spec import Step, case, register_app_teardown
from dlp_auto.core.platform import Platform


_SAMPLES_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "assets", "samples",
))
_APP = AiChatApp(
    report_name="Kimi",
    app_key="kimi",
    id_slug="kimi",
    image_template=os.path.join(_SAMPLES_DIR, "dlp_image_trae.png"),
    relaunch_if_hidden=True,  # 真机确认：后台进程在且无主窗时，重启 exe 只恢复原单实例主窗
    # Kimi 无模式切换，required_mode 留空
    upload_document_label="添加文件和图片",  # 真机核对：点“+”后文件与图片共用此入口
    screenshot_label="截图",                 # 真机核对：“+”菜单里含“截图”字样的那行
    screenshot_in_plus_menu=True,            # 截图入口在“+”附件菜单内
    screenshot_auto_capture=True,            # 点该行后自动截图，无需框选/确认
    document_send_via_button=True,           # 真机核对：回车只换行不发送，必须点发送按钮
)
_TAGS = [
    "desktop_app", "ai_chat", "kimi", "dlp", "outbound", "windows",
]

register_app_teardown(_APP.report_name, make_app_teardown(_APP))


@case(
    id="desktop_app.ai_chat.kimi.outbound_document.drag_drop",
    name="桌面应用 - AI应用 - Kimi - 外发文档 - 拖拽文档到对话",
    channel="desktop_app.ai_chat", app=_APP.report_name,
    scenario="外发文档", action="拖拽文档到对话",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_drag_document() -> list[Step | None]:
    return drag_document_steps(_APP)


@case(
    id="desktop_app.ai_chat.kimi.outbound_document.upload",
    name="桌面应用 - AI应用 - Kimi - 外发文档 - 上传文件",
    channel="desktop_app.ai_chat", app=_APP.report_name,
    scenario="外发文档", action="上传文件",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_upload_document() -> list[Step | None]:
    return upload_document_steps(_APP)


@case(
    id="desktop_app.ai_chat.kimi.outbound_document.copy_paste",
    name="桌面应用 - AI应用 - Kimi - 外发文档 - 复制粘贴文档",
    channel="desktop_app.ai_chat", app=_APP.report_name,
    scenario="外发文档", action="复制粘贴文档",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_copy_paste_document() -> list[Step | None]:
    return copy_paste_document_steps(_APP)


@case(
    id="desktop_app.ai_chat.kimi.outbound_screenshot.builtin_capture",
    name="桌面应用 - AI应用 - Kimi - 外发截图 - 截屏提问",
    channel="desktop_app.ai_chat", app=_APP.report_name,
    scenario="外发截图", action="截屏提问",
    platforms=[Platform.WINDOWS], tags=[*_TAGS, "screenshot"], reflect=True,
)
def case_screenshot() -> list[Step | None]:
    return screenshot_steps(_APP)
