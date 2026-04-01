import { existsSync } from "node:fs"
import { readFileSync } from "node:fs"
import { statSync } from "node:fs"
import { spawnSync } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const SKILL_ROOT = path.resolve(PLUGIN_DIR, "..")
const CURRENT_TASK_SCRIPT = path.join(SKILL_ROOT, "scripts", "current-task.sh")
const CHECK_DRIFT_SCRIPT = path.join(SKILL_ROOT, "scripts", "check-task-drift.sh")
const SUBAGENT_PREFLIGHT_SCRIPT = path.join(SKILL_ROOT, "scripts", "subagent-preflight.sh")
const COMPACT_SYNC_SCRIPT = path.join(SKILL_ROOT, "scripts", "compact-sync.sh")
const TASK_TITLE_PREFIX_RE = /^task:[^|]+\s+\|\s+/
const FRESHNESS_WORK_THRESHOLD = 2
const FRESHNESS_AGE_THRESHOLD_MS = 20 * 60 * 1000
const COMPACT_SYNC_DEBOUNCE_MS = 1500
const FRESHNESS_TRACKED_TOOLS = new Set(["bash", "edit", "multiedit", "write", "task"])
const COMPACT_SIGNAL_RE = /\b(compact|compaction|compress|compression|compressed)\b/i
const COMPACT_SIGNAL_VALUE_KEYS = new Set([
  "type",
  "reason",
  "action",
  "event",
  "kind",
  "name",
  "status",
  "phase",
  "updateType",
  "changeType",
  "mode",
])

function compactSignalKey(value) {
  return COMPACT_SIGNAL_RE.test(String(value || ""))
}

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

function hasCompactSignal(value, seen = new Set(), parentKey = "") {
  if (!value) {
    return false
  }

  if (typeof value === "string") {
    return (
      (COMPACT_SIGNAL_VALUE_KEYS.has(parentKey) || compactSignalKey(parentKey)) &&
      COMPACT_SIGNAL_RE.test(value)
    )
  }

  if (typeof value === "boolean") {
    return compactSignalKey(parentKey) && value
  }

  if (typeof value === "number") {
    return compactSignalKey(parentKey) && value > 0
  }

  if (typeof value !== "object") {
    return false
  }

  if (seen.has(value)) {
    return false
  }
  seen.add(value)

  if (Array.isArray(value)) {
    return value.some((item) => hasCompactSignal(item, seen, parentKey))
  }

  return Object.entries(value).some(([key, nested]) => {
    if (typeof nested === "boolean" || typeof nested === "number") {
      return hasCompactSignal(nested, seen, key)
    }
    return hasCompactSignal(nested, seen, key)
  })
}

function compactSyncIssueDetail(result) {
  const sources = []
  if (Array.isArray(result?.warnings)) {
    sources.push(...result.warnings)
  }
  sources.push(result?.main_sync?.message || "")
  sources.push(result?.artifact_sync?.message || "")

  for (const source of sources) {
    const lines = String(source || "")
      .split(/\r?\n/u)
      .map((line) => line.trim())
      .filter(Boolean)
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const cleaned = lines[index]
        .replace(/^\[context-task-planning\]\s*/u, "")
        .replace(/^-\s*/u, "")
        .trim()
      if (cleaned) {
        return cleaned
      }
    }
  }

  return ""
}

function compactSyncWarningToast(task, result) {
  const slug = result?.task?.slug || task?.slug || "(current task)"
  const detail = compactSyncIssueDetail(result)
  const message = !result
    ? `Compact sync status was unavailable for ${slug}; review .planning/${slug}/ manually if recovery looks stale.`
    : detail
      ? `${slug}: ${detail}`
      : `Compact sync did not complete cleanly for ${slug}; review .planning/${slug}/ manually.`

  return {
    title: "Compact sync warning",
    message,
    variant: "warning",
  }
}

function compactEventSignature(event) {
  try {
    return JSON.stringify(event) || String(event?.type || "compact")
  } catch {
    return String(event?.type || "compact")
  }
}

function shouldRunCompactSync(store, sessionID, event) {
  if (!sessionID || !hasCompactSignal(event)) {
    return false
  }

  const now = Date.now()
  const signature = compactEventSignature(event)
  const previous = store.get(sessionID)
  if (previous && previous.signature === signature && now - previous.at < COMPACT_SYNC_DEBOUNCE_MS) {
    return false
  }

  store.set(sessionID, { signature, at: now })
  return true
}

