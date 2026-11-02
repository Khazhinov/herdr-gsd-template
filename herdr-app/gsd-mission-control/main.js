// GSD Mission Control for Herdr App.
//
// Shows the project of the active space, and only when that project runs the
// orchestration hub (`scripts/orch.py hub start`); elsewhere the panel collapses.
//
// Data flow (no polling of the scheduler):
//   the hub terminal (label orch.hub) rewrites .orchestration/runtime/state.json
//   and bumps its orch.rev label on every change. Herdr re-renders mods when
//   terminals() change, so a new revision arrives here at once and the mod reads
//   state.json from the hub's machine. Worker status comes from terminals()
//   (OSC 7501).
import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { terminals, spaces, panes, layout, theme, run, exec, readTextFile, notify } from "herdr";

const NODE = "mission-control";
const STATE_SUFFIX = "/.orchestration/runtime/state.json";
const ROLES = [["execute", "exec"], ["review", "review"], ["plan", "plan"], ["research", "research"], ["debug", "debug"]];
const PROVIDERS = { claude: "Claude", codex: "Codex" };

// ---------------------------------------------------------------- helpers

const machineOf = (a) => (a.indexOf("/") < 0 ? null : a.slice(0, a.indexOf("/")));
const qualify = (m, a) => (!a ? null : m && !a.includes("/") ? `${m}/${a}` : a);
const inside = (path, root) => !!path && (path === root || path.startsWith(root + "/"));
const hasNode = (n, id) => !!n && typeof n === "object" && (n.id === id || (n.children || []).some((c) => hasNode(c, id)));
const pad = (n) => String(n).padStart(2, "0");

function span(sec) {
  const s = Math.max(0, sec);
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  if (s < 172800) return `${Math.round(s / 3600)}h`;
  return `${(s / 86400).toFixed(1)}d`;
}

// The JS runtime has no Intl and formats dates as en-US, so the system's own
// patterns are read once (Windows: Get-Culture) and applied here.
function formatWith(pattern, d, days) {
  const h12 = d.getHours() % 12 || 12;
  const map = {
    yyyy: d.getFullYear(), yy: pad(d.getFullYear() % 100), MM: pad(d.getMonth() + 1), M: d.getMonth() + 1,
    ddd: days[d.getDay()], dd: pad(d.getDate()), d: d.getDate(), HH: pad(d.getHours()), H: d.getHours(),
    hh: pad(h12), h: h12, mm: pad(d.getMinutes()), tt: d.getHours() < 12 ? "AM" : "PM",
  };
  return pattern.replace(/yyyy|yy|MM|M|ddd|dd|d|HH|H|hh|h|mm|tt/g, (k) => String(map[k]));
}

