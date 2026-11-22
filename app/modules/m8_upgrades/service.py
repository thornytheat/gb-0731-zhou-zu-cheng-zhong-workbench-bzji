from app.errors import DomainError
from app.manifest import canonical, clock, digest
from app.modules.m7_batches.pipeline import run_pipeline
from app.modules.m8_upgrades.impact import impact_entries
from app.modules.m8_upgrades.ruleset import target_rules
from app.sources import read_sources
from app.store import add_events, add_order, find_order


def _order_id(run_id, rules):
    key = {"run_id": run_id, "rules": rules.version, "parameters": rules.parameters()}
    return digest(canonical(key).encode("utf-8"))


def assess_upgrade(store, source_dir, run_id, version, overrides):
    """对归档批次出具升级复核单。

    复核单号由批次、目标版本与参数唯一决定：同一升级重复提交直接沿用原单，
    重算或写库失败时不写任何内容，已发出的复核单保持原样。
    """
    rules = target_rules(version, overrides)
    manifest, archived = store.read(run_id)
    if manifest["rules"] == rules.version and manifest["parameters"] == rules.parameters():
        raise DomainError("UPGRADE_NOOP")
    order_id = _order_id(run_id, rules)
    with store.transaction() as db:
        existing = find_order(db, order_id)
        if existing:
            add_events(db, run_id, [(clock(), "info", "UPGRADE_REUSED", f"复核单 {order_id[:12]} 已出具", None)])
            return existing, True
        sources = read_sources(source_dir, manifest["sample"])
        for role, source in sources.items():
            if digest(source.content) != manifest["files"][role]["sha256"]:
                raise DomainError("SOURCE_CHANGED", 409, file=source.name)
        recomputed = run_pipeline(sources, rules=rules)
        entries, summary = impact_entries(archived, recomputed)
        order = {
            "order_id": order_id,
            "created_at": clock(),
            "run_id": run_id,
            "sample": manifest["sample"],
            "from": {"rules": manifest["rules"], "parameters": manifest["parameters"]},
            "to": {"rules": rules.version, "parameters": rules.parameters()},
            "parameter_changes": [
                {"name": name, "old": manifest["parameters"].get(name), "new": value}
                for name, value in rules.parameters().items()
                if manifest["parameters"].get(name) != value
            ],
            "files": manifest["files"],
            "summary": summary,
            "entries": entries,
        }
        add_order(db, order)
        add_events(db, run_id, [(
            order["created_at"], "ok", "UPGRADE_ISSUED",
            f"复核单 {order_id[:12]} · {manifest['rules']} → {rules.version} · "
            f"重核 {summary['changed']}/{summary['passes']} 车次",
            None,
        )])
        return order, False
