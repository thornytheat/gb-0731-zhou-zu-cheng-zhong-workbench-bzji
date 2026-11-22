export const byId = (id) => document.getElementById(id);

export function element(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

const timeFormat = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai", hourCycle: "h23", hour: "2-digit", minute: "2-digit", second: "2-digit",
  fractionalSecondDigits: 3,
});
const dateFormat = new Intl.DateTimeFormat("zh-CN", {timeZone: "Asia/Shanghai", dateStyle: "short"});

export function clock(value) {
  return timeFormat.format(new Date(value.replace(/(\.\d{3})\d+Z$/, "$1Z")));
}

export function dateTime(value) {
  return `${dateFormat.format(new Date(value.replace(/(\.\d{3})\d+Z$/, "$1Z")))} ${clock(value)}`;
}

const col = (label, read, numeric = false) => ({label, read, numeric});
const source = (obj) => obj.source.ref;
const joined = (list) => list?.join(" / ");
const labels = {pass: "正常", warn: "偏载", severe: "严重", matched: "已核平", review: "待复秤"};
const styles = {pass: "ok", warn: "warn", severe: "bad", matched: "ok", review: "warn"};
const displayStatus = (level) => ({text: labels[level], level: styles[level]});
const impactLabels = {changed: "需重核", unchanged: "保持原样"};
const impactStyles = {changed: "warn", unchanged: "ok"};
const originLabels = {calibration: "轮载修正", debounce: "脉冲去抖", axles: "轴组重建", balance: "偏载判级", reconcile: "整车勾稽"};
const conclusionText = (c) => `${labels[c.status]}${c.codes.length ? " · " + c.codes.join("/") : ""}`;

function basisText(entry) {
  const basis = entry.basis;
  if (!basis) return "结论一致";
  const parts = [];
  if (basis.wheels.length) {
    parts.push(`轮载 ${basis.wheels.map((w) => `${w.trigger} ${w.old_kg ?? "—"}→${w.new_kg ?? "隔离"}`).join("，")}`);
  }
  if (basis.issues.length) {
    parts.push(`证据 ${basis.issues.map((i) => `${i.change === "added" ? "+" : "−"}${i.code}`).join(" ")}`);
  }
  if (basis.axles.old.join() !== basis.axles.new.join()) parts.push(`轴 ${basis.axles.old.length}→${basis.axles.new.length}`);
  if (basis.balance.length) {
    parts.push(`偏载 ${basis.balance.map((b) => `${b.axle.split("/").at(-1)} ${labels[b.old] ?? "—"}→${labels[b.new] ?? "撤销"}`).join("，")}`);
  }
  const recon = basis.reconcile;
  if (recon.old_status !== recon.new_status) parts.push(`${labels[recon.old_status]}→${labels[recon.new_status]}`);
  return parts.join(" · ") || "—";
}

const issueColumns = [
  col("车次", (r) => r.pass_id), col("原因码", (r) => r.code), col("说明", (r) => r.message),
  col("源文件行", source), col("关联证据", (r) => joined(r.related)), col("保留记录", (r) => r.kept_id),
  col("原始字段", (r) => joined(r.source.cells)),
];
const wheelColumns = [
  col("记录号", (r) => r.trigger.id), col("车次", (r) => r.trigger.pass_id),
  col("轮道", (r) => r.trigger.side), col("记录时刻", (r) => clock(r.trigger.time)),
  col("原轮载 kg", (r) => r.trigger.raw_kg, true), col("修正轮载 kg", (r) => r.kg, true),
  col("标定证书", (r) => r.cert), col("证书行", (r) => r.cert_ref), col("触发行", (r) => source(r.trigger)),
];

