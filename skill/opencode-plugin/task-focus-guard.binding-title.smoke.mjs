import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs"
import os from "node:os"
import path from "node:path"

import { ContextTaskPlanningOpenCodePlugin } from "./task-focus-guard.js"

function sessionBindingName(sessionKey) {
  const cleaned = sessionKey.replace(/[^A-Za-z0-9_.-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "") || "session"
  const digest = createHash("sha1").update(sessionKey, "utf8").digest("hex").slice(0, 12)
  return `${cleaned.slice(0, 48)}-${digest}.json`
}

function writeTask(planRoot, slug, title) {
  const planDir = path.join(planRoot, slug)
  mkdirSync(planDir, { recursive: true })
  writeFileSync(
    path.join(planDir, "state.json"),
    `${JSON.stringify({
      schema_version: "1.0.0",
      slug,
      title,
      status: "active",
      mode: "execute",
      current_phase: "execute",
      next_action: "Wait for explicit binding.",
      blockers: [],
      phases: [],
      delegation: { enabled: true, single_writer: true, active: [] },
    }, null, 2)}\n`,
    "utf8",
  )
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

const workspace = mkdtempSync(path.join(os.tmpdir(), "ctp-opencode-binding-title."))

try {
  const planRoot = path.join(workspace, ".planning")
  mkdirSync(planRoot, { recursive: true })
  writeTask(planRoot, "existing-task", "Existing Task")
  writeFileSync(path.join(planRoot, ".active_task"), "existing-task\n", "utf8")

  const titles = new Map([["A", "Session A"]])
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
      async showToast() {},
    },
  }

  const plugin = await ContextTaskPlanningOpenCodePlugin({ client, directory: workspace })

  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  assert.equal(titles.get("A"), "Session A")

  writeBinding(planRoot, "A", "existing-task")
  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  assert.equal(titles.get("A"), "task:existing-task | Session A")

  console.log("[context-task-planning] smoke test passed: OpenCode titles require explicit session binding")
} finally {
  rmSync(workspace, { recursive: true, force: true })
}
