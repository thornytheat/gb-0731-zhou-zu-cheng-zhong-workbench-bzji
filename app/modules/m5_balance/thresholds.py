from app.config import STANDARD_RULES
from app.values import rounded


def grade(left, right, rules=STANDARD_RULES):
    total, difference = left + right, abs(left - right)
    if difference >= total * rules.severe_ratio:
        level = "severe"
    elif difference >= total * rules.notice_ratio:
        level = "warn"
    else:
        level = "pass"
    return level, rounded(difference * 100 / total)