function currentTaskSummary(task) {
  const lines = [
    `[context-task-planning] Current task \`${task.slug}\` | status \`${task.status || "unknown"}\` | mode \`${task.mode || "unknown"}\` | phase \`${task.current_phase || "unknown"}\``,
    `Next action: ${task.next_action || "(none recorded)"}`,
    "Keep unrelated work out of this task; if the user's request does not belong here, confirm whether to continue, switch tasks, or initialize a new task before updating planning state.",
  ]
  const spec = task?.spec_context || {}
  if (spec.provider && spec.provider !== "none") {
    lines.push(
      `Spec context: mode=${spec.mode || "embedded"} | provider=${spec.provider} | status=${spec.status || "none"}`,
    )
    if (spec.primary_ref) {
      lines.push(`Primary spec ref: ${spec.primary_ref}`)
    }
    const candidateRefs = Array.isArray(task?.spec_candidate_refs) ? task.spec_candidate_refs : []
    if (candidateRefs.length > 0) {
      lines.push(`Spec candidates: ${candidateRefs.slice(0, 3).join("; ")}`)
    }
    if (typeof task?.spec_resolution_hint === "string" && task.spec_resolution_hint.trim()) {
      lines.push(`Resolve explicitly: ${task.spec_resolution_hint.trim()}`)
    }
  }

  if (task.binding_role) {
    lines.push(
      `Access: ${task.binding_role} | writer=${task.writer_display || "(none)"} | observers=${task.observer_count || 0}`,
    )
    if (task.binding_role === "observer") {
      lines.push(
        "Observe-only session: do not edit task_plan.md, progress.md, or state.json here. Delegate lane updates under delegates/<delegate-id>/ are still allowed.",
      )
    } else {
      lines.push(
        "If this turn materially changes task progress, blockers, or next_action, sync progress.md and state.json before you finish; if Hot Context changes, sync task_plan.md too.",
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

function taskTextFromArgs(args) {
  if (!args || typeof args !== "object") {
    return ""
  }

  return [args.description, args.prompt, args.command, args.subagent_type]
    .filter((value) => typeof value === "string" && value.trim())
    .join(" ")
    .trim()
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

function taskStateForSlug(planRoot, taskSlug) {
  if (!planRoot || !taskSlug) {
    return null
  }

  const statePath = path.join(planRoot, taskSlug, "state.json")
  if (!existsSync(statePath)) {
    return null
  }

  try {
    const parsed = JSON.parse(readFileSync(statePath, "utf8"))
    return parsed && typeof parsed === "object" ? parsed : null
  } catch {
    return null
  }
}

function completedTaskPrompt(taskSlug) {
  if (!taskSlug) {
    return null
  }

  return [
    `[context-task-planning] Nice work - the last bound task \`${taskSlug}\` is done.`,
    "Congratulate the user briefly, then ask whether they want to archive it now or start a new task.",
    "If the user already clearly chose one of those options, follow that choice instead of asking again.",
  ].join(" ")
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
  if (!sessionID) {
    return {
      state: defaultFreshnessState(planning),
      planning,
      planningUpdated: false,
    }
  }

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

function resolveExplicitSessionID(...values) {
  for (const value of values) {
    if (!value) {
      continue
    }

    if (typeof value === "string" && value.trim()) {
      return value.trim()
    }

    if (typeof value === "object") {
      const nested =
        resolveExplicitSessionID(
          value.sessionID,
          value.sessionId,
          value.id,
          value.session,
          value.properties?.sessionID,
          value.properties?.sessionId,
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
  const normalizedBaseCwd = path.resolve(baseCwd)
  const driftBySession = new Map()
  const promptBySession = new Map()
  const taskBySession = new Map()
  const completedTaskBySession = new Map()
  const freshnessBySession = new Map()
  const compactSyncBySession = new Map()
  const observedSessionIDs = new Set()
  let lastExplicitSessionID = ""

  function normalizeDirectory(value) {
    const text = String(value || "").trim()
    return text ? path.resolve(text) : ""
  }

  function sameWorkspaceDirectory(value) {
    const normalized = normalizeDirectory(value)
    return !normalized || normalized === normalizedBaseCwd
  }

  function visibleSessionEvent(event, sessionID) {
    if (!sessionID) {
      return false
    }

    if (!sameWorkspaceDirectory(event?.properties?.info?.directory)) {
      return false
    }

    if (event?.type === "session.updated" && observedSessionIDs.size > 0) {
      return observedSessionIDs.has(sessionID)
    }

    return true
  }

  function sessionContext(...values) {
    const explicitSessionID = resolveExplicitSessionID(...values)
    if (explicitSessionID) {
      observedSessionIDs.add(explicitSessionID)
      lastExplicitSessionID = explicitSessionID
    }

    const fallbackSessionID =
      !explicitSessionID && observedSessionIDs.size === 1 ? lastExplicitSessionID : ""

    return {
      explicitSessionID,
      fallbackSessionID,
      readSessionID: explicitSessionID || fallbackSessionID,
      ambiguous: !explicitSessionID && observedSessionIDs.size > 1,
    }
  }

  function sessionCacheKey(context, allowFallback = false) {
    if (context.explicitSessionID) {
      return context.explicitSessionID
    }

    if (allowFallback && context.fallbackSessionID) {
      return context.fallbackSessionID
    }

    return ""
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
      if (!session?.title || !sameWorkspaceDirectory(session?.directory)) {
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
      completedTaskBySession.delete(sessionID)
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

  function readSubagentPreflight(args, cwd = baseCwd, sessionID = "") {
    const scriptArgs = [
      "--json",
      "--cwd",
      cwd,
      "--host",
      "opencode",
      "--tool-name",
      "Task",
      "--task-text",
      taskTextFromArgs(args),
    ]
    const sessionKey = pluginSessionKey(sessionID)
    if (sessionKey) {
      scriptArgs.push("--session-key", sessionKey)
    }
    return runJsonScript(SUBAGENT_PREFLIGHT_SCRIPT, scriptArgs, cwd)
  }

  function readCompactSync(cwd = baseCwd, sessionID = "") {
    const scriptArgs = ["--json", "--host", "opencode"]
    const sessionKey = pluginSessionKey(sessionID)
    if (sessionKey) {
      scriptArgs.push("--session-key", sessionKey)
    }
    return runJsonScript(COMPACT_SYNC_SCRIPT, scriptArgs, cwd)
  }

  return {
    "chat.message": async (input, output) => {
      const session = sessionContext(input, output)
      const currentTask = readCurrentTask(baseCwd, session.readSessionID)
      if (!pluginEnabled(currentTask)) {
        if (session.explicitSessionID) {
          driftBySession.delete(session.explicitSessionID)
          promptBySession.delete(session.explicitSessionID)
          taskBySession.delete(session.explicitSessionID)
        }
        return
      }

      const prompt = collectPromptText(output.parts)
      const cacheSessionID = sessionCacheKey(session, true)
      if (cacheSessionID) {
        promptBySession.set(cacheSessionID, prompt)
      }

      const drift = readDrift(prompt, baseCwd, session.readSessionID)
      if (drift && cacheSessionID) {
        driftBySession.set(cacheSessionID, drift)
      }

      const task = drift?.task?.found ? drift.task : currentTask
      if (session.explicitSessionID) {
        await syncVisibleTask(session.explicitSessionID, task, drift)
      }
    },

    "experimental.chat.system.transform": async (input, output) => {
      const session = sessionContext(input)
      const visibleSessionID = session.explicitSessionID || session.fallbackSessionID
      const cacheSessionID = sessionCacheKey(session, true)
      const task = readCurrentTask(baseCwd, session.readSessionID)
      if (!pluginEnabled(task)) {
        return
      }

      const completedTaskSlug = visibleSessionID ? completedTaskBySession.get(visibleSessionID) || "" : ""
      if (completedTaskSlug && !task?.found) {
        const prompt = completedTaskPrompt(completedTaskSlug)
        if (prompt) {
          output.system.push(prompt)
        }
        completedTaskBySession.delete(visibleSessionID)
        return
      }

      const prompt = cacheSessionID ? promptBySession.get(cacheSessionID) || "" : ""
      const drift =
        (cacheSessionID ? driftBySession.get(cacheSessionID) : null) ||
        readDrift(prompt, baseCwd, session.readSessionID)
      const { state: freshnessState, planning } = refreshFreshnessState(freshnessBySession, cacheSessionID, task)

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
      const session = sessionContext(input, output)
      const currentTask = readCurrentTask(baseCwd, session.readSessionID)
      if (!pluginEnabled(currentTask)) {
        return
      }

      const toolName = String(input.tool || "").toLowerCase()
      if (toolName !== "task") {
        return
      }

      const cacheSessionID = sessionCacheKey(session, true)
      const preflight = readSubagentPreflight(
        output.args || input.args || {},
        baseCwd,
        session.readSessionID,
      )
      const drift = cacheSessionID ? driftBySession.get(cacheSessionID) : null

      const { state: freshnessState, planning } = refreshFreshnessState(
        freshnessBySession,
        cacheSessionID,
        currentTask,
      )
      const prefixes = []

      if (preflight) {
        if (
          (preflight.decision === "payload_only" ||
            preflight.decision === "payload_plus_delegate_recommended") &&
          preflight.prompt_prefix
        ) {
          prefixes.push(preflight.prompt_prefix)
        } else if (preflight.operator_message) {
          prefixes.push(preflight.operator_message)
        }
      } else if (drift) {
        const task = drift.task && drift.task.found ? drift.task : currentTask
        if (task && task.found) {
          prefixes.push(taskToolPrefix(task, drift))
        }
      }

      const freshnessPrefix = freshnessTaskPrefix(currentTask, freshnessState, planning)
      if (freshnessPrefix) {
        prefixes.push(freshnessPrefix)
      }

      const prefix = prefixes.join("\n\n")
      if (!prefix || !output.args || typeof output.args !== "object") {
        return
      }

      if (typeof output.args.prompt === "string" && !output.args.prompt.includes("[context-task-planning]")) {
        output.args.prompt = `${prefix}\n\n${output.args.prompt}`
      }
    },

    "shell.env": async (input, output) => {
      const session = sessionContext(input, output)
      const task = readCurrentTask(input.cwd || baseCwd, session.readSessionID)
      if (!pluginEnabled(task)) {
        return
      }

      const sessionID = session.explicitSessionID || session.fallbackSessionID
      if (!sessionID) {
        return
      }

      output.env = {
        ...output.env,
        PLAN_SESSION_KEY: pluginSessionKey(sessionID),
      }
    },

    "tool.execute.after": async (input, output) => {
      const session = sessionContext(input, output)
      const visibleSessionID = session.explicitSessionID || session.fallbackSessionID
      const previousTaskSlug = visibleSessionID ? taskBySession.get(visibleSessionID) || "" : ""
      const task = readCurrentTask(baseCwd, session.readSessionID)
      if (!pluginEnabled(task)) {
        return
      }

      if (visibleSessionID) {
        const currentTaskSlug = visibleTaskSlug(task)
        if (currentTaskSlug !== previousTaskSlug) {
          await syncVisibleTask(visibleSessionID, task, null)
        }

        if (!currentTaskSlug && previousTaskSlug) {
          const previousTask = taskStateForSlug(task?.plan_root, previousTaskSlug)
          if (previousTask?.status === "done") {
            completedTaskBySession.set(visibleSessionID, previousTaskSlug)
            await showToast(
              "Nice work",
              `${previousTaskSlug} is done. Want to archive it or start a new task?`,
              "info",
            )
          } else {
            completedTaskBySession.delete(visibleSessionID)
          }
        }
      }

      if (!task?.found) {
        return
      }

      const toolName = String(input.tool || "").toLowerCase()
      const cacheSessionID = sessionCacheKey(session, true)
      const { state, planning, planningUpdated } = refreshFreshnessState(
        freshnessBySession,
        cacheSessionID,
        task,
      )

      if (!planning || !trackableTool(toolName) || planningUpdated || !cacheSessionID) {
        return
      }

      state.workEventsSincePlanning += 1
      state.lastWorkTool = toolName
      state.lastWorkAt = Date.now()
      freshnessBySession.set(cacheSessionID, state)

      const toast = freshnessToastMessage(task, state, planning)
      if (!toast || state.toastPlanningMtimeMs === planning.latestMtimeMs) {
        return
      }

      state.toastPlanningMtimeMs = planning.latestMtimeMs
      freshnessBySession.set(cacheSessionID, state)
      await showToast(toast.title, toast.message, toast.variant)
    },

    event: async ({ event }) => {
      const compactEvent = hasCompactSignal(event)
      if (
        !compactEvent &&
        event?.type !== "session.created" &&
        event?.type !== "session.updated" &&
        event?.type !== "tui.session.select"
      ) {
        return
      }

      const explicitSessionID = resolveExplicitSessionID(event)
      if (!explicitSessionID) {
        return
      }

      if (!visibleSessionEvent(event, explicitSessionID)) {
        return
      }

      const session = sessionContext(event)

      let task = readCurrentTask(baseCwd, session.readSessionID)
      if (!pluginEnabled(task)) {
        return
      }

      if (shouldRunCompactSync(compactSyncBySession, session.readSessionID, event)) {
        const compactSync = readCompactSync(baseCwd, session.readSessionID)
        task = readCurrentTask(baseCwd, session.readSessionID)
        if (!compactSync || compactSync.ok === false) {
          const toast = compactSyncWarningToast(task, compactSync)
          await showToast(toast.title, toast.message, toast.variant)
        }
      }

      const cacheSessionID = sessionCacheKey(session, true)
      refreshFreshnessState(freshnessBySession, cacheSessionID, task)
      await syncVisibleTask(session.explicitSessionID, task, null)
    },
  }
}
