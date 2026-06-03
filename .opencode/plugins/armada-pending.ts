// Armada pending plugin — reports status to the Armada dashboard

const API = "http://127.0.0.1:9100";
const NODE = process.env.ARMADA_NODE_NAME;

function post(status, message) {
  if (!NODE) return;
  const body = JSON.stringify({ name: NODE, status, message });
  try {
    fetch(`${API}/api/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    }).catch(() => {});
  } catch (_) {
    try {
      const http = require("http");
      const url = new (require("url").URL)(`${API}/api/report`);
      const req = http.request({
        hostname: url.hostname, port: url.port, path: url.pathname,
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
      }, () => {});
      req.on("error", () => {});
      req.write(body);
      req.end();
    } catch (_) {}
  }
}

let evtLog;
try {
  evtLog = require("fs").appendFileSync.bind(null, "/tmp/armada-events.log");
} catch (_) {}

export const ArmadaPending = async () => ({
  event: async ({ event }) => {
    if (evtLog) {
      try { evtLog(JSON.stringify(event) + "\n"); } catch (_) {}
    }
    if (event.type === "tool.execute.before") {
      post("active", "running " + event.properties.tool);
    } else if (event.type === "tool.execute.after") {
      post("idle", event.properties.tool + " completed");
    } else if (event.type === "permission.asked") {
      post("pending", event.properties.permission + " permission: " + (event.properties.patterns || []).join(", "));
    }
  },
});
