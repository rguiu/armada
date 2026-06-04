var NODE = process.env ? process.env.ARMADA_NODE_NAME : undefined;

function post(status, message, extra) {
  if (!NODE) return;
  extra = extra || {};
  var http = require("http");
  var payload = { name: NODE, status: status, message: message };
  if (extra.tokens) payload.tokens = extra.tokens;
  if (extra.cost !== undefined) payload.cost = extra.cost;
  var body = JSON.stringify(payload);
  var url = new (require("url").URL)("http://127.0.0.1:9100/api/report");
  var req = http.request({
    hostname: url.hostname, port: url.port, path: url.pathname,
    method: "POST",
    headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
  }, function () {});
  req.on("error", function () {});
  req.write(body);
  req.end();
}

var evtLog;
try {
  evtLog = require("fs").appendFileSync.bind(null, "/tmp/armada-events.log");
} catch (_) {}

export async function ArmadaPending() {
  var seenCosts = {};
  return {
    event: async function (input) {
      var event = input && input.event;
      if (!event) return;
      if (evtLog) {
        try { evtLog(JSON.stringify(event) + "\n"); } catch (_) {}
      }
      if (event.type === "tool.execute.before") {
        var props = event.properties || {};
        if (props.tool) post("active", "running " + props.tool);
      } else if (event.type === "tool.execute.after") {
        var props2 = event.properties || {};
        if (props2.tool) post("idle", props2.tool + " completed");
      } else if (event.type === "permission.asked") {
        var props3 = event.properties || {};
        var patterns = props3.patterns || [];
        post("pending", (props3.permission || "?") + " permission: " + patterns.join(", "));
      } else if (event.type === "message.part.updated") {
        var props4 = event.properties || {};
        var part = props4.part;
        if (part && part.type === "step-finish" && part.id && !seenCosts[part.id]) {
          seenCosts[part.id] = true;
          post("active", "step completed", { tokens: part.tokens, cost: part.cost });
        }
      }
    },
  };
}
