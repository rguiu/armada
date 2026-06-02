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

export default async function () {
  return {
    "tool.execute.before": async function (input, output) {
      if (input && input.tool) post("active", "running " + input.tool);
    },
    "tool.execute.after": async function (input, output) {
      if (input && input.tool) post("idle", input.tool + " completed");
    },
    "permission.ask": async function (input, output) {
      if (!output || output.decision !== "ask") return;
      var tool = (input && input.tool) || "?";
      post("pending", "waiting for " + tool + " permission");
    },
  };
}
