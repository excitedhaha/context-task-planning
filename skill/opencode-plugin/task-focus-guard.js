import { existsSync } from "node:fs"
import { statSync } from "node:fs"
import { spawnSync } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const SKILL_ROOT = path.resolve(PLUGIN_DIR, "..")
const CURRENT_TASK_SCRIPT = path.join(SKILL_ROOT, "scripts", "current-task.sh")
const CHECK_DRIFT_SCRIPT = path.join(SKILL_ROOT, "scripts", "check-task-drift.sh")
const TASK_TITLE_PREFIX_RE = /^task:[^|]+\s+\|\s+/
const FRESHNESS_WORK_THRESHOLD = 2
const FRESHNESS_AGE_THRESHOLD_MS = 20 * 60 * 1000
const FRESHNESS_TRACKED_TOOLS = new Set(["bash", "edit", "multiedit", "write", "task"])

function runJsonScript(script, args, cwd) {
  const result = spawnSync("sh", [script, ...args], {
    cwd,
    encoding: "utf8",
  })

  if (result.error || result.status !== 0) {
    return null
  }

  const stdout = (result.stdout || "").trim()
  if (!stdout) {
    return null
  }

  try {
    return JSON.parse(stdout)
  } catch {
    return null
  }
}

function collectPromptText(parts) {
  const lines = []
  for (const part of parts || []) {
    if (!part || part.ignored) continue
    if ((part.type === "text" || part.type === "reasoning") && typeof part.text === "string") {
      lines.push(part.text)
    }
  }
  return lines.join("\n").trim()
}

function currentTaskSummary(task) {
  const lines = [
    `[context-task-planning] Current task \`${task.slug}\` | status \`${task.status || "unknown"}\` | mode \`${task.mode || "unknown"}\` | phase \`${task.current_phase || "unknown"}\``,
    `Next action: ${task.next_action || "(none recorded)"}`,
    "Keep unrelated work out of this task; if the user's request does not belong here, confirm whether to continue, switch tasks, or initialize a new task before updating planning state.",
  ]

  if (task.binding_role) {
    lines.push(
      `Access: ${task.binding_role} | writer=${task.writer_display || "(none)"} | observers=${task.observer_count || 0}`,
    )
    if (task.binding_role === "observer") {
      lines.push(
        "Observe-only session: do not edit task_plan.md, progress.md, or state.json here. Delegate lane updates under delegates/<delegate-id>/ are still allowed.",
      )
    }
  }

  if (Array.isArray(task.repo_scope) && task.repo_scope.length > 0) {
    lines.push(
      `Repos: primary=${task.primary_repo || "(none)"} | scope=${task.repo_scope.join(", ")}`,
    )
  }

  return lines.join("\n")
}

function noActiveTaskReminder(result) {
  if (!result || result.classification !== "no-active-task" || !result.complex_prompt) {
    return null
  }
  return "[context-task-planning] No active task is selected for this workspace. For multi-step work, initialize or resume a task under `.planning/<slug>/` before implementation."
}

function driftReminder(result) {
  if (!result) return null
  const task = result.task || {}
  const slug = task.slug || "(unknown)"

  if (result.classification === "likely-unrelated") {
    return [
      `[context-task-planning] The newest user request looks likely unrelated to the current task \`${slug}\`.`,
      "Before acting, explicitly confirm whether to continue the current task, switch tasks, or create a new task.",
      `Do not silently mix unrelated work into \`.planning/${slug}/\`.`,
    ].join(" ")
  }

  if (result.classification === "unclear" && result.complex_prompt) {
    return [
      `[context-task-planning] The newest user request may be drifting away from the current task \`${slug}\`.`,
      "If it is not part of the same task, confirm whether to continue here, switch tasks, or create a new task before editing planning state.",
    ].join(" ")
  }

  return null
}

function taskToolPrefix(task, result) {
  if (!result) return null
  if (result.classification !== "likely-unrelated" && result.classification !== "unclear") {
    return null
  }

  return [
    `[context-task-planning] Active task: ${task.slug || "(unknown)"}`,
    `Drift classification: ${result.classification}`,
    "Before treating this as a subagent side quest, confirm whether the request belongs to the current task, should switch tasks, or should start a new task.",
    task.binding_role === "observer"
      ? "This session is observe-only for the main planning files; keep any subagent output inside delegate lanes instead."
      : "",
  ].filter(Boolean).join("\n")
}

function stripTaskPrefix(title) {
  return String(title || "").replace(TASK_TITLE_PREFIX_RE, "")
}