export function moduleViews(name, snapshot, history, upgrade) {
  const data = snapshot?.data;
  const stage = data?.[name];
  switch (name) {
    case "intake": return {summary: stage ? `${stage.encoding} · ${stage.segments} 段 · ${stage.blank} 空行 · ${stage.late} 乱序` : "", views: [
      ["采样记录", stage?.accepted, [
        col("记录号", (r) => r.id), col("车次", (r) => r.pass_id), col("轮道", (r) => r.side),
        col("采样时间", (r) => dateTime(r.time)), col("原轮载 kg", (r) => r.raw_kg, true),
        col("顺序", (r) => r.late ? "乱序" : "顺序"), col("源文件行", source),
        col("原始字段", (r) => joined(r.source.cells)),
      ]], ["采样隔离", stage?.issues, issueColumns],
    ]};
    case "calibration": return {summary: stage ? `${stage.wheels.length} 条修正 · ${stage.issues.length} 条隔离` : "", views: [
      ["修正轮载", stage?.wheels, wheelColumns],
      ["标定证书", stage?.certificates, [
        col("证书", (r) => r.id), col("轮道", (r) => r.side), col("生效", (r) => dateTime(r.start)),
        col("失效", (r) => dateTime(r.end)), col("增益", (r) => r.gain, true),
        col("偏置 kg", (r) => r.bias_kg, true), col("源文件行", source),
      ]], ["标定隔离", stage?.issues, issueColumns],
    ]};
    case "debounce": return {summary: stage ? `${stage.kept.length} 条保留 · ${stage.duplicates.length} 条重复` : "", views: [
      ["保留触发", stage?.kept, wheelColumns], ["重复触发", stage?.duplicates, issueColumns],
      ["记录冲突", stage?.issues, issueColumns],
    ]};
    case "axles": return {summary: stage ? `${stage.axes.length} 轴 · ${stage.groups} 轴组` : "", views: [
      ["确认车轴", stage?.axes, [
        col("轴号", (r) => r.id), col("轴组", (r) => r.group), col("轴时刻", (r) => clock(r.time)),
        col("轴距 m", (r) => r.gap_m, true), col("右减左 ms", (r) => r.skew_ms, true),
        col("左轮 kg", (r) => r.left.kg, true), col("右轮 kg", (r) => r.right.kg, true),
        col("轴重 kg", (r) => r.total_kg, true), col("左轮证据", (r) => source(r.left.trigger)),
        col("右轮证据", (r) => source(r.right.trigger)),
      ]], ["轴组隔离", stage?.issues, issueColumns],
    ]};
    case "balance": return {summary: stage ? `${stage.counts.pass} 正常 · ${stage.counts.warn} 偏载 · ${stage.counts.severe} 严重` : "", views: [
      ["偏载结果", stage?.rows, [
        col("轴号", (r) => r.id), col("判级", (r) => displayStatus(r.level)),
        col("左轮 kg", (r) => r.left_kg, true), col("右轮 kg", (r) => r.right_kg, true),
        col("偏载率 %", (r) => r.percent, true), col("重侧", (r) => ({L: "左", R: "右"})[r.heavy]),
        col("左轮证据", (r) => r.left_ref), col("右轮证据", (r) => r.right_ref),
      ]],
    ]};
    case "reconcile": return {summary: stage ? `${stage.ledger.matched} 核平 · ${stage.ledger.review} 待复秤` : "", views: [
      ["勾稽结果", stage?.rows, [
        col("车次", (r) => r.pass_id), col("车牌", (r) => r.plate), col("状态", (r) => displayStatus(r.status)),
        col("磅单", (r) => r.ticket?.id), col("版次", (r) => r.ticket?.revision, true),
        col("静态总重 kg", (r) => r.ticket?.kg, true), col("有效轮载 kg", (r) => r.wheel_kg, true),
        col("差额 kg", (r) => r.difference_kg, true), col("原因码", (r) => joined(r.codes)),
        col("磅单证据", (r) => joined(r.ticket_refs)), col("轮载证据", (r) => joined(r.wheel_refs)),
        col("复秤证据", (r) => joined(r.review_refs)),
      ]], ["磅单隔离", stage?.ticket_issues, issueColumns], ["触发隔离汇总", data?.quarantine, issueColumns],
    ]};
    case "batches": return {summary: `${history.length} 条归档`, views: [
      ["归档批次", history, [
        col("批次号", (r) => ({text: r.run_id.slice(0, 12), run: r.run_id})),
        col("数据源", (r) => r.files.triggers.file), col("规则版本", (r) => r.rules),
        col("归档时间", (r) => dateTime(r.created_at)), col("用时 ms", (r) => r.elapsed_ms, true),
        col("触发数", (r) => r.ledger.raw, true), col("待复秤", (r) => r.ledger.review, true),
      ]], ["输入文件", Object.values(snapshot?.manifest?.files ?? {}), [
        col("源文件", (r) => r.file), col("字节数", (r) => r.bytes, true), col("SHA-256", (r) => r.sha256),
      ]],
    ]};
    case "upgrades": {
      const orders = upgrade?.orders ?? [];
      const order = upgrade?.order ?? null;
      const head = order ? `复核单 ${order.order_id.slice(0, 12)} · 重核 ${order.summary.changed}/${order.summary.passes} 车次` : `${orders.length} 份复核单`;
      return {summary: head, views: [
        ["复核单", orders, [
          col("复核单", (r) => ({text: r.order_id.slice(0, 12), order: r.order_id})),
          col("批次", (r) => r.run_id.slice(0, 12)),
          col("规则升级", (r) => `${r.from_rules} → ${r.to_rules}`),
          col("参数变化", (r) => r.parameter_changes, true),
          col("需重核", (r) => r.summary.changed, true),
          col("保持原样", (r) => r.summary.unchanged, true),
          col("出单时间", (r) => dateTime(r.created_at)),
        ]],
        ["车次影响", order?.entries, [
          col("车次", (r) => r.pass_id), col("车牌", (r) => r.plate),
          col("结论", (r) => ({text: impactLabels[r.impact], level: impactStyles[r.impact]})),
          col("变化起点", (r) => originLabels[r.origin]),
          col("旧结论", (r) => conclusionText(r.old)),
          col("复核后结论", (r) => conclusionText(r.new)),
          col("旧差额 kg", (r) => r.old.difference_kg, true),
          col("新差额 kg", (r) => r.new.difference_kg, true),
          col("依据", basisText),
        ]],
        ["参数变化", order?.parameter_changes, [
          col("参数", (r) => r.name), col("旧值", (r) => String(r.old ?? "—")), col("新值", (r) => String(r.new)),
        ]],
      ]};
    }
    default: throw new Error("模块不存在");
  }
}

