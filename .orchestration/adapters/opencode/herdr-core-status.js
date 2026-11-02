// Reports OpenCode status to herdr-core through OSC 7501, written to the
// controlling terminal. herdr-core and Herdr App show it (working / blocked /
// idle) and orchestration uses it to see that a worker started.
// The legacy herdr-agent-state.js speaks the old Herdr TUI socket; this file
// covers terminals started by herdr-core (HC_TERMINAL_ID is set there).
// Format verified against herdr-core 0.1.16: ESC ] 7501 ; state=<s>[:kind=<k>] BEL.
import fs from "node:fs";

let last = "";

function report(state, kind) {
  const payload = kind ? `state=${state}:kind=${kind}` : `state=${state}`;
  if (payload === last) return;
  last = payload;
  try {
    fs.writeFileSync("/dev/tty", `\x1b]7501;${payload}\x07`);
  } catch {
    // no controlling terminal (server mode): nothing to report to
  }
}

export const HerdrCoreStatusPlugin = async () => {
  if (!process.env.HC_TERMINAL_ID) return {};
  report("idle");
  return {
    "chat.message": async () => report("working"),
    event: async ({ event }) => {
      switch (event?.type) {
        case "permission.asked":
          return report("blocked", "permission");
        case "question.asked":
          return report("blocked", "question");
        case "session.error":
          return report("error");
        case "session.idle":
          return report("idle");
        case "session.status": {
          const s = event.properties?.status;
          const kind = typeof s === "string" ? s : s?.type;
          return report(kind === "idle" ? "idle" : "working");
        }
        case "tool.execute.before":
        case "permission.replied":
        case "question.replied":
          return report("working");
        default:
          return undefined;
      }
    },
  };
};

export default { id: "herdr.core-status", server: HerdrCoreStatusPlugin, setup() {} };
