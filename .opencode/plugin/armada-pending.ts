// Armada pending plugin — reports status to the Armada dashboard

const API = "http://127.0.0.1:9100";
const NODE = process.env.ARMADA_NODE_NAME;

function post(status: string, message: string) {
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

export default async () => ({
  "tool.execute.before": async (input: any, _output: any) => {
    if (input?.tool) post("active", "running " + input.tool);
  },
  "tool.execute.after": async (input: any, _output: any) => {
    if (input?.tool) post("idle", input.tool + " completed");
  },
  "permission.ask": async (input: any, output: any) => {
    if (!output || output.decision !== "ask") return;
    post("pending", "waiting for " + (input?.tool || "?") + " permission");
  },
});
