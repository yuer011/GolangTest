"""独立回归 case 的数据模型与注册表。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from dlp_auto.config import Settings
from dlp_auto.core.platform import Platform

RegressionStepKind = Literal["ai", "hard", "cleanup"]
Instruction = str | Callable[["RegressionStepContext"], str]
StepCondition = Callable[["RegressionStepContext"], bool]


@dataclass
class RegressionStepContext:
    case: RegressionCaseSpec
    settings: Settings
    run_id: str
    extras: dict[str, Any] = field(default_factory=dict)
    resources: Any = None


@dataclass(frozen=True)
class RegressionStep:
    name: str
    kind: RegressionStepKind
    payload: Instruction | Callable[[RegressionStepContext], Any]
    evidence_ref: str = ""
    action_limits: dict[str, int] = field(default_factory=dict)
    continue_on_assertion_failure: bool = False
    when: StepCondition | None = None


@dataclass(frozen=True)
class AssertionSpec:
    name: str
    checker: str
    assertion_set: Instruction
    adapter: str = ""
    evidence_ref: str = ""
    settle_timeout_sec: float = 0


@dataclass(frozen=True)
class SourceCheck:
    source_ref: str
    required_assertions: tuple[str, ...]


@dataclass(frozen=True)
class RegressionCaseSpec:
    id: str
    name: str
    platforms: tuple[Platform, ...]
    steps: tuple[RegressionStep, ...]
    assertions: tuple[AssertionSpec, ...]
    source_checks: tuple[SourceCheck, ...]
    tags: tuple[str, ...] = ()
    reflect: bool = False


_REGISTRY: list[RegressionCaseSpec] = []


def get_registry() -> list[RegressionCaseSpec]:
    return list(_REGISTRY)


def clear_registry() -> None:
    _REGISTRY.clear()


def regression_case(
    *,
    id: str,
    name: str,
    platforms: Iterable[Platform],
    assertions: Iterable[AssertionSpec],
    source_checks: Iterable[SourceCheck],
    tags: Iterable[str] = (),
    reflect: bool = False,
) -> Callable[
    [Callable[[], Iterable[RegressionStep]]],
    RegressionCaseSpec,
]:
    platform_tuple = tuple(platforms)
    if not platform_tuple:
        raise ValueError(f"regression case {id!r} 必须声明至少一个平台")

    assertion_tuple = tuple(assertions)
    assertion_names = [item.name for item in assertion_tuple]
    if len(assertion_names) != len(set(assertion_names)):
        raise ValueError(f"regression case {id!r} 存在重复 assertion name")

    source_tuple = tuple(source_checks)
    known_assertions = set(assertion_names)
    for source in source_tuple:
        missing = set(source.required_assertions) - known_assertions
        if missing:
            raise ValueError(
                f"regression case {id!r} 的 {source.source_ref} 引用了未知断言：{sorted(missing)}"
            )

    def decorator(
        define_fn: Callable[[], Iterable[RegressionStep]],
    ) -> RegressionCaseSpec:
        spec = RegressionCaseSpec(
            id=id,
            name=name,
            platforms=platform_tuple,
            steps=tuple(define_fn()),
            assertions=assertion_tuple,
            source_checks=source_tuple,
            tags=tuple(tags),
            reflect=reflect,
        )
        _REGISTRY.append(spec)
        return spec

    return decorator


def ai_step(
    name: str,
    instruction: Instruction,
    *,
    when: StepCondition | None = None,
    evidence_ref: str = "",
    action_limits: dict[str, int] | None = None,
    continue_on_assertion_failure: bool = False,
) -> RegressionStep:
    return RegressionStep(
        name=name,
        kind="ai",
        payload=instruction,
        when=when,
        evidence_ref=evidence_ref,
        action_limits=dict(action_limits or {}),
        continue_on_assertion_failure=continue_on_assertion_failure,
    )


def hard_step(
    name: str,
    fn: Callable[[RegressionStepContext], Any],
    *,
    when: StepCondition | None = None,
) -> RegressionStep:
    return RegressionStep(name=name, kind="hard", payload=fn, when=when)


def cleanup_step(
    fn: Callable[[RegressionStepContext], Any],
    *,
    when: StepCondition | None = None,
) -> RegressionStep:
    return RegressionStep(
        name="<cleanup>",
        kind="cleanup",
        payload=fn,
        when=when,
    )


def resolve_text(
    value: Instruction,
    ctx: RegressionStepContext,
) -> str:
    return value(ctx) if callable(value) else value
