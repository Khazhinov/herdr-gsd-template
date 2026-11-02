// GSD Mission Control for Herdr App.
//
// Shows the project of the active space, and only when that project runs the
// orchestration hub (`scripts/orch.py hub start`). In other spaces the panel
// hides its own layout node.
//
// Data flow (no polling of the scheduler):
//   the hub terminal (label orch.hub) rewrites .orchestration/runtime/state.json
//   and bumps its orch.rev label on every change. Herdr re-renders mods when
//   terminals() change, so the new revision arrives here at once and the mod
//   reads state.json from the hub's machine. Live worker status comes straight
//   from terminals() (OSC 7501 reports), never from the file.
import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { terminals, spaces, panes, layout, theme, run, exec, readTextFile, notify } from "herdr";

const NODE = "mission-control";            // id of this panel in the generated layout
const STATE_SUFFIX = "/.orchestration/runtime/state.json";
const ROLES = ["execute", "review", "plan", "research", "debug"];
const PROVIDER_NAMES = { claude: "Claude", codex: "Codex" };

function machineOf(address) {
  const i = address.indexOf("/");
  return i < 0 ? null : address.slice(0, i);
}

function qualify(machine, address) {
  if (!address) return null;
  return machine && !address.includes("/") ? `${machine}/${address}` : address;
}

function inside(path, root) {
  return !!path && (path === root || path.startsWith(root + "/"));
}

