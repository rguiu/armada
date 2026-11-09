// Armada pending plugin — reports node status to the Armada dashboard.
//
// This targets the OpenCode V2 plugin API:
// https://opencode.ai/docs/build/plugins/
//
// OpenCode discovers direct .ts/.js files under .opencode/plugins/ (project)
// and ~/.config/opencode/plugins/ (global), so no opencode.json entry is needed.

import { Plugin } from "@opencode/plugin"

const API = process.env.ARMADA_API || "http://127.0.0.1:9100"
const NODE = process.env.ARMADA_NODE_NAME

type Tokens = { input?: number; output?: number }
type PermissionOption = { label: string; key: string }
type Extra = {
  tokens?: Tokens
  cost?: number
  options?: PermissionOption[]
}

async function post(status: string, message: string, extra: Extra = {}) {
  if (!NODE) return

  const body = JSON.stringify({ name: NODE, status, message, ...extra })
  try {
    await fetch(`${API}/api/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      // The dashboard may be down; agent work must never be blocked by it.
      signal: AbortSignal.timeout(1500),
    })
  } catch {
    // Ignore connectivity failures.
  }
}

function permissionMessage(data: Record<string, any>) {
  const action = typeof data.action === "string" ? data.action : "permission"
  const resources = Array.isArray(data.resources)
    ? data.resources.filter((value) => typeof value === "string").join(", ")
    : ""
  const detail =
    typeof data.message === "string" && data.message.length > 0
      ? data.message
      : resources
  return detail ? `${action}: ${detail}` : action
}

export default Plugin.define({
  id: "armada.pending",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", (event) => {
      void post("active", `running ${event.tool}`)
    })

    await ctx.tool.hook("execute.after", (event) => {
      void post("idle", `${event.tool} completed`)
    })

    // session.usage.updated carries cumulative session totals. Armada adds
    // every report to its own totals, so send only the delta since the last
    // event for that session.
    const lastUsage = new Map<string, { cost: number; input: number; output: number }>()

    const controller = new AbortController()
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          const data = (event.data ?? {}) as Record<string, any>

          switch (event.type) {
            case "permission.asked":
              void post("pending", permissionMessage(data), {
                options: [
                  { label: "Allow once", key: "\n" },
                  { label: "Always allow", key: "\x1b[C\n" },
                  { label: "Deny", key: "\x1b[C\x1b[C\n" },
                ],
              })
              break

            case "permission.replied":
              void post(
                data.reply === "reject" ? "idle" : "active",
                `permission ${data.reply ?? "replied"}`,
              )
              break

            case "session.status": {
              const status = data.status
              if (status?.type === "idle") {
                void post("idle", "waiting for input")
              } else if (status?.type === "retry") {
                void post("active", `retrying: ${status.message ?? ""}`)
              }
              break
            }

            case "session.usage.updated": {
              const sessionID =
                typeof data.sessionID === "string" ? data.sessionID : "unknown"
              const cost = typeof data.cost === "number" ? data.cost : 0
              const tokens = (data.tokens ?? {}) as Record<string, any>
              const input = Number(tokens.input ?? 0)
              const output =
                Number(tokens.output ?? 0) + Number(tokens.reasoning ?? 0)

              const previous =
                lastUsage.get(sessionID) ?? { cost: 0, input: 0, output: 0 }
              const deltaCost = Math.max(0, cost - previous.cost)
              const deltaInput = Math.max(0, input - previous.input)
              const deltaOutput = Math.max(0, output - previous.output)
              lastUsage.set(sessionID, { cost, input, output })

              if (deltaCost > 0 || deltaInput > 0 || deltaOutput > 0) {
                void post("active", "usage recorded", {
                  tokens: { input: deltaInput, output: deltaOutput },
                  cost: deltaCost,
                })
              }
              break
            }

            case "session.execution.failed":
              void post("error", data.error?.message ?? "execution failed")
              break
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error("armada plugin event stream failed", error)
        }
      }
    })()

    return () => controller.abort()
  },
})
