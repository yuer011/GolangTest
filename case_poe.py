"""桌面应用 - AI应用 - Poe - DLP 对话外发 case 集合（Windows）。

真机与产品语义（均经真机核对）：
- 主程序/主窗：Poe.exe（Electron + Squirrel 打包，装于 %LOCALAPPDATA%\\Poe）。根目录
  Poe.exe 是版本无关的 Squirrel 启动器，自动拉起 app-<版本>\\Poe.exe 主进程，故只登记它。
- Poe 主窗**标题恒为空**（真机实测：唯一可见主窗 class=Chrome_WidgetWin_1、title=''），
  无法用标题子串识别，只能靠进程名 poe.exe 强匹配——已在 apps._EMPTY_TITLE_APPS 登记，
  _find_window 对其放行空标题窗口（仍要求进程名命中，不影响其它应用）。
- 关闭主窗后 4 个 Poe.exe 进程仍在、主窗销毁；再次启动根目录 Poe.exe 后进程数仍为 4，
  且恢复同一空标题主窗，未启动第二实例，故 relaunch_if_hidden=True。
- Poe 无「办公模式/日常模式」之分，进入对话即可外发，不需要 required_mode 前置切换。
- 进入对话：左侧存在历史对话时进入第一条；左侧没有历史对话时沿用当前对话页。
- 每次先在输入区写入“这是测试文件，收到后回复收到即可，无需解析”及本次唯一标识，
  再加入附件；文档 hard 回车一次发送（Poe 回车即发送），声明不单独发送。
- Poe 会回复消息，视觉验收必须同时看到我方最新消息中的声明 + 唯一标识 + 附件、输入框清空、
  该消息后的新 AI 回复；回复不能代替我方外发证据。
- 附件入口与千问/元宝/Kimi 不同（真机核对）：点“+”附件按钮**直接弹出系统文件对话框**，
  没有二级菜单（attach_opens_dialog_directly=True），故上传步骤只点一次“+”，不再点菜单项。
- Poe 客户端界面为英文，但外发内容与验收锚点均为我方中文测试声明 + dlp_ai_ 唯一标识，
  不依赖界面语言。
- 比 Kimi 少一条截图 case：共 3 条 —— 拖拽文档、上传文件、复制粘贴文档。

该类软件使用独立的 desktop_app.ai_chat 通道和 ai_chat_windows_common 脚手架，不放入 IM
目录，也不复用 IM 的联系人/群聊提示词。
"""
from __future__ import annotations

import os

from dlp_auto.case.ai_chat_windows_common import (
    AiChatApp, copy_paste_document_steps, drag_document_steps,
    make_app_teardown, upload_document_steps,
)
from dlp_auto.case.spec import Step, case, register_app_teardown
from dlp_auto.core.platform import Platform


_SAMPLES_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "assets", "samples",
))
_APP = AiChatApp(
    report_name="Poe",
    app_key="poe",
    id_slug="poe",
    image_template=os.path.join(_SAMPLES_DIR, "dlp_image_trae.png"),
    relaunch_if_hidden=True,  # 真机确认：后台进程仍在且无主窗时，重启只恢复原单实例主窗
    # Poe 无模式切换，required_mode 留空
    attach_opens_dialog_directly=True,  # 真机核对：点“+”直接弹系统文件对话框，无二级菜单
    # document_send_via_button 用默认 False：真机核对回车即发送（同千问/元宝）
)
_TAGS = [
    "desktop_app", "ai_chat", "poe", "dlp", "outbound", "windows",
]

register_app_teardown(_APP.report_name, make_app_teardown(_APP))


@case(
    id="desktop_app.ai_chat.poe.outbound_document.drag_drop",
    name="桌面应用 - AI应用 - Poe - 外发文档 - 拖拽文档到对话",
    channel="desktop_app.ai_chat", app=_APP.report_name,
    scenario="外发文档", action="拖拽文档到对话",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_drag_document() -> list[Step | None]:
    return drag_document_steps(_APP)


@case(
    id="desktop_app.ai_chat.poe.outbound_document.upload",
    name="桌面应用 - AI应用 - Poe - 外发文档 - 上传文件",
    channel="desktop_app.ai_chat", app=_APP.report_name,
    scenario="外发文档", action="上传文件",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_upload_document() -> list[Step | None]:
    return upload_document_steps(_APP)


@case(
    id="desktop_app.ai_chat.poe.outbound_document.copy_paste",
    name="桌面应用 - AI应用 - Poe - 外发文档 - 复制粘贴文档",
    channel="desktop_app.ai_chat", app=_APP.report_name,
    scenario="外发文档", action="复制粘贴文档",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_copy_paste_document() -> list[Step | None]:
    return copy_paste_document_steps(_APP)