function prefixedSessionTitle(taskSlug, title) {
  const baseTitle = stripTaskPrefix(title).trim() || "Session"
  return `task:${taskSlug} | ${baseTitle}`
}

function visibleTaskSlug(task) {
  if (!task?.found || !task?.slug) {
    return ""
  }

  if (task.selection_source !== "session_binding") {
    return ""
  }

  return task.slug
}

function pluginSessionKey(sessionID) {
  const value = String(sessionID || "").trim()
  return value ? `opencode:${value}` : ""
}

function pluginEnabled(task) {
  if (task?.found) {
    return true
  }

  const planRoot = task?.plan_root
  return typeof planRoot === "string" && planRoot.length > 0 && existsSync(planRoot)
}

function planningFiles(task) {
  if (!task?.plan_dir) {
    return []
  }

  return ["state.json", "task_plan.md", "progress.md", "findings.md"]
    .map((name) => path.join(task.plan_dir, name))
    .filter((filePath) => existsSync(filePath))
}

function latestPlanningInfo(task) {
  const files = planningFiles(task)
  if (files.length === 0) {
    return null
  }

  let latestPath = files[0]
  let latestMtimeMs = statSync(files[0]).mtimeMs

  for (const filePath of files.slice(1)) {
    const mtimeMs = statSync(filePath).mtimeMs
    if (mtimeMs > latestMtimeMs) {
      latestMtimeMs = mtimeMs
      latestPath = filePath
    }
  }

  return {
    latestPath,
    latestFile: path.basename(latestPath),
    latestMtimeMs,
    ageMs: Math.max(0, Date.now() - latestMtimeMs),
  }
}

function defaultFreshnessState(planning) {
  return {
    lastPlanningMtimeMs: planning?.latestMtimeMs || 0,
    workEventsSincePlanning: 0,
    lastWorkTool: "",
    lastWorkAt: 0,
    toastPlanningMtimeMs: 0,
  }
}

function refreshFreshnessState(store, sessionID, task) {
  const planning = latestPlanningInfo(task)
  const state = store.get(sessionID) || defaultFreshnessState(planning)
  const planningUpdated = Boolean(planning && planning.latestMtimeMs > state.lastPlanningMtimeMs)

  if (planningUpdated && planning) {
    state.lastPlanningMtimeMs = planning.latestMtimeMs
    state.workEventsSincePlanning = 0
    state.lastWorkTool = ""
    state.lastWorkAt = 0
    state.toastPlanningMtimeMs = 0
  }

  store.set(sessionID, state)
  return { state, planning, planningUpdated }
}

function freshnessLevel(state, planning) {
  if (!state || !planning || state.workEventsSincePlanning < 1) {
    return null
  }

  if (state.workEventsSincePlanning >= FRESHNESS_WORK_THRESHOLD) {
    return "stale"
  }

  if (planning.ageMs >= FRESHNESS_AGE_THRESHOLD_MS) {
    return "aging"
  }

  return null
}

function freshnessReminder(task, state, planning) {
  const level = freshnessLevel(state, planning)
  if (!level) {
    return null
  }

  const slug = task.slug || "(unknown)"
  const ageMinutes = Math.max(1, Math.round(planning.ageMs / 60000))
  const count = state.workEventsSincePlanning
  const urgency =
    level === "stale"
      ? "Task files look stale for the current task"
      : "Task files may be getting stale for the current task"

  return [
    `[context-task-planning] ${urgency} \`${slug}\`: last planning update was \`${planning.latestFile}\` about ${ageMinutes}m ago, and ${count} tracked work step(s) have happened since then.`,
    `Before more implementation or wrap-up, sync \`.planning/${slug}/\` with at least the current progress and next_action.`,
  ].join(" ")
}

function freshnessToastMessage(task, state, planning) {
  const reminder = freshnessReminder(task, state, planning)
  if (!reminder) {
    return null
  }

  return {
    title: "Task files stale",
    message: `Sync .planning/${task.slug}/ before more implementation or wrap-up.`,
    variant: "warning",
  }
}

function freshnessTaskPrefix(task, state, planning) {
  const level = freshnessLevel(state, planning)
  if (!level) {
    return null
  }

  return [
    `[context-task-planning] Task files may be stale for ${task.slug || "(unknown)"}.`,
    `Last planning update: ${planning.latestFile}. Work steps since then: ${state.workEventsSincePlanning}.`,
    "Before or after this subagent work, sync `.planning/<slug>/` with the current progress and next_action.",
  ].join("\n")
}

function trackableTool(toolName) {
  return FRESHNESS_TRACKED_TOOLS.has(String(toolName || "").toLowerCase())
}

