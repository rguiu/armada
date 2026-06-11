// Armada pending plugin — reports status to the Armada dashboard

const API = "http://127.0.0.1:9100";
const NODE = process.env.ARMADA_NODE_NAME;

function post(status, message, extra = {}) {
  if (!NODE) return;
  const body = JSON.stringify({ name: NODE, status, message, ...extra });
  const payload = Buffer.byteLength(body, 'utf8');

  let sent = false;

  try {
    const http = require("http");
    const u = new (require("url").URL)(`${API}/api/report`);
    const req = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname,
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": payload },
    }, (res) => { res.resume(); });
    req.on("error", () => {});
    req.write(body);
    req.end();
    sent = true;
  } catch (_) {}

  if (!sent) {
    try {
      fetch(`${API}/api/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      }).then(r => r.text()).catch(() => {});
    } catch (_) {}
  }
}

let evtLog;
try {
  evtLog = require("fs").appendFileSync.bind(null, "/tmp/armada-events.log");
} catch (_) {}

let _pendingTool = null;

export const ArmadaPending = async () => {
  const seenCosts = new Set();
  return {
  event: async ({ event }) => {
    if (evtLog) {
      try { evtLog(JSON.stringify(event) + "\n"); } catch (_) {}
    }
    if (event.type === "tool.execute.before") {
      _pendingTool = event.properties.tool;
      post("active", "running " + event.properties.tool);
    } else if (event.type === "tool.execute.after") {
      _pendingTool = null;
      post("idle", event.properties.tool + " completed");
    } else if (event.type === "permission.asked") {
      const perm = event.properties.permission || "unknown";
      const patterns = (event.properties.patterns || []).join(", ") || "any file";
      const tool = _pendingTool || "unknown";
      // Send with small delay to ensure it arrives after active post
      setTimeout(() => {
        post("pending", tool + " needs " + perm + " permission: " + patterns, {
          options: [
            { label: "Allow once", key: "\n" },
            { label: "Allow always", key: "\x1b[C\n" },
            { label: "Reject", key: "\x1b[C\x1b[C\n" },
          ]
        });
      }, 200);
    } else if (event.type === "message.part.updated") {
      const part = event.properties?.part;
      if (part?.type === "step-finish" && part.id && !seenCosts.has(part.id)) {
        seenCosts.add(part.id);
        post("active", "step completed", { tokens: part.tokens, cost: part.cost });
      }
    }
  },
};
};
