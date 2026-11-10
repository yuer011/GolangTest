"""Web 网站 - 其它 - 傲游浏览器 - DLPTest HTTPS POST case（Windows）。"""
from __future__ import annotations

from dlp_auto.case.spec import Step, case, register_app_teardown
from dlp_auto.case.web_dlptest_windows import click_upload_steps, drag_drop_steps
from dlp_auto.case.web_windows_common import BrowserApp, make_browser_teardown
from dlp_auto.core.platform import Platform


_APP = BrowserApp(report_name="傲游浏览器", app_key="maxthon")
register_app_teardown(_APP.report_name, make_browser_teardown(_APP))


@case(
    id="web.other.maxthon.dlptest_https_post.drag_drop",
    name="Web 网站 - 其它 - 傲游浏览器 - DLPTest HTTPS POST - 拖拽上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="拖拽上传",
    platforms=[Platform.WINDOWS],
    tags=[
        "web", "other", "browser", "maxthon", "dlptest",
        "https_post", "outbound", "windows",
    ],
    reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return drag_drop_steps(_APP)


@case(
    id="web.other.maxthon.dlptest_https_post.click_upload",
    name="Web 网站 - 其它 - 傲游浏览器 - DLPTest HTTPS POST - 点击上传",
    channel="web.other",
    app=_APP.report_name,
    scenario="HTTPS POST 文件上传",
    action="点击上传",
    platforms=[Platform.WINDOWS],
    tags=[
        "web", "other", "browser", "maxthon", "dlptest",
        "https_post", "outbound", "windows",
    ],
    reflect=True,
)
def case_click_upload() -> list[Step | None]:
    return click_upload_steps(_APP)
