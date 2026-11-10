"""数据安全回归 case 的独立 CLI 入口。"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from dlp_auto.core.agent import Agent
from dlp_auto.core.executor import Executor
from dlp_auto.core.judge import Judge
from dlp_auto.core.run_context import RunContext
from dlp_auto.core.runlock import single_instance
from dlp_auto.core.screen import Screen
from dlp_auto.llm import build_registry

from .loader import RegressionLoader
from .report import RegressionReportWriter
from .resources import RegressionRunResources
from .runner import RegressionRunner


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for stream in self._streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self):
        for stream in self._streams:
            stream.flush()


@contextlib.contextmanager
def _tee_output(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = _Tee(old_out, file)
        sys.stderr = _Tee(old_err, file)
        try:
            yield
        finally:
            sys.stdout, sys.stderr = old_out, old_err


def _build_agent(
    settings,
    *,
    platform,
    screen: Screen,
) -> tuple[Agent, Judge, object]:
    registry = build_registry(settings)
    executor = Executor(
        platform,
        screen,
        failsafe=settings.get("executor", "failsafe", default=True),
        type_interval=settings.get("executor", "type_interval", default=0.02),
        move_duration=settings.get("executor", "move_duration", default=0.2),
        click_pause=settings.get("executor", "click_pause", default=0.05),
    )
    judge = Judge(registry.judge)
    agent = Agent(
        registry.default,
        executor,
        screen,
        max_steps=settings.get("agent", "max_steps", default=30),
        step_wait_sec=settings.get("agent", "step_wait_sec", default=0.9),
        capture_each_step=False,
        judge=judge,
        max_verify_retries=settings.get("agent", "max_verify_retries", default=2),
        max_parse_retries=settings.get("agent", "max_parse_retries", default=3),
    )
    return agent, judge, registry


def _run(args, context: RunContext) -> int:
    cases = RegressionLoader().load(args.cases_dir)
    if args.filter:
        cases = [case for case in cases if args.filter in case.id]
    if not cases:
        print(f"[regression] 未找到匹配的 case（dir={args.cases_dir} filter={args.filter}）")
        return 0

    run_dir = Path(args.report_root) / context.run_id
    writer = RegressionReportWriter(run_dir)
    screen = Screen(
        resize_to=context.settings.get("screen", "resize_to", default=1080),
        out_dir=writer.screenshot_dir,
    )
    try:
        agent, judge, registry = _build_agent(
            context.settings,
            platform=context.platform,
            screen=screen,
        )
    except ValueError as exc:
        print(f"[regression] LLM 配置无效：{exc}", file=sys.stderr)
        return 2
    agent.capture_each_step = args.debug_shots

    print(f"[regression] platform={context.platform.value}")
    print(f"[regression] 载入 {len(cases)} 个 case")
    report = RegressionRunner(
        context=context,
        agent=agent,
        judge=judge,
        writer=writer,
        llm_registry=registry,
        reflect=args.reflect,
        resources=RegressionRunResources(
            keep_browser_open=args.keep_browser_open,
        ),
    ).run(cases)
    statuses = [case.status for case in report.cases]
    print(
        "\n===== 回归汇总 ===== "
        f"total={len(statuses)} "
        f"passed={statuses.count('passed')} "
        f"failed={statuses.count('failed')} "
        f"inconclusive={statuses.count('inconclusive')} "
        f"skipped={statuses.count('skipped')} "
        f"error={statuses.count('error')}"
    )
    print(f"[regression] 本地报告：{writer.html_path}")
    if any(status in {"failed", "error"} for status in statuses):
        return 1
    if any(status == "inconclusive" for status in statuses):
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dlp_auto.regression.run",
        description="运行与通道覆盖主线隔离的数据安全回归 case",
    )
    parser.add_argument(
        "cases_dir",
        nargs="?",
        default="cases/regression",
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--filter", default=None)
    parser.add_argument("--debug-shots", action="store_true")
    parser.add_argument(
        "--keep-browser-open",
        action="store_true",
        help="run 结束后保留本次管理后台受管浏览器，默认统一关闭",
    )
    reflect_group = parser.add_mutually_exclusive_group()
    reflect_group.add_argument(
        "--reflect",
        dest="reflect",
        action="store_true",
        default=None,
        help="强制开启成功 AI 步骤反哺",
    )
    reflect_group.add_argument(
        "--no-reflect",
        dest="reflect",
        action="store_false",
        help="强制关闭反哺（已存在 hints 仍会读取）",
    )
    parser.add_argument(
        "--report-root",
        default="reports/regression",
    )
    parser.add_argument(
        "--no-lock",
        dest="use_lock",
        action="store_false",
        default=True,
    )
    parser.add_argument(
        "--no-log-file",
        dest="log_file",
        action="store_false",
        default=True,
    )
    args = parser.parse_args(argv)

    try:
        context = RunContext.create(
            config_path=args.config,
            report_dir=args.report_root,
            log_dir=args.report_root,
            screenshot_root=args.report_root,
        )
    except ValueError as exc:
        print(f"[regression] 运行配置无效：{exc}", file=sys.stderr)
        return 2

    def dispatch() -> int:
        if not args.log_file:
            return _run(args, context)
        run_dir = Path(args.report_root) / context.run_id
        with _tee_output(run_dir / "run.log"):
            return _run(args, context)

    if args.use_lock:
        with single_instance(".tmp/dlp_auto_run.lock") as ok:
            if not ok:
                print(
                    "[regression] 已有 GUI run 在执行，本次未启动。",
                    file=sys.stderr,
                )
                return 3
            return dispatch()
    return dispatch()


if __name__ == "__main__":
    raise SystemExit(main())
