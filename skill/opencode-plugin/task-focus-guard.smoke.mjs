import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdtempSync, mkdirSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs"
import os from "node:os"
import path from "node:path"

import { ContextTaskPlanningOpenCodePlugin } from "./task-focus-guard.js"

function sessionBindingName(sessionKey) {
  const cleaned = sessionKey.replace(/[^A-Za-z0-9_.-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "") || "session"
  const digest = createHash("sha1").update(sessionKey, "utf8").digest("hex").slice(0, 12)
  return `${cleaned.slice(0, 48)}-${digest}.json`
}

function writeTask(planRoot, slug, title, status = "active") {
  const planDir = path.join(planRoot, slug)
  mkdirSync(planDir, { recursive: true })
  writeFileSync(
    path.join(planDir, "state.json"),
    `${JSON.stringify({
      schema_version: "1.0.0",
      slug,
      title,
      status,
      mode: "execute",
      current_phase: "execute",
      next_action: "Keep session titles isolated.",
      blockers: [],
      phases: [],
      delegation: { enabled: true, single_writer: true, active: [] },
    }, null, 2)}\n`,
    "utf8",
  )
}

function setTaskStatus(planRoot, slug, status) {
  const statePath = path.join(planRoot, slug, "state.json")
  const state = JSON.parse(readFileSync(statePath, "utf8"))
  state.status = status
  writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`, "utf8")
}

function writeBinding(planRoot, sessionID, taskSlug) {
  const sessionKey = `opencode:${sessionID}`
  const sessionsDir = path.join(planRoot, ".sessions")
  mkdirSync(sessionsDir, { recursive: true })
  writeFileSync(
    path.join(sessionsDir, sessionBindingName(sessionKey)),
    `${JSON.stringify({
      schema_version: "1.0.0",
      session_key: sessionKey,
      task_slug: taskSlug,
      role: "writer",
      updated_at: "2026-03-26T00:00:00Z",
    }, null, 2)}\n`,
    "utf8",
  )
}

function clearBinding(planRoot, sessionID) {
  const sessionKey = `opencode:${sessionID}`
  unlinkSync(path.join(planRoot, ".sessions", sessionBindingName(sessionKey)))
}

const workspace = mkdtempSync(path.join(os.tmpdir(), "ctp-opencode-title-smoke."))

try {
  const planRoot = path.join(workspace, ".planning")
  mkdirSync(planRoot, { recursive: true })

  writeTask(planRoot, "base-app-mobile", "Base App Mobile")
  writeTask(
    planRoot,
    "base-app-mobile-coldstart-optimization",
    "Base App Mobile Coldstart Optimization",
  )
  writeBinding(planRoot, "A", "base-app-mobile")
  writeBinding(planRoot, "B", "base-app-mobile-coldstart-optimization")
  writeFileSync(path.join(planRoot, ".active_task"), "base-app-mobile-coldstart-optimization\n", "utf8")

  const titles = new Map([
    ["A", "Session A"],
    ["B", "Session B"],
  ])
  const toasts = []
  const client = {
    session: {
      async get({ path: { id } }) {
        return { data: { id, title: titles.get(id) || "Session" } }
      },
      async update({ path: { id }, body: { title } }) {
        titles.set(id, title)
        return { data: { id, title } }
      },
    },
    tui: {
      async showToast({ body }) {
        toasts.push(body)
      },
    },
  }

  const plugin = await ContextTaskPlanningOpenCodePlugin({ client, directory: workspace })

  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  await plugin.event({ event: { type: "session.created", properties: { info: { id: "B" } } } })
  assert.equal(titles.get("A"), "task:base-app-mobile | Session A")
  assert.equal(titles.get("B"), "task:base-app-mobile-coldstart-optimization | Session B")

  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  await plugin["tool.execute.after"]({ tool: "read" }, {})
  assert.equal(titles.get("A"), "task:base-app-mobile | Session A")
  assert.equal(titles.get("B"), "task:base-app-mobile-coldstart-optimization | Session B")

  unlinkSync(path.join(planRoot, ".active_task"))
  setTaskStatus(planRoot, "base-app-mobile", "paused")
  setTaskStatus(planRoot, "base-app-mobile-coldstart-optimization", "paused")

  await plugin["tool.execute.after"]({ tool: "read" }, {})
  assert.equal(titles.get("A"), "task:base-app-mobile | Session A")
  assert.equal(titles.get("B"), "task:base-app-mobile-coldstart-optimization | Session B")

  writeTask(planRoot, "archive-me", "Archive Me")
  writeBinding(planRoot, "A", "archive-me")
  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  assert.equal(titles.get("A"), "task:archive-me | Session A")

  setTaskStatus(planRoot, "archive-me", "done")
  clearBinding(planRoot, "A")
  await plugin["tool.execute.after"]({ tool: "bash", sessionID: "A" }, {})
  assert.equal(titles.get("A"), "Session A")
  assert.deepEqual(toasts.at(-1), {
    title: "Nice work",
    message: "archive-me is done. Want to archive it or start a new task?",
    variant: "info",
    duration: 2600,
  })

  const transformOutput = { system: [] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "A" }, transformOutput)
  assert.match(
    transformOutput.system.join("\n"),
    /congratulate the user briefly, then ask whether they want to archive it now or start a new task/i,
  )

  const secondTransformOutput = { system: [] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "A" }, secondTransformOutput)
  assert.equal(secondTransformOutput.system.length, 0)

  console.log("[context-task-planning] smoke test passed: OpenCode multi-session titles stay isolated")
} finally {
  rmSync(workspace, { recursive: true, force: true })
}
