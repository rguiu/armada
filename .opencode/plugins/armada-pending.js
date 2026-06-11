var API = "http://127.0.0.1:9100";
var NODE = process.env ? process.env.ARMADA_NODE_NAME : undefined;

function post(status, message, extra) {
  if (!NODE) return;
  extra = extra || {};
  var body = JSON.stringify({ name: NODE, status: status, message: message, options: extra.options, tokens: extra.tokens, cost: extra.cost });
  var payload = Buffer.byteLength(body, 'utf8');

  var sent = false;

  try {
    var http = require("http");
    var u = new (require("url").URL)(API + "/api/report");
    var req = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname,
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": payload },
    }, function (res) { res.resume(); });
    req.on("error", function () {});
    req.write(body);
    req.end();
    sent = true;
  } catch (_) {}

  if (!sent) {
    try {
      fetch(API + "/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
      }).then(function (r) { return r.text(); }).catch(function () {});
    } catch (_) {}
  }
}

var evtLog;
try {
  evtLog = require("fs").appendFileSync.bind(null, "/tmp/armada-events.log");
} catch (_) {}

var _pendingTool = null;

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
        _pendingTool = props.tool;
        if (props.tool) post("active", "running " + props.tool);
      } else if (event.type === "tool.execute.after") {
        _pendingTool = null;
        var props2 = event.properties || {};
        if (props2.tool) post("idle", props2.tool + " completed");
      } else if (event.type === "permission.asked") {
        var props3 = event.properties || {};
        var patterns = (props3.patterns || []).join(", ") || "any file";
        var tool = _pendingTool || "unknown";
        setTimeout(function () {
          post("pending", tool + " needs " + (props3.permission || "?") + " permission: " + patterns, {
            options: [
              { label: "Allow once", key: "\n" },
              { label: "Allow always", key: "\x1b[C\n" },
              { label: "Reject", key: "\x1b[C\x1b[C\n" }
            ]
          });
        }, 200);
      } else if (event.type === "message.part.updated") {
        var part = (event.properties || {}).part;
        if (part && part.type === "step-finish" && part.id && !seenCosts[part.id]) {
          seenCosts[part.id] = true;
          post("active", "step completed", { tokens: part.tokens, cost: part.cost });
        }
      }
    },
  };
}