function resolveSessionID(...values) {
  for (const value of values) {
    if (!value) {
      continue
    }

    if (typeof value === "string" && value.trim()) {
      return value.trim()
    }

    if (typeof value === "object") {
      const nested =
        resolveSessionID(
          value.sessionID,
          value.sessionId,
          value.id,
          value.session,
          value.properties?.info?.id,
        ) || ""
      if (nested) {
        return nested
      }
    }
  }

  return ""
}

export const ContextTaskPlanningOpenCodePlugin = async ({ client, directory, worktree }) => {
  const baseCwd = worktree || directory || process.cwd()
  const driftBySession = new Map()
  const promptBySession = new Map()
  const taskBySession = new Map()
  const freshnessBySession = new Map()
  let lastSessionID = ""

  function rememberSessionID(...values) {
    const sessionID = resolveSessionID(...values)
    if (sessionID) {
      lastSessionID = sessionID
    }
    return sessionID || lastSessionID
  }

  async function showToast(title, message, variant = "info") {
    if (!client?.tui?.showToast) {
      return
    }

    try {
      await client.tui.showToast({
        body: {
          title,
          message,
          variant,
          duration: 2600,
        },
        query: {
          directory: baseCwd,
        },
      })
    } catch {}
  }

  async function ensureSessionTitle(sessionID, taskSlug) {
    if (!client?.session?.get || !client?.session?.update || !sessionID) {
      return
    }

    try {
      const response = await client.session.get({
        path: { id: sessionID },
        query: { directory: baseCwd },
      })
      const session = response?.data
      if (!session?.title) {
        return
      }

      const nextTitle = taskSlug
        ? prefixedSessionTitle(taskSlug, session.title)
        : stripTaskPrefix(session.title).trim() || "Session"
      if (session.title === nextTitle) {
        return
      }

      await client.session.update({
        path: { id: sessionID },
        query: { directory: baseCwd },
        body: { title: nextTitle },
      })
    } catch {}
  }

  async function syncVisibleTask(sessionID, task, drift) {
    if (!sessionID) {
      return
    }

    const taskSlug = visibleTaskSlug(task)
    const previous = taskBySession.get(sessionID) || ""

    if (taskSlug) {
      taskBySession.set(sessionID, taskSlug)
    } else {
      taskBySession.delete(sessionID)
    }

    await ensureSessionTitle(sessionID, taskSlug)

    if (!taskSlug) {
      return
    }

    if (previous !== taskSlug) {
      await showToast("Current task", taskSlug, "info")
    }

    if (drift?.classification === "likely-unrelated") {
      await showToast(
        "Task drift",
        `Current task is ${task.slug}; confirm before switching work.`,
        "warning",
      )
    }
  }

  function readCurrentTask(cwd = baseCwd, sessionID = "") {
    const args = ["--json", "--cwd", cwd]
    const sessionKey = pluginSessionKey(sessionID)
    if (sessionKey) {
      args.push("--session-key", sessionKey)
    }
    return runJsonScript(CURRENT_TASK_SCRIPT, args, cwd)
  }

  function readDrift(prompt, cwd = baseCwd, sessionID = "") {
    if (!prompt || !prompt.trim()) return null
    const args = ["--json", "--cwd", cwd]
    const sessionKey = pluginSessionKey(sessionID)
    if (sessionKey) {
      args.push("--session-key", sessionKey)
    }
    args.push("--prompt", prompt)
    return runJsonScript(
      CHECK_DRIFT_SCRIPT,
      args,
      cwd,
    )
  }

  return {
    "chat.message": async (input, output) => {
      const sessionID = rememberSessionID(input, output)
      const currentTask = readCurrentTask(baseCwd, sessionID)
      if (!pluginEnabled(currentTask)) {
        if (sessionID) {
          driftBySession.delete(sessionID)
          promptBySession.delete(sessionID)
          taskBySession.delete(sessionID)
        }
        return
      }

      const prompt = collectPromptText(output.parts)
      if (sessionID) {
        promptBySession.set(sessionID, prompt)
      }

      const drift = readDrift(prompt, baseCwd, sessionID)
      if (drift && sessionID) {
        driftBySession.set(sessionID, drift)
      }

      const task = drift?.task?.found ? drift.task : currentTask
      await syncVisibleTask(sessionID, task, drift)
    },

    "experimental.chat.system.transform": async (input, output) => {
      const sessionID = rememberSessionID(input)
      const mapSessionID = sessionID || "default"
      const task = readCurrentTask(baseCwd, sessionID)
      if (!pluginEnabled(task)) {
        return
      }

      const drift = driftBySession.get(mapSessionID) || readDrift(promptBySession.get(mapSessionID) || "", baseCwd, sessionID)
      const { state: freshnessState, planning } = refreshFreshnessState(freshnessBySession, mapSessionID, task)

      if (task && task.found) {
        output.system.push(currentTaskSummary(task))
        const reminder = driftReminder(drift)
        if (reminder) {
          output.system.push(reminder)
        }
        const freshness = freshnessReminder(task, freshnessState, planning)
        if (freshness) {
          output.system.push(freshness)
        }
        return
      }

      const noTaskHint = noActiveTaskReminder(drift)
      if (noTaskHint) {
        output.system.push(noTaskHint)
      }
    },

    "tool.execute.before": async (input, output) => {
      const sessionID = rememberSessionID(input, output)
      const currentTask = readCurrentTask(baseCwd, sessionID)
      if (!pluginEnabled(currentTask)) {
        return
      }

      const toolName = String(input.tool || "").toLowerCase()
      if (toolName !== "task") {
        return
      }

      const drift = sessionID ? driftBySession.get(sessionID) : null
      if (!drift) {
        const { state: freshnessState, planning } = refreshFreshnessState(
          freshnessBySession,
          sessionID || "default",
          currentTask,
        )
        const freshnessPrefix = freshnessTaskPrefix(currentTask, freshnessState, planning)
        if (!freshnessPrefix || !output.args || typeof output.args !== "object") {
          return
        }
        if (typeof output.args.prompt === "string" && !output.args.prompt.includes("Task files may be stale")) {
          output.args.prompt = `${freshnessPrefix}\n\n${output.args.prompt}`
        }
        return
      }

      const task = drift.task && drift.task.found ? drift.task : currentTask
      if (!task || !task.found) {
        return
      }

      const { state: freshnessState, planning } = refreshFreshnessState(
        freshnessBySession,
        sessionID || "default",
        task,
      )
      const prefixes = [taskToolPrefix(task, drift), freshnessTaskPrefix(task, freshnessState, planning)].filter(
        Boolean,
      )
      const prefix = prefixes.join("\n\n")
      if (!prefix || !output.args || typeof output.args !== "object") {
        return
      }

      if (typeof output.args.prompt === "string" && !output.args.prompt.includes("[context-task-planning]")) {
        output.args.prompt = `${prefix}\n\n${output.args.prompt}`
      }
    },

    "shell.env": async (input, output) => {
      const sessionID = rememberSessionID(input, output)
      const task = readCurrentTask(input.cwd || baseCwd, sessionID)
      if (!pluginEnabled(task)) {
        return
      }

      if (!task || !task.found || !task.slug) {
        return
      }

      output.env = {
        ...output.env,
        PLAN_SESSION_KEY: pluginSessionKey(sessionID),
      }
    },

    "tool.execute.after": async (input, output) => {
      const sessionID = rememberSessionID(input, output)
      const task = readCurrentTask(baseCwd, sessionID)
      if (!pluginEnabled(task)) {
        return
      }

      const previousTaskSlug = sessionID ? taskBySession.get(sessionID) || "" : ""
      const currentTaskSlug = visibleTaskSlug(task)
      if (currentTaskSlug !== previousTaskSlug) {
        await syncVisibleTask(sessionID, task, null)
      }

      if (!task?.found) {
        return
      }

      const toolName = String(input.tool || "").toLowerCase()
      const { state, planning, planningUpdated } = refreshFreshnessState(
        freshnessBySession,
        sessionID || "default",
        task,
      )

      if (!planning || !trackableTool(toolName) || planningUpdated) {
        return
      }

      state.workEventsSincePlanning += 1
      state.lastWorkTool = toolName
      state.lastWorkAt = Date.now()
      freshnessBySession.set(sessionID || "default", state)

      const toast = freshnessToastMessage(task, state, planning)
      if (!toast || state.toastPlanningMtimeMs === planning.latestMtimeMs) {
        return
      }

      state.toastPlanningMtimeMs = planning.latestMtimeMs
      freshnessBySession.set(sessionID || "default", state)
      await showToast(toast.title, toast.message, toast.variant)
    },

    event: async ({ event }) => {
      if (event?.type !== "session.created") {
        return
      }

      const sessionID = rememberSessionID(event)
      const task = readCurrentTask(baseCwd, sessionID)
      if (!pluginEnabled(task)) {
        return
      }

      refreshFreshnessState(freshnessBySession, sessionID, task)
      await syncVisibleTask(sessionID, task, null)
    },
  }
}