export default class MissionControl extends View {
  init(_props, cx) {
    this.states = {};
    this.open = {};
    this.shown = undefined;
    this.fmt = { time: "HH:mm", date: "dd.MM", days: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] };
    try { this.open = JSON.parse(localStorage.getItem("open") || "{}"); } catch (_) {}
    cx.spawn(async (cx) => {
      try {
        const r = await exec("powershell", ["-NoProfile", "-Command",
          "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $c=(Get-Culture).DateTimeFormat; " +
          "$c.ShortTimePattern; $c.ShortDatePattern; ($c.AbbreviatedDayNames -join ',')"]);
        const [time, date, days] = r.stdout.split(/\r?\n/);
        if (time && date) {
          // Day and month only: the year adds nothing to a reset time.
          const dm = date.replace(/[^dM]*y+[^dM]*/g, "").replace(/^[^dM]+|[^dM]+$/g, "");
          this.fmt = { time: time.trim(), date: dm || "dd.MM", days: days ? days.split(",") : this.fmt.days };
          cx.notify();
        }
      } catch (_) { /* not Windows: keep the 24-hour default */ }
    });
    cx.timer.every(30000, (cx) => cx.notify());
  }

  resetAt(ts) {
    if (!ts) return "?";
    const d = new Date(ts * 1000);
    const now = new Date();
    const same = d.toDateString() === now.toDateString();
    const t = formatWith(this.fmt.time, d, this.fmt.days);
    return same ? t : `${this.fmt.days[d.getDay()]} ${formatWith(this.fmt.date, d, this.fmt.days)} ${t}`;
  }

  toggle(key, cx) {
    this.open[key] = !this.open[key];
    try { localStorage.setItem("open", JSON.stringify(this.open)); } catch (_) {}
    cx.notify();
  }

  // ---------------------------------------------------------------- data

  currentHub() {
    const space = spaces().find((s) => s.active);
    if (!space) return null;
    const tabIds = new Set(space.tabs.map((t) => t.id));
    const cwds = panes().filter((p) => tabIds.has(p.tab)).map((p) => p.cwd).filter(Boolean);
    if (space.folder) cwds.push(space.folder);
    return terminals().find((t) => {
      if (!(t.state === "live" && t.labels && t.labels["orch.hub"] && t.labels["orch.state"])) return false;
      if ((machineOf(t.address) || null) !== (space.machine || null)) return false;
      const root = t.labels["orch.state"].replace(STATE_SUFFIX, "");
      return cwds.some((c) => inside(c, root));
    }) || null;
  }

  // A hidden layout node stops rendering and could never show itself again,
  // so the panel collapses to zero width instead and keeps receiving data.
  syncVisibility(want) {
    if (this.shown === want || !hasNode(layout(), NODE)) return;
    this.shown = want;
    if (want) run("layout.show", { id: NODE });
    run("layout.resize", { id: NODE, px: want ? (this.openWidth || 460) : 0 });
  }

  load(hub, cx) {
    const rev = hub.labels["orch.rev"];
    const st = this.states[hub.address] || (this.states[hub.address] = {});
    if (st.loading || st.rev === rev) return;
    st.loading = true;
    cx.spawn(async (cx) => {
      try {
        const text = await readTextFile(hub.labels["orch.state"], { on: machineOf(hub.address) });
        st.data = text ? JSON.parse(text) : null;
        st.error = text ? null : "state.json missing";
      } catch (e) {
        st.error = String(e);
      }
      st.rev = rev;
      st.loading = false;
      cx.notify();
    });
  }

  orch(hub, args, cx) {
    const data = this.states[hub.address]?.data;
    if (!data) return;
    cx.spawn(async (cx) => {
      const r = await exec("python3", [`${data.root}/scripts/orch.py`, ...args], { cwd: data.root, on: machineOf(hub.address) });
      if (r.code !== 0) notify({ title: "orch.py failed", body: (r.stderr || r.stdout).slice(-300), level: "error" });
      cx.notify();
    });
  }

  // ---------------------------------------------------------------- view

  render(cx) {
    const t = theme();
    const hub = this.currentHub();
    this.syncVisibility(!!hub);
    const root = v_flex().id("mc").size_full().bg(t.chrome).text_color(t.foreground).text_size(12)
      .px(12).py(10).gap(14).overflow_y_scrollbar()
      .on_size_change((size) => { if (size.width > 120) this.openWidth = Math.round(size.width); });
    if (!hub) {
      return root.child(div().text_color(t.dim).child("No orchestration hub here. Template project: python3 scripts/orch.py hub start"));
    }
    this.load(hub, cx);
    const st = this.states[hub.address] || {};
    const s = st.data;
    const m = machineOf(hub.address);
    if (!s) return root.child(div().text_color(st.error ? t.blocked : t.dim).child(st.error || "loading…"));

    const termByTask = {};
    for (const term of terminals()) {
      const id = term.labels && term.labels["orch.task"];
      if (id && term.labels["orch.project"] === s.project && term.state === "live") termByTask[id] = term;
    }
    const running = s.tasks.filter((x) => x.state === "running");
    const p = s.planning && s.planning.available ? s.planning : null;

    root.child(this.header(s, p, hub, t));
    root.child(this.section("Active", t, running.length ? String(running.length) : null,
      running.length ? running.map((x) => this.workerCard(x, termByTask[x.id], m, t))
        : [div().text_color(t.dim).child("No workers running")]));
    const next = this.upNext(p, running);
    if (next.length) {
      root.child(this.section("Up next", t, null, next.map(({ phase, plan }) => this.planRow(phase, plan, null, t, cx, false))));
    }
    if (p) root.child(this.section("Plan", t, p.progress != null ? `${p.progress}%` : null, this.planTree(p, running, t, cx)));
    root.child(this.section("Limits", t, null, this.limits(s, t)));
    root.child(this.section("Routing", t, null, [this.routing(s, hub, t)]));
    const done = s.tasks.filter((x) => x.state !== "running").sort((a, b) => (b.finished_at || 0) - (a.finished_at || 0)).slice(0, 3);
    if (done.length || (s.tools || []).length) root.child(this.section("Recent", t, null, [...done.map((x) => this.doneRow(x, t)),
      ...(s.tools || []).map((tool) => this.toolRow(tool, m, t))]));
    return root;
  }

  header(s, p, hub, t) {
    const sub = p ? [p.milestone, p.phase && `phase ${p.phase}`, p.status].filter(Boolean).join(" · ") : "GSD not available";
    return v_flex().gap(3)
      .child(h_flex().items_center().gap(6)
        .child(div().flex_1().font_semibold().text_size(13.5).truncate().child(s.project))
        .child(this.pill(`owner ${s.owner}`, t))
        .child(div().id("hub").text_color(t.dim).text_size(11).tooltip("Peek at the hub terminal")
          .on_click(() => run("terminal.peek", { terminal: hub.address }))
          .child(`${span(Date.now() / 1000 - s.updated_at)} ago`)))
      .child(div().text_color(t.muted).truncate().child(sub))
      .when(Boolean(p && p.stopped_at), (el) => el.child(div().text_color(t.dim).truncate().child(`stopped at ${p.stopped_at}`)));
  }

  section(title, t, badge, children) {
    return v_flex().gap(6)
      .child(h_flex().items_center().gap(6)
        .child(div().text_size(10.5).font_semibold().text_color(t.dim).child(title.toUpperCase()))
        .when(Boolean(badge), (el) => el.child(div().text_size(10.5).text_color(t.muted).child(badge)))
        .child(div().flex_1().h(1).bg(t.border)))
      .children(children);
  }

  pill(text, t, color) {
    return div().px(6).py(1).rounded(8).bg(t.raised).text_size(10.5).text_color(color || t.muted).child(text);
  }

  dot(color, size = 7) {
    return div().size(size).rounded(size).bg(color);
  }

  statusColor(s, t) {
    return { working: t.working, blocked: t.blocked, done: t.done, idle: t.idle, error: t.blocked }[s] || t.unknown;
  }

  // ---- active workers: one compact row each, status + what the agent says
  workerCard(x, term, m, t) {
    const addr = term ? term.address : qualify(m, x.live && x.live.address);
    // Programs that report no OSC status have status null.
    const status = (term ? term.status : x.live && x.live.status) || (term ? "running" : "gone");
    const msg = term && term.report && term.report.msg;
    const elapsed = x.started_at ? span(Date.now() / 1000 - x.started_at) : "";
    const icon = (id, label, fn, color) => div().id(id).px(6).rounded(5).text_size(11).text_color(color || t.muted)
      .hover((el) => el.bg(t.hover).text_color(color || t.foreground)).on_click(fn).child(label);
    return v_flex().id(`w-${x.id}`).gap(1).px(6).py(4).rounded(6).hover((el) => el.bg(t.hover))
      .when(status === "blocked", (el) => el.bg(t.surface))
      .child(h_flex().items_center().gap(6)
        .child(this.dot(this.statusColor(status, t)))
        .child(div().font_semibold().child(x.id))
        .child(div().flex_1().truncate().text_color(status === "blocked" ? t.blocked : t.muted)
          .child(msg || (status === "blocked" ? "waiting for a person" : status)))
        .when(Boolean(term && addr), (el) => el
          .child(icon(`o-${x.id}`, "open", () => run("agent.focus", { terminal: addr })))
          .child(icon(`p-${x.id}`, "peek", () => run("terminal.peek", { terminal: addr })))
          .child(icon(`k-${x.id}`, "stop", () => run("terminal.kill", { terminal: addr }), t.blocked))))
      .child(div().pl(13).text_size(10.5).text_color(t.dim).child(`${x.agent} · ${x.role} · ${elapsed}`));
  }

  // ---- nearest plans that are neither done nor running
  upNext(p, running) {
    if (!p) return [];
    const busy = new Set(running.map((x) => x.id));
    const out = [];
    for (const ph of p.phases || []) {
      if (ph.complete) continue;
      const plans = [...(ph.plans || [])].sort((a, b) => (a.wave || 0) - (b.wave || 0));
      for (const pl of plans) if (!pl.complete && !busy.has(pl.id)) out.push({ phase: ph, plan: pl });
      if (out.length >= 3) break;
    }
    return out.slice(0, 3);
  }

  // ---- phase > wave > plan > task, as deep as GSD knows it
  planTree(p, running, t, cx) {
    const busy = new Set(running.map((x) => x.id));
    const rows = [];
    for (const ph of p.phases || []) {
      const key = `ph-${ph.id}`;
      const current = String(ph.id) === String(p.phase);
      const isOpen = this.open[key] ?? current;
      const plans = ph.plans || [];
      const doneN = plans.filter((x) => x.complete).length;
      const glyph = ph.complete ? "✓" : current ? "●" : "○";
      const color = ph.complete ? t.done : current ? t.accent : t.dim;
      rows.push(h_flex().id(key).items_center().gap(6).py(1).rounded(4).hover((x) => x.bg(t.hover))
        .on_click((_e, cx) => this.toggle(key, cx))
        .child(div().w(10).text_color(t.dim).child(plans.length ? (isOpen ? "▾" : "▸") : ""))
        .child(div().w(12).text_color(color).child(glyph))
        .child(div().w(22).text_color(t.muted).child(ph.id))
        .child(div().flex_1().truncate().text_color(ph.complete ? t.muted : t.foreground).child(ph.name || ""))
        .child(div().text_size(10.5).text_color(t.dim).child(plans.length ? `${doneN}/${plans.length}` : this.phaseState(ph))));
      if (!isOpen || !plans.length) continue;
      const waves = {};
      for (const pl of plans) (waves[pl.wave || 0] = waves[pl.wave || 0] || []).push(pl);
      for (const w of Object.keys(waves).sort((a, b) => a - b)) {
        rows.push(div().pl(28).text_size(10.5).text_color(t.dim).child(Number(w) ? `Wave ${w}` : "Plans"));
        for (const pl of waves[w]) rows.push(this.planRow(ph, pl, busy, t, cx, true));
      }
    }
    return rows;
  }

  phaseState(ph) {
    return { no_directory: "not planned", discussed: "discussed", researched: "researched" }[ph.status] || ph.status || "";
  }

  planRow(ph, pl, busy, t, cx, nested) {
    const key = `pl-${pl.id}`;
    const working = busy && busy.has(pl.id);
    const tasks = pl.tasks || [];
    const doneT = pl.complete ? tasks.length : tasks.filter((x) => x.status === "done").length;
    const isOpen = !!this.open[key];
    const row = v_flex().gap(1)
      .child(h_flex().id(key).items_center().gap(6).pl(nested ? 28 : 0).py(1).rounded(4).hover((x) => x.bg(t.hover))
        .on_click((_e, cx) => this.toggle(key, cx))
        .child(div().w(12).text_color(pl.complete ? t.done : working ? t.working : t.dim)
          .child(pl.complete ? "✓" : working ? "◐" : "○"))
        .child(div().w(40).text_color(t.muted).child(pl.id))
        .child(div().flex_1().truncate().text_color(pl.complete ? t.muted : t.foreground).child(pl.title || ""))
        .when(!nested && pl.wave != null, (el) => el.child(this.pill(`w${pl.wave}`, t)))
        .child(div().text_size(10.5).text_color(t.dim).child(tasks.length ? `${doneT}/${tasks.length}` : "")));
    if (isOpen) {
      for (const task of tasks) {
        const done = pl.complete || task.status === "done";
        row.child(h_flex().gap(6).pl(nested ? 46 : 18)
          .child(div().w(12).text_color(done ? t.done : task.checkpoint ? t.ansi3 : t.dim).child(done ? "✓" : task.checkpoint ? "◆" : "·"))
          .child(div().flex_1().truncate().text_size(11).text_color(done ? t.dim : t.muted).child(task.name || `task ${task.n}`)));
      }
    }
    return row;
  }

  // ---- limits per agent environment, with the exact reset time
  limits(s, t) {
    const out = [];
    for (const [kind, q] of Object.entries(s.providers || {})) {
      const state = !q.available ? "unknown" : q.stale ? `stale · ${span(Date.now() / 1000 - q.observed_at)} ago` : "";
      out.push(h_flex().items_center().gap(6)
        .child(div().font_semibold().child(PROVIDERS[kind] || kind))
        .when(Boolean(state), (el) => el.child(div().text_size(10.5).text_color(q.stale ? t.blocked : t.dim).child(state)))
        .child(div().flex_1())
        .when(Boolean(q.extra && q.extra.reset_credits_available),
          (el) => el.child(this.pill(`${q.extra.reset_credits_available} resets`, t))));
      for (const w of q.windows || []) {
        const pct = Math.max(0, Math.min(100, w.remaining_percent));
        const col = pct <= 15 ? t.blocked : pct <= 35 ? t.ansi3 : t.done;
        out.push(h_flex().id(`q-${kind}-${w.name}`).items_center().gap(8)
          .tooltip(`${w.name} window: ${Math.round(w.used_percent)}% used, resets in ${span((w.resets_at || 0) - Date.now() / 1000)}`)
          .child(div().w(22).text_color(t.dim).child(w.name))
          .child(div().flex_1().h(5).rounded(3).bg(t.surface)
            .child(div().h(5).rounded(3).bg(col).w(`${Math.max(1, Math.round(pct))}%`)))
          .child(div().w(34).child(`${Math.round(pct)}%`))
          .child(div().w(110).text_color(t.muted).text_size(11).child(this.resetAt(w.resets_at))));
      }
      if (!q.available) out.push(div().text_color(t.dim).truncate().child((q.extra && q.extra.reason) || "no quota source"));
    }
    return out;
  }

  routing(s, hub, t) {
    const grid = h_flex().flex_wrap().gap(6);
    for (const [role, short] of ROLES) {
      const d = s.routing[role];
      if (!d) continue;
      const over = s.override && s.override[role];
      grid.child(h_flex().id(`r-${role}`).items_center().gap(4).px(6).py(2).rounded(6).bg(t.surface)
        .tooltip(d.reason)
        .child(div().text_size(10.5).text_color(t.dim).child(short))
        .child(div().text_size(11).text_color(d.selected ? (over ? t.ansi3 : t.foreground) : t.blocked)
          .child(d.selected || "none"))
        .when(d.independent === false, (el) => el.child(div().text_color(t.ansi3).child("!"))));
    }
    const overrides = Object.keys(s.override || {});
    if (overrides.length) {
      grid.child(this.button("clear-ov", "Clear override", t, (cx) => {
        for (const role of overrides) this.orch(hub, ["prefer", role, "-"], cx);
      }));
    }
    return grid;
  }

  doneRow(x, t) {
    const ok = x.state === "complete";
    return h_flex().gap(6).items_center()
      .child(div().w(12).text_color(ok ? t.done : t.blocked).child(ok ? "✓" : "!"))
      .child(div().w(120).truncate().child(x.id))
      .child(div().flex_1().truncate().text_color(t.dim).text_size(11).child(`${x.agent} · ${x.verdict || x.state}`));
  }

  toolRow(tool, m, t) {
    const addr = qualify(m, tool.address);
    return h_flex().id(`tool-${tool.name}`).gap(6).items_center().rounded(4).hover((x) => x.bg(t.hover))
      .on_click(() => run("terminal.peek", { terminal: addr }))
      .child(this.dot(this.statusColor(tool.status, t), 6))
      .child(div().flex_1().truncate().child(tool.tool))
      .child(div().text_size(11).text_color(t.dim).child(`tool · ${tool.status || tool.state}`));
  }

  button(id, label, t, fn, color) {
    return div().id(id).px(8).py(1).rounded(6).bg(t.raised).text_size(11).text_color(color || t.foreground)
      .hover((x) => x.bg(t.hover)).on_click((_e, cx) => fn(cx)).child(label);
  }
}
