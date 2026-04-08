import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { ContextTaskPlanningOpenCodePlugin } from "./task-focus-guard.js"

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const SCRIPTS_DIR = path.resolve(PLUGIN_DIR, "..", "scripts")

function runScript(scriptName, args, cwd, extraEnv = {}) {
  const result = spawnSync("sh", [path.join(SCRIPTS_DIR, scriptName), ...args], {
    cwd,
    encoding: "utf8",
    env: {
      ...process.env,
      ...extraEnv,
    },
  })

  if (result.error || result.status !== 0) {
    throw new Error(
      [
        `script failed: ${scriptName}`,
        `status=${result.status}`,
        (result.stderr || "").trim(),
        (result.stdout || "").trim(),
      ].filter(Boolean).join("\n"),
    )
  }

  return (result.stdout || "").trim()
}

function introduceWarningDrift(planDir, goal, nextAction) {
  const statePath = path.join(planDir, "state.json")
  const progressPath = path.join(planDir, "progress.md")
  const state = JSON.parse(readFileSync(statePath, "utf8"))
  state.goal = goal
  writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`, "utf8")

  const progress = readFileSync(progressPath, "utf8").replace(
    "- Next Action: Fill in goal, non-goals, acceptance criteria, constraints, and open questions before implementation.",
    `- Next Action: ${nextAction}`,
  )
  writeFileSync(progressPath, progress, "utf8")
}

function removeProgressFile(planDir) {
  rmSync(path.join(planDir, "progress.md"))
}

const workspace = mkdtempSync(path.join(os.tmpdir(), "ctp-opencode-compact-sync."))

try {
  runScript("init-task.sh", ["--slug", "compact-demo", "--title", "Compact demo"], workspace)
  const planDir = path.join(workspace, ".planning", "compact-demo")
  introduceWarningDrift(planDir, "Refresh OpenCode compact coverage.", "compact plugin stale action")

  runScript(
    "set-active-task.sh",
    ["--allow-dirty", "--steal", "compact-demo"],
    workspace,
    { PLAN_SESSION_KEY: "opencode:A" },
  )

  const titles = new Map([["A", "Session A"]])
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
      async showToast(toast) {
        toasts.push(toast)
      },
    },
  }

  const plugin = await ContextTaskPlanningOpenCodePlugin({ client, directory: workspace })
  const compactingOutput = { context: [] }
  await plugin["experimental.session.compacting"]({ sessionID: "A" }, compactingOutput)
  assert.match(compactingOutput.context.join("\n"), /Task `compact-demo`/u)
  assert.match(compactingOutput.context.join("\n"), /recently compacted/u)

  await plugin.event({
    event: {
      type: "session.compacted",
      properties: {
        sessionID: "A",
      },
    },
  })

  const transformAfterCompact = { system: [] }
  await plugin["experimental.chat.system.transform"](
    { sessionID: "A", model: {} },
    transformAfterCompact,
  )
  assert.match(transformAfterCompact.system.join("\n"), /recently compacted/u)
  assert.match(transformAfterCompact.system.join("\n"), /Task `compact-demo`/u)
  assert.match(transformAfterCompact.system.join("\n"), /state\.json/u)
  assert.match(transformAfterCompact.system.join("\n"), /progress\.md/u)

  const secondTransformAfterCompact = { system: [] }
  await plugin["experimental.chat.system.transform"](
    { sessionID: "A", model: {} },
    secondTransformAfterCompact,
  )
  assert.match(secondTransformAfterCompact.system.join("\n"), /state\.json/u)
  assert.match(secondTransformAfterCompact.system.join("\n"), /progress\.md/u)

  await plugin["tool.execute.after"](
    {
      tool: "multi_tool_use.parallel",
      sessionID: "A",
      args: {
        tool_uses: [
          {
            recipient_name: "functions.read",
            parameters: { filePath: path.join(planDir, "state.json") },
          },
          {
            recipient_name: "functions.read",
            parameters: { filePath: path.join(planDir, "progress.md") },
          },
        ],
      },
    },
    {},
  )

  const thirdTransformAfterCompact = { system: [] }
  await plugin["experimental.chat.system.transform"](
    { sessionID: "A", model: {} },
    thirdTransformAfterCompact,
  )
  assert.doesNotMatch(thirdTransformAfterCompact.system.join("\n"), /This session compacted recently/u)
  assert.doesNotMatch(thirdTransformAfterCompact.system.join("\n"), /re-read `\.planning\/compact-demo\/state\.json`/u)

  const validate = runScript("validate-task.sh", ["--task", "compact-demo"], workspace)
  assert.match(validate, /Validation passed\./)
  assert.equal(
    existsSync(path.join(planDir, ".derived", "context_compact.json")),
    true,
  )
  assert.equal(titles.get("A"), "task:compact-demo | Session A")
  assert.equal(toasts.some((toast) => toast.body?.title === "Compact sync warning"), false)

  introduceWarningDrift(planDir, "Do not compact on false events.", "false event stale action")
  await plugin.event({
    event: {
      type: "session.updated",
      properties: {
        info: { id: "A" },
        compact: false,
      },
    },
  })

  const falsePositiveValidate = runScript("validate-task.sh", ["--task", "compact-demo"], workspace)
  assert.match(falsePositiveValidate, /Validation passed with warnings\./)
  assert.match(falsePositiveValidate, /progress\.md Snapshot `next_action` differs from state\.json/)

  runScript("init-task.sh", ["--slug", "compact-fail", "--title", "Compact fail"], workspace)
  const brokenPlanDir = path.join(workspace, ".planning", "compact-fail")
  runScript(
    "set-active-task.sh",
    ["--allow-dirty", "--steal", "compact-fail"],
    workspace,
    { PLAN_SESSION_KEY: "opencode:B" },
  )
  titles.set("B", "Session B")
  removeProgressFile(brokenPlanDir)

  await plugin.event({
    event: {
      type: "session.created",
      properties: {
        info: { id: "B" },
        reason: "compact",
      },
    },
  })

  const compactWarningToast = toasts.find((toast) => toast.body?.title === "Compact sync warning")
  assert.ok(compactWarningToast)
  assert.match(compactWarningToast.body.message, /compact-fail/u)
  assert.match(compactWarningToast.body.message, /Missing required file: progress\.md/u)

  console.log("[context-task-planning] smoke test passed: OpenCode compact sync handles true, false, and failure signals")
} finally {
  rmSync(workspace, { recursive: true, force: true })
}
