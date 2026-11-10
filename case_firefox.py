"""Web 网站 - 其它 - 火狐浏览器 - DLPTest HTTPS POST case（macOS）。"""
from __future__ import annotations

from dlp_auto.case.spec import Step, case, register_app_teardown
from dlp_auto.case.web_dlptest_mac import click_upload_steps, drag_drop_steps
from dlp_auto.case.web_mac_common import BrowserApp, make_browser_teardown
from dlp_auto.core.platform import Platform


_APP = BrowserApp(
    report_name="火狐浏览器",
    app_key="firefox",
    startup_prompt_instruction=(
        "当前是刚用独立新 profile 启动的 Firefox Mac 版，DLPTest HTTPS POST 页面"
        "可能被一层或多层 Firefox 自身的首次启动弹窗遮挡。请根据当前画面逐层处理"
        "所有**非业务弹窗**：例如欢迎页点“继续”，翻译功能提示点“取消”或关闭。"
        "每关闭一层都重新观察画面，直到 DLPTest 页面不再变暗、没有任何弹窗或遮罩，"
        "并且能直接看到 HTTPS POST Test 与 File upload 表单后立即 finished。若一开始"
        "就没有弹窗，也立即 finished。\n"
        "**本步只关闭浏览器弹窗**：不要上传文件、不要点击网页 Submit、不要滚动页面、"
        "不要切换窗口。必须按当前视觉定位按钮，禁止依赖固定坐标。"
    ),
)
register_app_teardown(_APP.report_name, make_browser_teardown(_APP))


@case(
    id="web.other.firefox.dlptest_https_post.drag_drop",
    name="Web 网站 - 其它 - 火狐浏览器 - DLPTest HTTPS POST - 拖拽上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="拖拽上传",
    platforms=[Platform.MAC],
    tags=[
        "web", "other", "browser", "firefox", "dlptest",
        "https_post", "outbound", "mac",
    ],
    reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return drag_drop_steps(_APP)


@case(
    id="web.other.firefox.dlptest_https_post.click_upload",
    name="Web 网站 - 其它 - 火狐浏览器 - DLPTest HTTPS POST - 点击上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="点击上传",
    platforms=[Platform.MAC],
    tags=[
        "web", "other", "browser", "firefox", "dlptest",
        "https_post", "outbound", "mac",
    ],
    reflect=True,
)
def case_click_upload() -> list[Step | None]:
    return click_upload_steps(_APP)
