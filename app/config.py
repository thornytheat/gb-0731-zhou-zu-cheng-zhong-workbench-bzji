import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE_VERSION = "axle-1.0.0"
MAX_FILE_BYTES = 1024 * 1024
MAX_ROWS = 4000
CENT = Decimal("0.01")
MAX_WHEEL_KG = Decimal("25000")
DEBOUNCE_MS = 12
PAIR_MS = 35
MIN_SPACING = Decimal("0.55")
TANDEM_SPACING = Decimal("1.80")
MAX_SPACING = Decimal("12.00")
NOTICE_RATIO = Decimal("0.10")
SEVERE_RATIO = Decimal("0.20")
TICKET_TOLERANCE = Decimal("50.00")
TICKET_GRACE_MIN = 15

@dataclass(frozen=True)
class Rules:
    """一次称重计算使用的规则版本与全部参数。升级复核用同一来源换规则重算。"""

    version: str = RULE_VERSION
    debounce_ms: int = DEBOUNCE_MS
    pair_ms: int = PAIR_MS
    min_spacing_m: Decimal = MIN_SPACING
    tandem_spacing_m: Decimal = TANDEM_SPACING
    max_spacing_m: Decimal = MAX_SPACING
    max_wheel_kg: Decimal = MAX_WHEEL_KG
    weight_resolution_kg: Decimal = CENT
    notice_ratio: Decimal = NOTICE_RATIO
    severe_ratio: Decimal = SEVERE_RATIO
    ticket_tolerance_kg: Decimal = TICKET_TOLERANCE
    ticket_grace_min: int = TICKET_GRACE_MIN

    def parameters(self):
        return {
            "debounce_ms": self.debounce_ms,
            "pair_ms": self.pair_ms,
            "min_spacing_m": str(self.min_spacing_m),
            "tandem_spacing_m": str(self.tandem_spacing_m),
            "max_spacing_m": str(self.max_spacing_m),
            "max_wheel_kg": str(self.max_wheel_kg),
            "weight_resolution_kg": str(self.weight_resolution_kg),
            "notice_ratio": str(self.notice_ratio),
            "severe_ratio": str(self.severe_ratio),
            "ticket_tolerance_kg": str(self.ticket_tolerance_kg),
            "ticket_grace_min": self.ticket_grace_min,
        }


STANDARD_RULES = Rules()
RULE_PARAMETERS = STANDARD_RULES.parameters()


@dataclass(frozen=True)
class Settings:
    source_dir: Path
    db_file: Path

    @classmethod
    def from_env(cls):
        return cls(
            Path(os.getenv("WEIGH_SAMPLE_DIR", ROOT / "sample_data")),
            Path(os.getenv("WEIGH_DB", ROOT / "var/weigh.sqlite3")),
        )
