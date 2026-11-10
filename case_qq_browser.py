"""Web 网站 - 其它 - QQ 浏览器 - DLPTest HTTPS POST case（Windows）。"""
from __future__ import annotations

from dlp_auto.case.spec import Step, case, register_app_teardown
from dlp_auto.case.web_dlptest_windows import click_upload_steps, drag_drop_steps
from dlp_auto.case.web_windows_common import BrowserApp, make_browser_teardown
from dlp_auto.core.platform import Platform


_APP = BrowserApp(
    report_name="QQ 浏览器",
    app_key="qq_browser",
    startup_prompt_instruction=(
        "当前是用独立新 profile 启动的 QQ 浏览器，DLPTest HTTPS POST 页面可能被 "
        "QQ 浏览器自身的首次启动、功能引导或其他非业务弹窗遮挡。请根据当前画面关闭"
        "所有这类弹窗；若有多层，每关闭一层都重新观察，直到 DLPTest 页面无遮挡、"
        "可直接操作 HTTPS POST Test 与 File upload 表单后立即 finished。若一开始"
        "没有弹窗，也立即 finished。\n"
        "**本步只关闭浏览器自身弹窗**：不要上传文件、不要点击网页 Submit、不要滚动"
        "页面、不要点任务栏或切换窗口。必须按当前视觉定位关闭按钮，禁止依赖固定坐标。"
    ),
)
register_app_teardown(_APP.report_name, make_browser_teardown(_APP))


@case(
    id="web.other.qq_browser.dlptest_https_post.drag_drop",
    name="Web 网站 - 其它 - QQ 浏览器 - DLPTest HTTPS POST - 拖拽上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="拖拽上传",
    platforms=[Platform.WINDOWS],
    tags=[
        "web", "other", "browser", "qq_browser", "dlptest",
        "https_post", "outbound", "windows",
    ],
    reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return drag_drop_steps(_APP)


@case(
    id="web.other.qq_browser.dlptest_https_post.click_upload",
    name="Web 网站 - 其它 - QQ 浏览器 - DLPTest HTTPS POST - 点击上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="点击上传",
    platforms=[Platform.WINDOWS],
    tags=[
        "web", "other", "browser", "qq_browser", "dlptest",
        "https_post", "outbound", "windows",
    ],
    reflect=True,
)
def case_click_upload() -> list[Step | None]:
    return click_upload_steps(_APP)
