"""Web 网站 - 其它 - 谷歌浏览器 - DLPTest HTTPS POST case（macOS）。"""
from __future__ import annotations

from dlp_auto.case.spec import Step, case, register_app_teardown
from dlp_auto.case.web_dlptest_mac import click_upload_steps, drag_drop_steps
from dlp_auto.case.web_mac_common import BrowserApp, make_browser_teardown
from dlp_auto.core.platform import Platform


_APP = BrowserApp(
    report_name="谷歌浏览器",
    app_key="chrome",
)
register_app_teardown(_APP.report_name, make_browser_teardown(_APP))


@case(
    id="web.other.chrome.dlptest_https_post.drag_drop",
    name="Web 网站 - 其它 - 谷歌浏览器 - DLPTest HTTPS POST - 拖拽上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="拖拽上传",
    platforms=[Platform.MAC],
    tags=[
        "web", "other", "browser", "chrome", "dlptest",
        "https_post", "outbound", "mac",
    ],
    reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return drag_drop_steps(_APP)


@case(
    id="web.other.chrome.dlptest_https_post.click_upload",
    name="Web 网站 - 其它 - 谷歌浏览器 - DLPTest HTTPS POST - 点击上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="点击上传",
    platforms=[Platform.MAC],
    tags=[
        "web", "other", "browser", "chrome", "dlptest",
        "https_post", "outbound", "mac",
    ],
    reflect=True,
)
def case_click_upload() -> list[Step | None]:
    return click_upload_steps(_APP)
