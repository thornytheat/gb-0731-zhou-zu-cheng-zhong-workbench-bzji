import re
from decimal import Decimal, InvalidOperation

from app.config import Rules
from app.errors import DomainError

VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")

# 参数名 → (类型, 下限, 上限)。类型 int 只收 JSON 整数，decimal 收字符串或数字并精确解析。
FIELDS = {
    "debounce_ms": ("int", 0, 250),
    "pair_ms": ("int", 1, 500),
    "min_spacing_m": ("decimal", Decimal("0.1"), Decimal("12")),
    "tandem_spacing_m": ("decimal", Decimal("0.1"), Decimal("12")),
    "max_spacing_m": ("decimal", Decimal("0.55"), Decimal("60")),
    "max_wheel_kg": ("decimal", Decimal("1"), Decimal("100000")),
    "weight_resolution_kg": ("decimal", Decimal("0.000001"), Decimal("1")),
    "notice_ratio": ("decimal", Decimal("0.0001"), Decimal("1")),
    "severe_ratio": ("decimal", Decimal("0.0001"), Decimal("1")),
    "ticket_tolerance_kg": ("decimal", Decimal("0"), Decimal("100000")),
    "ticket_grace_min": ("int", 0, 1440),
}


def _invalid(detail):
    return DomainError("UPGRADE_INVALID", detail=detail)


def _field(name, raw):
    kind, low, high = FIELDS[name]
    if isinstance(raw, bool):
        raise _invalid(name)
    if kind == "int":
        if not isinstance(raw, int):
            raise _invalid(name)
        value = raw
    else:
        if not isinstance(raw, (str, int, float)):
            raise _invalid(name)
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            raise _invalid(name) from None
        if not value.is_finite():
            raise _invalid(name)
    if not low <= value <= high:
        raise _invalid(name)
    return value


def target_rules(version, overrides):
    """校验升级目标，返回完整规则集；未覆盖的参数沿用当前标准值。"""
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise _invalid("rules")
    values = {}
    for name, raw in (overrides or {}).items():
        if name not in FIELDS:
            raise _invalid(str(name))
        values[name] = _field(name, raw)
    rules = Rules(version=version, **values)
    if not rules.min_spacing_m <= rules.tandem_spacing_m <= rules.max_spacing_m:
        raise _invalid("spacing")
    if not rules.notice_ratio <= rules.severe_ratio:
        raise _invalid("ratio")
    return rules
