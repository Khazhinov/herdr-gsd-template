// GSD Mission Control for Herdr App.
//
// Data flow (no polling of the scheduler):
//   `scripts/orch.py watch` runs in a terminal labeled orch.hub=<project>.
//   On every change it rewrites .orchestration/runtime/state.json and bumps
//   the terminal's orch.rev / orch.q.* labels. Herdr re-renders mods whenever
//   terminals() change, so a new orch.rev arrives here at once; the mod then
//   reads state.json from the hub's machine. Live worker status comes straight
//   from terminals() (OSC 7501 reports), never from the file.
//
// Every control acts: focus/peek a worker, stop a worker, prefer an agent for
// the next execute task, clear the override. Missing data renders "unknown".
import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { terminals, theme, run, exec, readTextFile, notify } from "herdr";

const ROLES = ["execute", "review", "plan", "research", "debug"];

function machineOf(address) {
  const i = address.indexOf("/");
  return i < 0 ? null : address.slice(0, i);
}

function qualify(machine, address) {
  if (!address) return null;
  return machine && !address.includes("/") ? `${machine}/${address}` : address;
}

function ago(ts) {
  if (!ts) return "?";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return `${Math.round(s)}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

function until(ts) {
  if (!ts) return "?";
  const s = ts - Date.now() / 1000;
  if (s <= 0) return "now";
  if (s < 5400) return `${Math.round(s / 60)}m`;
  if (s < 172800) return `${Math.round(s / 3600)}h`;
  return `${(s / 86400).toFixed(1)}d`;
}

export default class MissionControl extends View {
  init(_props, cx) {
    this.states = {};   // hub address -> { rev, data, error, loading }
    this.selected = null;
    try { this.selected = localStorage.getItem("hub"); } catch (_) {}
    // Reset countdowns and "updated ago" change with time, not with data.
    cx.timer.every(30000, (cx) => cx.notify());
  }

  hubs() {
    return terminals().filter((t) => t.state === "live" && t.labels && t.labels["orch.hub"]);
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
      const r = await exec("python3", [`${data.root}/scripts/orch.py`, ...args],
        { cwd: data.root, on: machineOf(hub.address) });
      if (r.code !== 0) notify({ title: "orch.py failed", body: (r.stderr || r.stdout).slice(-300), level: "error" });
      cx.notify();
    });
  }

  render(cx) {
    const t = theme();
    const hubs = this.hubs();
    for (const h of hubs) this.load(h, cx);
    const root = v_flex().id("mc").size_full().bg(t.chrome).text_color(t.foreground).text_size(12.5)
      .p(10).gap(10).overflow_y_scrollbar()
      .on_size_change((size, cx) => { if (size.width !== this.width) { this.width = size.width; cx.notify(); } });
    if (!hubs.length) {
      return root.child(div().font_semibold().child("GSD Mission Control"))
        .child(div().text_color(t.muted).child("No orchestration hub is running. In the project, start:"))
        .child(div().text_color(t.accent).child("python3 scripts/orch.py watch"));
    }
    const hub = hubs.find((h) => h.address === this.selected) || hubs[0];
    const st = this.states[hub.address] || {};
    const s = st.data;
    const m = machineOf(hub.address);

    if (hubs.length > 1) {
      root.child(h_flex().gap(6).flex_wrap().children(hubs.map((h) =>
        div().id(`hub-${h.address}`).px(8).py(2).rounded(4)
          .bg(h === hub ? t.selected : t.surface)
          .on_click((_e, cx) => { this.selected = h.address; try { localStorage.setItem("hub", h.address); } catch (_) {} cx.notify(); })
          .child(h.labels["orch.hub"]))));
    }
    root.child(v_flex().gap(2)
      .child(div().font_semibold().text_size(14).child(`GSD Mission Control · ${hub.labels["orch.hub"]}`))
      .child(div().id("hub-focus").text_color(t.dim).tooltip("Peek at the watch terminal")
        .on_click(() => run("terminal.peek", { terminal: hub.address }))
        .child(s ? `owner ${s.owner} · ${ago(s.updated_at)} ago` : "loading…")));
    if (st.error) root.child(div().text_color(t.blocked).child(st.error));
    if (!s) return root;

    // ---- routing
    const route = v_flex().gap(3).child(this.title("Routing", t));
    for (const role of ROLES) {
      const d = s.routing[role];
      if (!d) continue;
      const ind = d.independent === false ? " · not independent" : "";
      route.child(h_flex().id(`route-${role}`).gap(8).tooltip(d.reason)
        .child(div().w(70).text_color(t.muted).child(role))
        .child(div().font_semibold().text_color(d.selected ? t.foreground : t.blocked).child(d.selected || "none"))
        .child(div().text_color(t.dim).child(`${d.weight}${ind}`)));
    }
    const ov = s.override || {};
    for (const [role, agent] of Object.entries(ov)) {
      route.child(h_flex().gap(8).items_center()
        .child(div().text_color(t.ansi3).child(`override ${role} -> ${agent}`))
        .child(this.button(`clear-${role}`, "clear", t, (cx) => this.orch(hub, ["prefer", role, "-"], cx))));
    }
    root.child(route);

    // ---- quotas
    const qs = v_flex().gap(6).child(this.title("Quotas", t));
    for (const [agent, q] of Object.entries(s.quotas)) {
      const live = hub.labels[`orch.q.${agent}`];
      const row = v_flex().gap(2);
      const head = h_flex().gap(8).items_center()
        .child(div().w(110).font_semibold().truncate().child(agent))
        .child(div().text_color(t.dim).child(q.available ? `${q.confidence}${q.stale ? " · STALE" : ""}` : "unknown"));
      if (s.routing.execute?.selected !== agent && q.available && !q.stale) {
        head.child(this.button(`prefer-${agent}`, "use for next execute", t,
          (cx) => this.orch(hub, ["prefer", "execute", agent], cx)));
      }
      row.child(head);
      if (!q.available) {
        row.child(div().text_color(t.dim).child((q.extra && q.extra.reason) || "no quota source"));
      } else {
        for (const w of q.windows) {
          const pct = Math.max(0, Math.min(100, w.remaining_percent));
          const col = pct <= 15 ? t.blocked : pct <= 35 ? t.ansi3 : t.done;
          row.child(h_flex().gap(8).items_center()
            .child(div().w(28).text_color(t.muted).child(w.name))
            .child(div().w(140).h(8).rounded(4).bg(t.surface).child(div().w(Math.round(1.4 * pct)).h(8).rounded(4).bg(col)))
            .child(div().w(40).child(`${Math.round(pct)}%`))
            .child(div().text_color(t.dim).child(`reset ${until(w.resets_at)}`)));
        }
        const extra = [];
        if (q.headroom != null) extra.push(`headroom ${q.headroom}%/h`);
        if (q.extra && q.extra.reset_credits_available) extra.push(`${q.extra.reset_credits_available} reset credits`);
        if (live && live !== String(Math.round(q.effective_remaining_percent))) extra.push(`now ${live}%`);
        if (extra.length) row.child(div().text_color(t.dim).child(extra.join(" · ")));
      }
      qs.child(row);
    }
    root.child(qs);

    // ---- board
    const byTask = {};
    for (const term of terminals()) {
      const id = term.labels && term.labels["orch.task"];
      if (id && term.labels["orch.project"] === s.project) byTask[id] = term;
    }
    const running = s.tasks.filter((x) => x.state === "running");
    const cols = {
      PLANNED: this.planned(s),
      RUNNING: running.filter((x) => x.role !== "review"),
      REVIEW: running.filter((x) => x.role === "review"),
      DONE: s.tasks.filter((x) => x.state !== "running").slice(-5).reverse(),
    };
    // Side by side when there is room, stacked in a narrow panel.
    const wide = (this.width || 0) >= 640;
    const board = (wide ? h_flex() : v_flex()).gap(6).items_start();
    for (const [name, items] of Object.entries(cols)) {
      if (!wide && !items.length) continue;
      const col = v_flex().flex_1().w_full().gap(4).p(6).rounded(6).bg(t.surface)
        .child(div().text_color(t.muted).text_size(11).child(`${name} ${items.length}`));
      for (const it of items) col.child(this.card(it, byTask[it.id], m, t, name));
      board.child(col);
    }
    root.child(v_flex().gap(4).child(this.title("Tasks", t)).child(board));

    // ---- tool agents
    if (s.tools && s.tools.length) {
      const tools = v_flex().gap(3).child(this.title("Tool agents", t));
      for (const tool of s.tools) {
        const addr = qualify(m, tool.address);
        tools.child(h_flex().id(`tool-${tool.name}`).gap(8).hover((x) => x.bg(t.hover))
          .on_click(() => run("terminal.peek", { terminal: addr }))
          .child(div().w(140).child(tool.tool))
          .child(div().text_color(this.statusColor(tool.status, t)).child(tool.status || tool.state)));
      }
      root.child(tools);
    }

    // ---- GSD
    const p = s.planning;
    const gsd = v_flex().gap(3).child(this.title("GSD", t));
    if (!p || !p.available) {
      gsd.child(div().text_color(t.dim).child((p && p.reason) || "unknown"));
    } else {
      gsd.child(div().child(`${p.milestone || "?"} · phase ${p.phase || "?"} · ${p.status || "?"}`));
      if (p.milestone_name) gsd.child(div().text_color(t.dim).truncate().child(p.milestone_name));
      for (const ph of (p.phases || []).slice(-5)) {
        const done = (ph.plans || []).filter((x) => x.complete).length;
        gsd.child(h_flex().gap(8)
          .child(div().w(18).text_color(ph.complete ? t.done : t.dim).child(ph.complete ? "✓" : "·"))
          .child(div().w(40).child(ph.id))
          .child(div().text_color(t.muted).child(`plans ${done}/${(ph.plans || []).length} · verify ${ph.verification || "?"}`)));
      }
    }
    root.child(gsd);
    return root;
  }

  planned(s) {
    const p = s.planning;
    if (!p || !p.available) return [];
    const ph = (p.phases || []).find((x) => String(x.id) === String(p.phase));
    const started = new Set(s.tasks.map((x) => x.id));
    return ((ph && ph.plans) || []).filter((x) => !x.complete && !started.has(x.id))
      .map((x) => ({ id: x.id, role: "plan", agent: "", planned: true, title: x.title }));
  }

  card(it, term, machine, t, col) {
    const addr = term ? term.address : qualify(machine, it.live && it.live.address);
    const status = term ? term.status : (it.live && it.live.status);
    const c = v_flex().id(`card-${col}-${it.id}`).gap(2).p(6).rounded(4).bg(t.background)
      .border(1).border_color(status === "blocked" ? t.blocked : t.border);
    c.child(div().font_semibold().truncate().child(it.id));
    if (it.planned) return c.child(div().text_color(t.dim).truncate().child(it.title || ""));
    c.child(div().text_color(t.muted).child(`${it.role} · ${it.agent}`));
    if (col === "DONE") {
      return c.child(div().text_color(it.state === "complete" ? t.done : t.blocked).truncate()
        .child(`${it.state}${it.verdict ? " · " + it.verdict : ""}`));
    }
    c.child(div().text_color(this.statusColor(status, t)).truncate()
      .child(`${status || "no status"}${term && term.report && term.report.msg ? " · " + term.report.msg : ""}`));
    if (addr && term && term.state === "live") {
      c.child(h_flex().gap(6)
        .child(this.button(`focus-${it.id}`, "open", t, () => run("agent.focus", { terminal: addr })))
        .child(this.button(`stop-${it.id}`, "stop", t, () => run("terminal.kill", { terminal: addr }))));
    }
    return c;
  }

  statusColor(s, t) {
    return { working: t.working, blocked: t.blocked, done: t.done, idle: t.idle }[s] || t.unknown;
  }

  title(text, t) {
    return div().text_color(t.muted).text_size(11).font_semibold().child(text.toUpperCase());
  }

  button(id, label, t, fn) {
    return div().id(id).px(6).rounded(3).bg(t.raised).text_color(t.foreground).text_size(11)
      .hover((x) => x.bg(t.hover))
      .on_click((_e, cx) => fn(cx))
      .child(label);
  }
}
