import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { mkdtempSync, mkdirSync, readFileSync, rmSync, unlinkSync, utimesSync, writeFileSync } from "node:fs"
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
      latest_checkpoint: "Initial checkpoint.",
      blockers: [],
      phases: [],
      delegation: { enabled: true, single_writer: true, active: [] },
      updated_at: "2026-03-26T00:00:00Z",
    }, null, 2)}\n`,
    "utf8",
  )
  writeFileSync(path.join(planDir, "task_plan.md"), `# Task Plan: ${title}\n`, "utf8")
  writeFileSync(path.join(planDir, "progress.md"), `# Progress Log: ${title}\n`, "utf8")
  writeFileSync(path.join(planDir, "findings.md"), `# Findings: ${title}\n`, "utf8")
}

function touchTaskFile(planRoot, slug, name) {
  const filePath = path.join(planRoot, slug, name)
  const nextTime = new Date(Date.now() + 2000)
  utimesSync(filePath, nextTime, nextTime)
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
  writeTask(planRoot, "base-mobile-number-locale", "Base Mobile Number Locale")
  writeBinding(planRoot, "A", "base-app-mobile")
  writeBinding(planRoot, "B", "base-app-mobile-coldstart-optimization")
  writeFileSync(path.join(planRoot, ".active_task"), "base-app-mobile-coldstart-optimization\n", "utf8")

  const titles = new Map([
    ["A", "Session A"],
    ["B", "Session B"],
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

  const plugin = await ContextTaskPlanningOpenCodePlugin({ client, directory: workspace })

  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  await plugin.event({ event: { type: "session.created", properties: { info: { id: "B" } } } })
  await plugin.event({ event: { type: "session.created", properties: { info: { id: "C" } } } })
  assert.equal(titles.get("A"), "task:base-app-mobile | Session A")
  assert.equal(titles.get("B"), "task:base-app-mobile-coldstart-optimization | Session B")
  assert.equal(titles.get("C"), "Session C")
  assert.equal(toasts.some((toast) => toast.title === "Current task"), false)

  const fallbackTransformOutput = { system: [] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "C" }, fallbackTransformOutput)
  assert.doesNotMatch(fallbackTransformOutput.system.join("\n"), /Current task `base-app-mobile-coldstart-optimization`/u)
  assert.match(fallbackTransformOutput.system.join("\n"), /Workspace fallback resolved task `base-app-mobile-coldstart-optimization`/u)

  const fallbackTaskOutput = { args: { prompt: "Investigate helper script behavior" } }
  await plugin["tool.execute.before"](
    { tool: "Task", sessionID: "C", args: { prompt: "Investigate helper script behavior" } },
    fallbackTaskOutput,
  )
  assert.equal(fallbackTaskOutput.args.prompt, "Investigate helper script behavior")

  await plugin["chat.message"](
    { sessionID: "B", messageID: "user-quiet" },
    {
      message: { id: "user-quiet" },
      parts: [{ type: "text", text: "Keep optimizing coldstart startup behavior" }],
    },
  )
  const quietTransformOutput = { system: [] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "B" }, quietTransformOutput)
  assert.equal(quietTransformOutput.system.join("\n"), "")

  toasts.length = 0
  await plugin["chat.message"](
    { sessionID: "B", messageID: "user-route" },
    {
      message: { id: "user-route" },
      parts: [{ type: "text", text: "另外新任务：修复 billing webhook" }],
    },
  )
  const routeTransformOutput = { system: [] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "B" }, routeTransformOutput)
  assert.match(routeTransformOutput.system.join("\n"), /Route evidence for the assistant/u)
  assert.doesNotMatch(routeTransformOutput.system.join("\n"), /may be drifting away|looks likely unrelated/u)
  assert.equal(toasts.some((toast) => toast.title === "Task drift"), false)

  toasts.length = 0
  await plugin["tool.execute.after"](
    {
      tool: "functions.apply_patch",
      sessionID: "C",
      args: {
        patchText: `*** Begin Patch\n*** Update File: .planning/base-mobile-number-locale/state.json\n@@\n-\"mode\": \"execute\"\n+\"mode\": \"execute\"\n*** End Patch`,
      },
    },
    {},
  )
  const autoBound = JSON.parse(
    readFileSync(path.join(planRoot, ".sessions", sessionBindingName("opencode:C")), "utf8"),
  )
  assert.equal(autoBound.task_slug, "base-mobile-number-locale")
  assert.equal(autoBound.role, "writer")
  assert.equal(titles.get("C"), "task:base-mobile-number-locale | Session C")
  assert.equal(toasts.some((toast) => toast.title === "Task binding bootstrapped"), true)

  await plugin["chat.message"](
    { sessionID: "B", messageID: "user-1" },
    {
      message: { id: "user-1" },
      parts: [{ type: "text", text: "Implement idle sync for planning updates" }],
    },
  )
  await plugin.event({
    event: {
      type: "message.updated",
      properties: {
        sessionID: "B",
        info: {
          id: "asst-1",
          sessionID: "B",
          role: "assistant",
          parentID: "user-1",
          time: { created: 1711600000, completed: 1711600005 },
          path: { cwd: workspace, root: workspace },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "message.part.updated",
      properties: {
        sessionID: "B",
        time: 1711600004,
        part: {
          id: "tool-1",
          sessionID: "B",
          messageID: "asst-1",
          type: "tool",
          callID: "call-1",
          tool: "functions.apply_patch",
          state: {
            status: "completed",
            input: {},
            output: "",
            title: "Updated task guard",
            metadata: {},
            time: { start: 1711600001, end: 1711600004 },
          },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "message.part.updated",
      properties: {
        sessionID: "B",
        time: 1711600004,
        part: {
          id: "patch-1",
          sessionID: "B",
          messageID: "asst-1",
          type: "patch",
          hash: "abc123",
          files: ["skill/opencode-plugin/task-focus-guard.js"],
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "session.diff",
      properties: {
        sessionID: "B",
        diff: [{ file: "skill/scripts/task_guard.py" }],
      },
    },
  })
  await plugin.event({ event: { type: "session.idle", properties: { sessionID: "B" } } })

  const syncedState = JSON.parse(
    readFileSync(path.join(planRoot, "base-app-mobile-coldstart-optimization", "state.json"), "utf8"),
  )
  const syncedProgressPath = path.join(planRoot, "base-app-mobile-coldstart-optimization", "progress.md")
  const syncedProgress = readFileSync(syncedProgressPath, "utf8")
  assert.equal(syncedState.updated_at, "2024-03-28T04:26:45Z")
  assert.match(syncedState.latest_checkpoint, /Handled: Implement idle sync for planning updates/)
  assert.match(syncedProgress, /### Session: 2024-03-28T04:26:45Z/)
  assert.match(syncedProgress, /Handled: Implement idle sync for planning updates/)
  assert.match(syncedProgress, /`skill\/opencode-plugin\/task-focus-guard.js`/)
  assert.match(syncedProgress, /`skill\/scripts\/task_guard.py`/)

  const progressAfterFirstIdle = syncedProgress
  await plugin.event({ event: { type: "session.idle", properties: { sessionID: "B" } } })
  assert.equal(readFileSync(syncedProgressPath, "utf8"), progressAfterFirstIdle)

  await plugin["chat.message"](
    { sessionID: "B", messageID: "user-2" },
    {
      message: { id: "user-2" },
      parts: [{ type: "text", text: "Fallback sync should work without session idle" }],
    },
  )
  await plugin.event({
    event: {
      type: "message.updated",
      properties: {
        sessionID: "B",
        info: {
          id: "asst-2",
          sessionID: "B",
          role: "assistant",
          parentID: "user-2",
          time: { created: 1711600010000, completed: 1711600015000 },
          path: { cwd: workspace, root: workspace },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "message.part.updated",
      properties: {
        sessionID: "B",
        time: 1711600014,
        part: {
          id: "tool-2",
          sessionID: "B",
          messageID: "asst-2",
          type: "tool",
          callID: "call-2",
          tool: "functions.apply_patch",
          state: {
            status: "completed",
            input: {},
            output: "",
            title: "Updated docs",
            metadata: {},
            time: { start: 1711600011, end: 1711600014 },
          },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "message.part.updated",
      properties: {
        sessionID: "B",
        time: 1711600014,
        part: {
          id: "patch-2",
          sessionID: "B",
          messageID: "asst-2",
          type: "patch",
          hash: "def456",
          files: ["docs/opencode.md"],
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "session.diff",
      properties: {
        sessionID: "B",
        diff: [{ file: "docs/opencode.md" }],
      },
    },
  })
  await plugin.event({
    event: {
      type: "session.updated",
      properties: {
        info: {
          id: "B",
          directory: workspace,
        },
      },
    },
  })

  const fallbackSyncedState = JSON.parse(readFileSync(path.join(planRoot, "base-app-mobile-coldstart-optimization", "state.json"), "utf8"))
  const fallbackSyncedProgress = readFileSync(syncedProgressPath, "utf8")
  assert.equal(fallbackSyncedState.updated_at, "2024-03-28T04:26:55Z")
  assert.match(fallbackSyncedState.latest_checkpoint, /Handled: Fallback sync should work without session idle/)
  assert.match(fallbackSyncedProgress, /### Session: 2024-03-28T04:26:55Z/)
  assert.match(fallbackSyncedProgress, /`docs\/opencode\.md`/)

  await plugin["chat.message"](
    { sessionID: "B", messageID: "user-2b" },
    {
      message: { id: "user-2b" },
      parts: [{ type: "text", text: "Out-of-order fallback sync should wait for files" }],
    },
  )
  await plugin.event({
    event: {
      type: "message.updated",
      properties: {
        sessionID: "B",
        info: {
          id: "asst-2b",
          sessionID: "B",
          role: "assistant",
          parentID: "user-2b",
          time: { created: 1711600016, completed: 1711600018 },
          path: { cwd: workspace, root: workspace },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "message.part.updated",
      properties: {
        sessionID: "B",
        time: 1711600017,
        part: {
          id: "tool-2b",
          sessionID: "B",
          messageID: "asst-2b",
          type: "tool",
          callID: "call-2b",
          tool: "functions.bash",
          state: {
            status: "completed",
            input: {},
            output: "",
            title: "Checked changed files",
            metadata: {},
            time: { start: 1711600016, end: 1711600017 },
          },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "session.updated",
      properties: {
        info: {
          id: "B",
          directory: workspace,
        },
      },
    },
  })

  const noPrematureSyncState = JSON.parse(readFileSync(path.join(planRoot, "base-app-mobile-coldstart-optimization", "state.json"), "utf8"))
  assert.equal(noPrematureSyncState.updated_at, "2024-03-28T04:26:55Z")

  await plugin.event({
    event: {
      type: "session.diff",
      properties: {
        sessionID: "B",
        diff: [{ file: "docs/task-focus-guard.md" }],
      },
    },
  })

  const diffArrivedState = JSON.parse(readFileSync(path.join(planRoot, "base-app-mobile-coldstart-optimization", "state.json"), "utf8"))
  const diffArrivedProgress = readFileSync(syncedProgressPath, "utf8")
  assert.equal(diffArrivedState.updated_at, "2024-03-28T04:26:58Z")
  assert.match(diffArrivedState.latest_checkpoint, /Handled: Out-of-order fallback sync should wait for files/)
  assert.match(diffArrivedProgress, /### Session: 2024-03-28T04:26:58Z/)
  assert.match(diffArrivedProgress, /`docs\/task-focus-guard\.md`/)

  await plugin["chat.message"](
    { sessionID: "B", messageID: "user-3" },
    {
      message: { id: "user-3" },
      parts: [{ type: "text", text: "Fallback sync should use session diff when patch files are absent" }],
    },
  )
  await plugin.event({
    event: {
      type: "message.updated",
      properties: {
        sessionID: "B",
        info: {
          id: "asst-3",
          sessionID: "B",
          role: "assistant",
          parentID: "user-3",
          time: { created: 1711600020, completed: 1711600025 },
          path: { cwd: workspace, root: workspace },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "message.part.updated",
      properties: {
        sessionID: "B",
        time: 1711600024,
        part: {
          id: "tool-3",
          sessionID: "B",
          messageID: "asst-3",
          type: "tool",
          callID: "call-3",
          tool: "functions.bash",
          state: {
            status: "completed",
            input: {},
            output: "",
            title: "Checked docs links",
            metadata: {},
            time: { start: 1711600021, end: 1711600024 },
          },
        },
      },
    },
  })
  await plugin.event({
    event: {
      type: "session.diff",
      properties: {
        sessionID: "B",
        diff: [{ file: "docs/design.md" }],
      },
    },
  })
  await plugin.event({
    event: {
      type: "session.updated",
      properties: {
        info: {
          id: "B",
          directory: workspace,
        },
      },
    },
  })

  const diffOnlySyncedState = JSON.parse(readFileSync(path.join(planRoot, "base-app-mobile-coldstart-optimization", "state.json"), "utf8"))
  const diffOnlySyncedProgress = readFileSync(syncedProgressPath, "utf8")
  assert.equal(diffOnlySyncedState.updated_at, "2024-03-28T04:27:05Z")
  assert.match(diffOnlySyncedState.latest_checkpoint, /Handled: Fallback sync should use session diff when patch files are absent/)
  assert.match(diffOnlySyncedProgress, /### Session: 2024-03-28T04:27:05Z/)
  assert.match(diffOnlySyncedProgress, /`docs\/design\.md`/)

  toasts.length = 0
  await plugin["tool.execute.after"]({ tool: "functions.apply_patch", sessionID: "B", args: {} }, {})
  assert.equal(toasts.some((toast) => toast.title === "Task files stale"), false)
  touchTaskFile(planRoot, "base-app-mobile-coldstart-optimization", "task_plan.md")
  await plugin["tool.execute.after"](
    {
      tool: "multi_tool_use.parallel",
      sessionID: "B",
      args: {
        tool_uses: [
          { recipient_name: "functions.read", parameters: {} },
          { recipient_name: "functions.apply_patch", parameters: {} },
        ],
      },
    },
    {},
  )
  assert.deepEqual(toasts.at(-1), {
    title: "Task files stale",
    message: "Sync .planning/base-app-mobile-coldstart-optimization/ before more implementation or wrap-up.",
    variant: "warning",
    duration: 2600,
  })
  toasts.length = 0

  await plugin.event({ event: { type: "session.created", properties: { info: { id: "A" } } } })
  await plugin["tool.execute.after"]({ tool: "read" }, {})
  assert.equal(titles.get("A"), "task:base-app-mobile | Session A")
  assert.equal(titles.get("B"), "task:base-app-mobile-coldstart-optimization | Session B")

  unlinkSync(path.join(planRoot, ".active_task"))
  setTaskStatus(planRoot, "base-app-mobile", "paused")
  setTaskStatus(planRoot, "base-app-mobile-coldstart-optimization", "paused")
  setTaskStatus(planRoot, "base-mobile-number-locale", "paused")

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
