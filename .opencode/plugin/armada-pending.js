var NODE = process.env ? process.env.ARMADA_NODE_NAME : undefined;

function post(status, message) {
  if (!NODE) return;
  var http = require("http");
  var body = JSON.stringify({ name: NODE, status: status, message: message });
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
      }
    },
  };
}
