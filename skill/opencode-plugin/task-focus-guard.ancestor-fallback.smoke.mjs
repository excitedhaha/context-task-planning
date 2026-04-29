import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { spawnSync } from "node:child_process"

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
      next_action: "Do not leak fallback context into unrelated sessions.",
      blockers: [],
      phases: [],
      delegation: { enabled: true, single_writer: true, active: [] },
    }, null, 2)}\n`,
    "utf8",
  )
  writeFileSync(path.join(planDir, "task_plan.md"), `# Task Plan: ${title}\n`, "utf8")
  writeFileSync(path.join(planDir, "progress.md"), `# Progress Log: ${title}\n`, "utf8")
  writeFileSync(path.join(planDir, "findings.md"), `# Findings: ${title}\n`, "utf8")
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

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, encoding: "utf8" })
  if (result.error || result.status !== 0) {
    throw new Error(
      [
        `command failed: ${command} ${args.join(" ")}`,
        `status=${result.status}`,
        (result.stderr || "").trim(),
        (result.stdout || "").trim(),
      ].filter(Boolean).join("\n"),
    )
  }
}

const workspace = mkdtempSync(path.join(os.tmpdir(), "ctp-opencode-ancestor-fallback."))

try {
  const planRoot = path.join(workspace, ".planning")
  const childRepo = path.join(workspace, "VSCProjects")
  mkdirSync(planRoot, { recursive: true })
  mkdirSync(childRepo, { recursive: true })

  writeTask(planRoot, "existing-task", "Existing Task")
  writeFileSync(path.join(planRoot, ".active_task"), "existing-task\n", "utf8")

  run("git", ["init"], childRepo)

  const titles = new Map([
    ["A", "Session A"],
    ["C", "Session C"],
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

  const plugin = await ContextTaskPlanningOpenCodePlugin({ client, directory: childRepo })

  await plugin.event({ event: { type: "session.created", properties: { info: { id: "C" } } } })
  assert.equal(titles.get("C"), "Session C")

  const fallbackTransformOutput = { system: [] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "C" }, fallbackTransformOutput)
  assert.match(fallbackTransformOutput.system.join("\n"), /Workspace fallback resolved task `existing-task`/u)
  assert.doesNotMatch(fallbackTransformOutput.system.join("\n"), /Current task `existing-task`/u)
  assert.doesNotMatch(fallbackTransformOutput.system.join("\n"), /Next action:/u)

  const fallbackTaskOutput = { args: { prompt: "Investigate the repo behavior" } }
  await plugin["tool.execute.before"](
    { tool: "Task", sessionID: "C", args: { prompt: "Investigate the repo behavior" } },
    fallbackTaskOutput,
  )
  assert.equal(fallbackTaskOutput.args.prompt, "Investigate the repo behavior")

  writeBinding(planRoot, "A", "existing-task")
  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  assert.equal(titles.get("A"), "task:existing-task | Session A")

  const boundTransformOutput = { system: [] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "A" }, boundTransformOutput)
  assert.equal(boundTransformOutput.system.join("\n"), "")

  assert.equal(toasts.length, 0)
  console.log("[context-task-planning] smoke test passed: OpenCode ancestor workspace fallback stays advisory until explicit binding")
} finally {
  rmSync(workspace, { recursive: true, force: true })
}