function hasNode(node, id) {
  if (!node || typeof node !== "object") return false;
  if (node.id === id) return true;
  return (node.children || []).some((c) => hasNode(c, id));
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
    this.shown = undefined;
    // Reset countdowns and "ago" texts change with time, not with data.
    cx.timer.every(30000, (cx) => cx.notify());
  }

  // The hub whose project root contains the folders of the active space.
  currentHub() {
    const space = spaces().find((s) => s.active);
    if (!space) return null;
    const tabIds = new Set(space.tabs.map((t) => t.id));
    const cwds = panes().filter((p) => tabIds.has(p.tab)).map((p) => p.cwd).filter(Boolean);
    if (space.folder) cwds.push(space.folder);
    return terminals().find((t) => {
      const st = t.state === "live" && t.labels && t.labels["orch.hub"] && t.labels["orch.state"];
      if (!st || (machineOf(t.address) || null) !== (space.machine || null)) return false;
      const root = t.labels["orch.state"].replace(STATE_SUFFIX, "");
      return cwds.some((c) => inside(c, root));
    }) || null;
  }

  // Show the layout panel only where it has something to say. A hidden layout
  // node stops rendering and could never show itself again, so the panel is
  // collapsed to zero width instead and keeps receiving live data.
  syncVisibility(want) {
    if (this.shown === want || !hasNode(layout(), NODE)) return;
    this.shown = want;
    if (want) run("layout.show", { id: NODE });  // undo an older hide
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
      const r = await exec("python3", [`${data.root}/scripts/orch.py`, ...args],
        { cwd: data.root, on: machineOf(hub.address) });
      if (r.code !== 0) notify({ title: "orch.py failed", body: (r.stderr || r.stdout).slice(-300), level: "error" });
      cx.notify();
    });
  }

  render(cx) {
    const t = theme();
    const hub = this.currentHub();
    this.syncVisibility(!!hub);
    const root = v_flex().id("mc").size_full().bg(t.chrome).text_color(t.foreground).text_size(12.5)
      .p(10).gap(12).overflow_y_scrollbar()
      // Remember the width the person chose, to restore it after a collapse.
      .on_size_change((size) => { if (size.width > 120) this.openWidth = Math.round(size.width); });
    if (!hub) {
      return root.child(div().text_color(t.muted)
        .child("No orchestration hub for this space. In a template project run: python3 scripts/orch.py hub start"));
    }
    this.load(hub, cx);
    const st = this.states[hub.address] || {};
    const s = st.data;
    const m = machineOf(hub.address);

    root.child(v_flex().gap(2)
      .child(div().font_semibold().text_size(14).child(hub.labels["orch.hub"]))
      .child(div().id("hub-peek").text_color(t.dim).tooltip("Peek at the hub terminal")
        .on_click(() => run("terminal.peek", { terminal: hub.address }))
        .child(s ? `owner ${s.owner} · updated ${ago(s.updated_at)} ago` : "loading…")));
    if (st.error) root.child(div().text_color(t.blocked).child(st.error));
    if (!s) return root;

    const live = {};
    for (const term of terminals()) {
      const id = term.labels && term.labels["orch.task"];
      if (id && term.labels["orch.project"] === s.project) live[id] = term;
    }
    const running = s.tasks.filter((x) => x.state === "running");
    const done = s.tasks.filter((x) => x.state !== "running")
      .sort((a, b) => (b.finished_at || 0) - (a.finished_at || 0)).slice(0, 3);

    // ---- now: GSD position + live workers
    const now = v_flex().gap(4).child(this.title("Now", t));
    const p = s.planning;
    if (p && p.available) {
      now.child(div().child(`${p.milestone || "?"} · phase ${p.phase || "?"} · ${p.status || "?"}`));
      if (p.stopped_at) now.child(div().text_color(t.dim).child(`stopped at: ${p.stopped_at}`));
    } else {
      now.child(div().text_color(t.dim).child((p && p.reason) || "GSD state unknown"));
    }
    if (!running.length) now.child(div().text_color(t.dim).child("no workers running"));
    for (const it of running) now.child(this.card(it, live[it.id], m, t));
    root.child(now);

    // ---- next: plans of the current phase not dispatched yet
    const next = this.planned(s);
    const nx = v_flex().gap(3).child(this.title("Next", t));
    if (!next.length) nx.child(div().text_color(t.dim).child("no pending plans in the current phase"));
    for (const it of next.slice(0, 6)) {
      nx.child(h_flex().gap(8)
        .child(div().w(70).child(it.id))
        .child(div().flex_1().text_color(t.muted).truncate().child(it.title || "")));
    }
    root.child(nx);

    // ---- quotas per agent environment
    const qs = v_flex().gap(6).child(this.title("Limits", t));
    for (const [kind, q] of Object.entries(s.providers || {})) {
      const head = h_flex().gap(8).items_center()
        .child(div().font_semibold().child(PROVIDER_NAMES[kind] || kind))
        .child(div().text_color(q.stale ? t.blocked : t.dim).child(
          !q.available ? "unknown" : q.stale ? `stale · seen ${ago(q.observed_at)} ago` : q.confidence));
      const row = v_flex().gap(2).child(head);
      if (!q.available) {
        row.child(div().text_color(t.dim).child((q.extra && q.extra.reason) || "no quota source"));
      }
      for (const w of q.windows || []) {
        const pct = Math.max(0, Math.min(100, w.remaining_percent));
        const col = pct <= 15 ? t.blocked : pct <= 35 ? t.ansi3 : t.done;
        row.child(h_flex().gap(8).items_center()
          .child(div().w(28).text_color(t.muted).child(w.name))
          .child(div().w(140).h(8).rounded(4).bg(t.surface).child(div().w(Math.round(1.4 * pct)).h(8).rounded(4).bg(col)))
          .child(div().w(40).child(`${Math.round(pct)}%`))
          .child(div().text_color(t.dim).child(`reset ${until(w.resets_at)}`)));
      }
      if (q.extra && q.extra.reset_credits_available) {
        row.child(div().text_color(t.dim).child(`${q.extra.reset_credits_available} reset credits`));
      }
      qs.child(row);
    }
    root.child(qs);

    // ---- routing: who gets the next task of each role
    const route = v_flex().gap(3).child(this.title("Next task goes to", t));
    for (const role of ROLES) {
      const d = s.routing[role];
      if (!d) continue;
      route.child(h_flex().id(`route-${role}`).gap(8).tooltip(d.reason)
        .child(div().w(70).text_color(t.muted).child(role))
        .child(div().font_semibold().text_color(d.selected ? t.foreground : t.blocked).child(d.selected || "none"))
        .child(div().text_color(t.dim).child(d.independent === false ? "not independent" : "")));
    }
    for (const [role, agent] of Object.entries(s.override || {})) {
      route.child(h_flex().gap(8).items_center()
        .child(div().text_color(t.ansi3).child(`override ${role} -> ${agent}`))
        .child(this.button(`clear-${role}`, "clear", t, (cx) => this.orch(hub, ["prefer", role, "-"], cx))));
    }
    root.child(route);

    // ---- recently finished
    if (done.length) {
      const dn = v_flex().gap(3).child(this.title("Done", t));
      for (const it of done) {
        dn.child(h_flex().gap(8)
          .child(div().w(120).truncate().child(it.id))
          .child(div().text_color(it.state === "complete" ? t.done : t.blocked).truncate()
            .child(`${it.agent} · ${it.verdict || it.state}`)));
      }
      root.child(dn);
    }

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
    return root;
  }

  planned(s) {
    const p = s.planning;
    if (!p || !p.available) return [];
    const ph = (p.phases || []).find((x) => String(x.id) === String(p.phase));
    const started = new Set(s.tasks.map((x) => x.id));
    return ((ph && ph.plans) || []).filter((x) => !x.complete && !started.has(x.id));
  }

  card(it, term, machine, t) {
    const addr = term ? term.address : qualify(machine, it.live && it.live.address);
    const status = term ? term.status : (it.live && it.live.status);
    const msg = term && term.report && term.report.msg;
    const c = v_flex().id(`card-${it.id}`).gap(2).p(6).rounded(4).bg(t.background)
      .border(1).border_color(status === "blocked" ? t.blocked : t.border)
      .child(h_flex().justify_between()
        .child(div().font_semibold().truncate().child(it.id))
        .child(div().text_color(this.statusColor(status, t)).child(status || "no status")))
      .child(div().text_color(t.muted).child(`${it.role} · ${it.agent}`));
    if (msg) c.child(div().text_color(t.dim).truncate().child(msg));
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
