"""升级影响比对：同一来源在旧规则归档结果与新规则重算结果之间逐车次核对。

结论一致的车次记为 unchanged（保持原样）；结论变化的车次记为 changed（需重核），
并给出变化起点阶段与依据：轮载修正、证据隔离、轴组、偏载和整车勾稽的逐项差异。
"""

STAGES = ("calibration", "debounce", "axles", "balance", "reconcile")


def _wheels(results, pass_id):
    return {
        wheel["trigger"]["id"]: wheel
        for wheel in results["calibration"]["wheels"]
        if wheel["trigger"]["pass_id"] == pass_id
    }


def _issues(results, stage, pass_id):
    return sorted(
        (issue["code"], issue["source"]["ref"])
        for issue in results[stage]["issues"]
        if issue["pass_id"] == pass_id
    )


def _evidence(results, pass_id):
    items = [(issue["code"], issue["source"]["ref"]) for issue in results["quarantine"]
             if issue["pass_id"] == pass_id]
    items += [(issue["code"], issue["source"]["ref"]) for issue in results["debounce"]["duplicates"]
              if issue["pass_id"] == pass_id]
    return sorted(items)


def _axes(results, pass_id):
    return sorted(axis["id"] for axis in results["axles"]["axes"] if axis["pass_id"] == pass_id)


def _grades(results, pass_id):
    return {row["id"]: row["level"] for row in results["balance"]["rows"] if row["pass_id"] == pass_id}


def _ledger_row(results, pass_id):
    return next(row for row in results["reconcile"]["rows"] if row["pass_id"] == pass_id)


def _stage_snapshot(results, stage, pass_id):
    if stage == "calibration":
        wheels = sorted((key, wheel["kg"], wheel["cert"]) for key, wheel in _wheels(results, pass_id).items())
        return wheels, _issues(results, "calibration", pass_id)
    if stage == "debounce":
        kept = sorted(wheel["trigger"]["id"] for wheel in results["debounce"]["kept"]
                      if wheel["trigger"]["pass_id"] == pass_id)
        duplicates = sorted((issue["code"], issue["source"]["ref"], issue["kept_id"])
                            for issue in results["debounce"]["duplicates"] if issue["pass_id"] == pass_id)
        return kept, duplicates, _issues(results, "debounce", pass_id)
    if stage == "axles":
        axes = sorted(
            (axis["id"], axis["group"], axis["total_kg"], axis["left"]["kg"], axis["right"]["kg"])
            for axis in results["axles"]["axes"] if axis["pass_id"] == pass_id
        )
        return axes, _issues(results, "axles", pass_id)
    if stage == "balance":
        return sorted(
            (row["id"], row["level"], row["percent"])
            for row in results["balance"]["rows"] if row["pass_id"] == pass_id
        )
    row = _ledger_row(results, pass_id)
    return row["status"], tuple(row["codes"]), row["wheel_kg"], row["difference_kg"]


def _conclusion(results, pass_id):
    row = _ledger_row(results, pass_id)
    axes = _axes(results, pass_id)
    counts = {"pass": 0, "warn": 0, "severe": 0}
    for level in _grades(results, pass_id).values():
        counts[level] += 1
    groups = {axis["group"] for axis in results["axles"]["axes"] if axis["pass_id"] == pass_id}
    return {
        "status": row["status"],
        "codes": row["codes"],
        "wheel_kg": row["wheel_kg"],
        "difference_kg": row["difference_kg"],
        "axles": len(axes),
        "groups": len(groups),
        "balance": counts,
    }


def _basis(old, new, pass_id):
    old_wheels, new_wheels = _wheels(old, pass_id), _wheels(new, pass_id)
    wheels = []
    for key in sorted(old_wheels.keys() | new_wheels.keys()):
        before, after = old_wheels.get(key), new_wheels.get(key)
        if before and after and before["kg"] == after["kg"] and before["cert"] == after["cert"]:
            continue
        shown = before or after
        wheels.append({
            "trigger": key,
            "side": shown["trigger"]["side"],
            "ref": shown["trigger"]["source"]["ref"],
            "old_kg": before["kg"] if before else None,
            "new_kg": after["kg"] if after else None,
            "old_cert": before["cert"] if before else None,
            "new_cert": after["cert"] if after else None,
        })
    old_evidence, new_evidence = _evidence(old, pass_id), _evidence(new, pass_id)
    issues = [{"code": code, "ref": ref, "change": "removed"}
              for code, ref in old_evidence if (code, ref) not in new_evidence]
    issues += [{"code": code, "ref": ref, "change": "added"}
               for code, ref in new_evidence if (code, ref) not in old_evidence]
    old_grades, new_grades = _grades(old, pass_id), _grades(new, pass_id)
    balance = [
        {"axle": key, "old": old_grades.get(key), "new": new_grades.get(key)}
        for key in sorted(old_grades.keys() | new_grades.keys())
        if old_grades.get(key) != new_grades.get(key)
    ]
    before, after = _ledger_row(old, pass_id), _ledger_row(new, pass_id)
    return {
        "wheels": wheels,
        "issues": issues,
        "axles": {"old": _axes(old, pass_id), "new": _axes(new, pass_id)},
        "balance": balance,
        "reconcile": {
            "old_status": before["status"], "new_status": after["status"],
            "old_codes": before["codes"], "new_codes": after["codes"],
            "old_wheel_kg": before["wheel_kg"], "new_wheel_kg": after["wheel_kg"],
            "old_difference_kg": before["difference_kg"], "new_difference_kg": after["difference_kg"],
        },
    }


def _entry(old, new, pass_id, plate):
    before, after = _conclusion(old, pass_id), _conclusion(new, pass_id)
    if before == after:
        return {"pass_id": pass_id, "plate": plate, "impact": "unchanged",
                "origin": None, "old": before, "new": after, "basis": None}
    origin = next(
        stage for stage in STAGES
        if _stage_snapshot(old, stage, pass_id) != _stage_snapshot(new, stage, pass_id)
    )
    return {"pass_id": pass_id, "plate": plate, "impact": "changed",
            "origin": origin, "old": before, "new": after, "basis": _basis(old, new, pass_id)}


def impact_entries(old, new):
    """逐车次比对归档结果与重算结果，返回 (明细, 汇总)。车次顺序按归档勾稽账。"""
    entries = [
        _entry(old, new, row["pass_id"], row["plate"])
        for row in old["reconcile"]["rows"]
    ]
    changed = sum(entry["impact"] == "changed" for entry in entries)
    return entries, {"passes": len(entries), "changed": changed, "unchanged": len(entries) - changed}