function valueText(value) {
  return value && typeof value === "object" ? value.text : value ?? "";
}

export function renderTable(view, query) {
  const [, rows = [], columns] = view;
  const matches = [];
  for (const row of rows) {
    const values = columns.map((column) => column.read(row));
    if (!query || values.some((value) => String(valueText(value)).toLowerCase().includes(query))) matches.push(values);
  }
  const host = byId("evidence-table");
  byId("table-count").textContent = `${matches.length} / ${rows.length} 条`;
  if (!matches.length) {
    host.replaceChildren(element("p", query ? "没有匹配记录。" : "暂无记录。", "empty"));
    return;
  }
  const table = element("table", "", "ledger");
  const header = table.createTHead().insertRow();
  for (const column of columns) {
    const th = element("th", column.label, column.numeric ? "num" : "");
    th.scope = "col";
    header.append(th);
  }
  const body = table.createTBody();
  for (const values of matches) {
    const row = body.insertRow();
    for (const [index, value] of values.entries()) {
      const td = row.insertCell();
      const text = String(valueText(value));
      td.title = text;
      if (columns[index].numeric) td.className = "num";
      if (value?.level) {
        td.append(element("i", "", `lamp ${value.level}`), text);
      } else if (value?.run || value?.order) {
        const button = element("button", text);
        button.type = "button";
        if (value.run) button.dataset.run = value.run;
        else button.dataset.order = value.order;
        button.title = value.run ?? value.order;
        td.append(button);
      } else {
        td.textContent = text || "—";
      }
    }
  }
  host.replaceChildren(table);
}

function track(side, value, maximum) {
  const wrap = element("div", "", `load-track ${side}`);
  const label = element("span", value, "num");
  const bed = element("div", "", "bar-bed");
  const bar = element("i", "", "load-bar");
  bar.style.setProperty("--amount", `${Number(value) / maximum * 100}%`);
  bed.append(bar);
  wrap.append(label, bed);
  return wrap;
}

export function renderChart(data, passId) {
  const axes = data?.axles.axes.filter((axis) => axis.pass_id === passId) ?? [];
  const host = byId("load-chart");
  const match = data?.reconcile.rows.find((row) => row.pass_id === passId);
  byId("load-summary").replaceChildren(element("span", `${axes.length} 根确认车轴`),
    element("span", match ? `有效合计 ${match.wheel_kg} kg` : "—"));
  if (!axes.length) {
    host.replaceChildren(element("p", "暂无确认车轴。", "empty"));
    return;
  }
  const maximum = Math.ceil(Math.max(...axes.flatMap((axis) => [Number(axis.left.kg), Number(axis.right.kg)])) / 1000) * 1000;
  const axisScale = element("div", "", "load-scale");
  axisScale.append(...["轴号", `左轮 ${maximum}`, "│", `${maximum} 右轮`, "kg"].map((item) => element("span", item)));
  const frag = document.createDocumentFragment();
  frag.append(axisScale);
  const grades = new Map(data.balance.rows.map((row) => [row.id, row]));
  for (const axis of axes) {
    const grade = grades.get(axis.id);
    const state = displayStatus(grade.level);
    const row = element("div", "", "load-row");
    row.append(element("span", axis.id.split("/").at(-1), "axis-tag"), track("left", axis.left.kg, maximum),
      element("i", "", "load-axis-line"), track("right", axis.right.kg, maximum),
      element("span", state.text, `load-grade level-${state.level}`));
    row.title = `${axis.id} · 左 ${source(axis.left.trigger)} · 右 ${source(axis.right.trigger)}`;
    frag.append(row);
  }
  host.replaceChildren(frag);
}
