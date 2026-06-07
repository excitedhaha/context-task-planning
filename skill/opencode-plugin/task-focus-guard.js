import { existsSync, mkdirSync, writeFileSync, readdirSync } from "node:fs"
import { readFileSync } from "node:fs"
import { statSync } from "node:fs"
import { spawnSync } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const PLUGIN_VERSION = "0.8.4" // sync with VERSION file

/**
 * Discover the skill root directory containing scripts/task_guard.py.
 * Supports: env override, legacy symlink layout, global OpenCode install,
 * project-local OpenCode install, and ancestor directory search.
 */
function resolveSkillRoot(directory) {
  const marker = path.join("scripts", "task_guard.py")

  // 1. Environment variable override (development / CI)
  const envOverride = (process.env.CONTEXT_TASK_PLANNING_SKILL_DIR || "").trim()
  if (envOverride && existsSync(path.join(envOverride, marker))) {
    return envOverride
  }

  // 2. Legacy symlink layout: skill is at ../ relative to plugin file
  const legacyRoot = path.resolve(PLUGIN_DIR, "..")
  if (existsSync(path.join(legacyRoot, marker))) {
    return legacyRoot
  }

  // 3. Global OpenCode skill install
  const home = process.env.HOME || process.env.USERPROFILE || ""
  if (home) {
    const globalSkill = path.join(home, ".config", "opencode", "skills", "context-task-planning")
    if (existsSync(path.join(globalSkill, marker))) {
      return globalSkill
    }
  }

  // 4. Project-local OpenCode skill install
  if (directory) {
    const localSkill = path.join(directory, ".opencode", "skills", "context-task-planning")
    if (existsSync(path.join(localSkill, marker))) {
      return localSkill
    }
  }

  // 5. Walk ancestor directories looking for skill/
  if (directory) {
    for (let dir = directory; dir !== path.dirname(dir); dir = path.dirname(dir)) {
      if (existsSync(path.join(dir, "skill", marker))) {
        return path.join(dir, "skill")
      }
    }
  }

  return null
}

const COMMAND_SCRIPT_NAMES = {
  "task-current.md": "current-task.sh",
  "task-done.md": "done-task.sh",
  "task-drift.md": "check-task-drift.sh",
  "task-init.md": "init-task.sh",
  "task-list.md": "list-tasks.sh",
  "task-validate.md": "validate-task.sh",
}

const COMMAND_MARKER_RE = /^<!-- context-task-planning-opencode:managed version=([^ ]+) -->/mu

function managedCommandContent(content) {
  return `<!-- context-task-planning-opencode:managed version=${PLUGIN_VERSION} -->\n${content}`
}

function managedCommandVersion(content) {
  const match = String(content || "").match(COMMAND_MARKER_RE)
  return match ? String(match[1] || "").trim() : ""
}

function looksLikeLegacyGeneratedCommand(file, content) {
  const scriptName = COMMAND_SCRIPT_NAMES[file]
  const text = String(content || "")
  return Boolean(
    scriptName &&
      text.includes("context-task-planning") &&
      text.includes("Requirements:") &&
      text.includes(scriptName),
  )
}

/**
 * Auto-install slash commands from bundled commands/ directory to
 * ~/.config/opencode/commands/ on first load (npm package mode).
 * Commands use {{SKILL_SCRIPTS_DIR}} placeholder replaced with actual skill path.
 */
function autoInstallCommands(skillRoot) {
  const bundledDir = path.join(PLUGIN_DIR, "commands")
  if (!existsSync(bundledDir)) return // no bundled commands (symlink mode)

  const home = process.env.HOME || process.env.USERPROFILE || ""
  if (!home) return

  const targetDir = path.join(home, ".config", "opencode", "commands")
  const scriptsDir = skillRoot ? path.join(skillRoot, "scripts") : ""

  try {
    const files = readdirSync(bundledDir).filter(f => f.endsWith(".md"))
    for (const file of files) {
      const target = path.join(targetDir, file)
      const source = path.join(bundledDir, file)
      let content = readFileSync(source, "utf8")
      if (scriptsDir) {
        content = content.replace(/\{\{SKILL_SCRIPTS_DIR\}\}/g, scriptsDir)
      }
      content = managedCommandContent(content)

      if (existsSync(target)) {
        const existing = readFileSync(target, "utf8")
        const managedVersion = managedCommandVersion(existing)
        if (!managedVersion && !looksLikeLegacyGeneratedCommand(file, existing)) {
          continue
        }
        if (managedVersion === PLUGIN_VERSION && existing === content) {
          continue
        }
      }

      mkdirSync(targetDir, { recursive: true })
      writeFileSync(target, content, "utf8")
    }
  } catch { /* non-fatal: commands are helpful but not required */ }
}

const TASK_TITLE_PREFIX_RE = /^task:[^|]+\s+\|\s+/
const FRESHNESS_WORK_THRESHOLD = 2
const FRESHNESS_AGE_THRESHOLD_MS = 20 * 60 * 1000
const FRESHNESS_TRACKED_TOOLS = new Set(["apply_patch", "bash", "edit", "multiedit", "write", "task"])
const PRUNE_TOAST_COOLDOWN_MS = 60 * 60 * 1000
const PLANNING_FILES = ["state.json", "task_plan.md", "progress.md", "findings.md"]
const FRESHNESS_SYNC_FILES = ["state.json", "progress.md"]

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

function runJsonCommand(command, args, cwd) {
  const result = spawnSync(command, args, {
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

function runTextScript(script, args, cwd) {
  const result = spawnSync("sh", [script, ...args], {
    cwd,
    encoding: "utf8",
  })

  if (result.error || result.status !== 0) {
    return ""
  }

  return String(result.stdout || "").trim()
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
    const matched = Array.isArray(result.matched_terms) && result.matched_terms.length > 0
      ? result.matched_terms.join(", ")
      : "none"
    const cues = Array.isArray(result.switch_cues) && result.switch_cues.length > 0
      ? result.switch_cues.join(", ")
      : "none"
    return [
      `[context-task-planning] Route evidence for the assistant: the lightweight heuristic is \`likely-unrelated\` for current task \`${slug}\`.`,
      `Switch cues: ${cues}. Shared terms: ${matched}.`,
      "Use the conversation and current task goal to decide same-task, different-task, or unclear. If different-task or genuinely unclear, ask the user before updating planning state or launching subagents; if same-task, continue without surfacing this evidence.",
    ].join(" ")
  }

  return null
}

function taskToolPrefix(task, result) {
  if (!result) return null
  if (result.classification !== "likely-unrelated") {
    return null
  }

  return [
    `[context-task-planning] Active task: ${task.slug || "(unknown)"}`,
    `Route evidence: heuristic classification is ${result.classification}`,
    "Use the surrounding conversation and task goal to decide whether the subagent belongs to the current task; if not, ask the user or return a routing mismatch instead of continuing.",
    task.binding_role === "observer"
      ? "This session is observe-only for the main planning files; keep any subagent output inside delegate lanes instead."
      : "",
  ].filter(Boolean).join("\n")
}

function planningRecoveryPaths(task) {
  if (!task?.plan_dir) {
    return null
  }

  return {
    state: path.resolve(task.plan_dir, "state.json"),
    progress: path.resolve(task.plan_dir, "progress.md"),
    taskPlan: path.resolve(task.plan_dir, "task_plan.md"),
  }
}

function matchesTaskPlanningFile(filePath, task, fileName) {
  const text = String(filePath || "").trim()
  if (!text || !task?.slug || !fileName) {
    return false
  }

  const normalized = text.replaceAll("\\", "/")
  const expectedSuffix = `/.planning/${task.slug}/${fileName}`
  if (normalized.endsWith(expectedSuffix)) {
    return true
  }

  const paths = planningRecoveryPaths(task)
  if (!paths) {
    return false
  }

  const absoluteTarget =
    fileName === "state.json"
      ? paths.state
      : fileName === "progress.md"
        ? paths.progress
        : paths.taskPlan
  return path.resolve(text) === absoluteTarget
}

function readFileTargetsFromTool(toolName, args) {
  const normalized = normalizedToolName(toolName)
  if (normalized === "read") {
    return [String(args?.filePath || "").trim()].filter(Boolean)
  }

  if (normalized === "parallel" && Array.isArray(args?.tool_uses)) {
    return args.tool_uses.flatMap((toolUse) =>
      readFileTargetsFromTool(toolUse?.recipient_name, toolUse?.parameters || {}),
    )
  }

  return []
}

function writeFileTargetsFromPatchText(patchText) {
  const text = String(patchText || "")
  if (!text) {
    return []
  }

  const targets = []
  const pattern = /^\*\*\* (?:Add|Update|Delete) File: (.+)$/gmu
  for (const match of text.matchAll(pattern)) {
    const value = String(match[1] || "").trim()
    if (value) {
      targets.push(value)
    }
  }
  return targets
}

function writeFileTargetsFromTool(toolName, args) {
  const normalized = normalizedToolName(toolName)
  if (normalized === "write" || normalized === "edit" || normalized === "multiedit") {
    return [String(args?.filePath || "").trim()].filter(Boolean)
  }

  if (normalized === "apply_patch") {
    return writeFileTargetsFromPatchText(args?.patchText)
  }

  if (normalized === "parallel" && Array.isArray(args?.tool_uses)) {
    return args.tool_uses.flatMap((toolUse) =>
      writeFileTargetsFromTool(toolUse?.recipient_name, toolUse?.parameters || {}),
    )
  }

  return []
}

function planningTaskSlugFromPath(filePath) {
  const normalized = String(filePath || "").trim().replaceAll("\\", "/")
  if (!normalized) {
    return ""
  }

  const match = normalized.match(/(?:^|\/)\.planning\/([^/]+)\/(state\.json|task_plan\.md|progress\.md|findings\.md)$/u)
  return match ? String(match[1] || "").trim() : ""
}

function isMainPlanningFileForTask(filePath, task) {
  const text = String(filePath || "").trim()
  if (!text || !task?.slug || !task?.plan_dir) {
    return false
  }
  const normalized = text.replaceAll("\\", "/")
  if (planningTaskSlugFromPath(normalized) === task.slug) {
    return true
  }
  const absolute = path.resolve(text)
  return PLANNING_FILES.some((fileName) => absolute === path.resolve(task.plan_dir, fileName))
}

function allFilesAreMainPlanningFiles(files, task) {
  return Array.isArray(files) && files.length > 0 && files.every((filePath) => isMainPlanningFileForTask(filePath, task))
}

function writtenPlanningTaskSlugs(input) {
  return uniqueItems(writeFileTargetsFromTool(input?.tool, input?.args).map(planningTaskSlugFromPath).filter(Boolean))
}

function planningRecoveryReminder(task, recovery) {
  if (!task?.slug || !recovery) {
    return ""
  }

  const missing = []
  if (recovery.needState) {
    missing.push(`.planning/${task.slug}/state.json`)
  }
  if (recovery.needProgress) {
    missing.push(`.planning/${task.slug}/progress.md`)
  }

  if (missing.length === 0) {
    return ""
  }

  return [
    `[context-task-planning] This session compacted recently for task \`${task.slug}\`.`,
    `Before more implementation, wrap-up, or planning edits, re-read ${missing.map((item) => `\`${item}\``).join(" and ")}.`,
    `If Hot Context or decisions matter for this turn, also re-read \`.planning/${task.slug}/task_plan.md\`.`,
    "Do not rely only on compressed transcript memory.",
  ].join(" ")
}

function truncateLine(value, max = 220) {
  const text = String(value || "").replace(/\s+/g, " ").trim()
  if (!text) {
    return ""
  }

  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}...` : text
}

function uniqueItems(values) {
  const seen = new Set()
  const items = []
  for (const value of values || []) {
    const text = String(value || "").trim()
    if (!text || seen.has(text)) {
      continue
    }
    seen.add(text)
    items.push(text)
  }
  return items
}

function timestampFromUnixSeconds(value) {
  const unix = Number(value)
  if (!Number.isFinite(unix) || unix <= 0) {
    return ""
  }

  const milliseconds = unix >= 1e12 ? unix : unix * 1000
  return new Date(milliseconds).toISOString().replace(/\.\d{3}Z$/, "Z")
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

function preflightRepoContextNeeded(preflight) {
  const repoContext = preflight?.repo_context || {}
  const repos = Array.isArray(repoContext.repos) ? repoContext.repos : []
  const repoScope = Array.isArray(repoContext.repo_scope)
    ? repoContext.repo_scope.filter((repo) => String(repo || "").trim())
    : []

  return (
    repos.length > 1 ||
    repoScope.length > 1 ||
    repos.some((repo) => String(repo?.binding_mode || "shared") !== "shared")
  )
}

function preflightSpecContextNeeded(preflight) {
  const task = preflight?.task || {}
  const spec = task.spec_context || {}
  const provider = String(spec.provider || "none")
  const status = String(spec.status || "none")
  return Boolean(
    provider !== "none" ||
    status !== "none" ||
    String(spec.primary_ref || "").trim() ||
    (Array.isArray(spec.artifact_refs) && spec.artifact_refs.length > 0) ||
    (Array.isArray(task.spec_candidate_refs) && task.spec_candidate_refs.length > 0),
  )
}

function appendPreflightRepoContext(lines, preflight) {
  const repoContext = preflight?.repo_context || {}
  const repos = Array.isArray(repoContext.repos) ? repoContext.repos : []
  const repoScope = Array.isArray(repoContext.repo_scope)
    ? repoContext.repo_scope.map((repo) => String(repo || "").trim()).filter(Boolean)
    : []
  const primaryRepo = String(repoContext.primary_repo || "").trim()

  if (primaryRepo) {
    lines.push(`Primary repo: ${primaryRepo}`)
  }
  if (repoScope.length > 0) {
    lines.push(`Repo scope: ${repoScope.join(", ")}`)
  }
  if (repos.length > 0) {
    lines.push("Repo/worktree bindings:")
    for (const repo of repos) {
      const id = String(repo?.id || "").trim()
      const bindingMode = String(repo?.binding_mode || "shared").trim() || "shared"
      const checkoutPath = String(repo?.checkout_path || repo?.path || ".").trim() || "."
      if (id) {
        lines.push(`- ${id}: ${bindingMode} at ${checkoutPath}`)
      }
    }
  }
}

function appendPreflightSpecContext(lines, preflight) {
  const task = preflight?.task || {}
  const spec = task.spec_context || {}
  const mode = String(spec.mode || "embedded")
  const provider = String(spec.provider || "none")
  const status = String(spec.status || "none")
  const primaryRef = String(spec.primary_ref || "").trim()
  const artifactRefs = Array.isArray(spec.artifact_refs)
    ? spec.artifact_refs.map((ref) => String(ref || "").trim()).filter(Boolean)
    : []
  const candidateRefs = Array.isArray(task.spec_candidate_refs)
    ? task.spec_candidate_refs.map((ref) => String(ref || "").trim()).filter(Boolean)
    : []
  const refs = uniqueItems(candidateRefs.length > 0 ? candidateRefs : artifactRefs).slice(0, 3)
  const resolutionHint = String(task.spec_resolution_hint || "").trim()

  lines.push(`Spec context: mode=${mode} | provider=${provider} | status=${status}`)
  if (primaryRef) {
    lines.push(`Primary spec ref: ${primaryRef}`)
  }
  if (refs.length > 0) {
    lines.push(`${candidateRefs.length > 0 ? "Spec candidates" : "Linked spec refs"}: ${refs.join("; ")}`)
  }
  if (resolutionHint) {
    lines.push(`Resolve explicitly: ${resolutionHint}`)
    lines.push("Treat candidates as non-authoritative unless one is resolved explicitly.")
  }
}

function conciseTaskPreflightPrefix(preflight, currentTask) {
  const task = preflight?.task || {}
  const routing = preflight?.routing || {}
  const slug = String(task.slug || currentTask?.slug || "(unknown)").trim()
  const role = String(task.binding_role || currentTask?.binding_role || "writer").trim()
  const classification = String(routing.classification || "-").trim()
  const lines = [
    `[context-task-planning] Current task: ${slug || "(unknown)"} | role: ${role || "writer"} | routing: ${classification || "-"}`,
  ]

  if (classification === "unclear") {
    lines.push("Task fit is unclear. Use the surrounding conversation and task goal; report a routing mismatch instead of continuing if it does not fit.")
  } else {
    lines.push("Keep this subagent scoped to the current task; report a routing mismatch instead of switching scope.")
  }

  if (preflightRepoContextNeeded(preflight)) {
    appendPreflightRepoContext(lines, preflight)
  }
  if (preflightSpecContextNeeded(preflight)) {
    appendPreflightSpecContext(lines, preflight)
  }

  return lines.join("\n")
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

function explicitTaskContextEligible(task) {
  return Boolean(task?.found && task?.slug && task.selection_source === "session_binding")
}

function workspaceFallbackReminder(task) {
  if (!task?.found || !task?.slug || explicitTaskContextEligible(task)) {
    return null
  }

  return [
    `[context-task-planning] Workspace fallback resolved task \`${task.slug}\`, but this OpenCode session is not explicitly bound to it.`,
    "This is a session-binding advisory, not a drift warning.",
    "Do not treat that fallback task as this session's current task unless you bind or resume it explicitly.",
  ].join(" ")
}

function shouldShowFallbackReminder(seen, sessionID) {
  if (!sessionID) {
    return true
  }
  if (seen.has(sessionID)) {
    return false
  }
  seen.add(sessionID)
  return true
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

function taskFiles(task, names = PLANNING_FILES) {
  if (!task?.plan_dir) {
    return []
  }

  return names
    .map((name) => path.join(task.plan_dir, name))
    .filter((filePath) => existsSync(filePath))
}

function freshnessPlanningInfo(task) {
  const syncFiles = taskFiles(task, FRESHNESS_SYNC_FILES)
  const files = syncFiles.length > 0 ? syncFiles : taskFiles(task)
  if (files.length === 0) {
    return null
  }

  let baselinePath = files[0]
  let baselineMtimeMs = statSync(files[0]).mtimeMs

  for (const filePath of files.slice(1)) {
    const mtimeMs = statSync(filePath).mtimeMs
    if (mtimeMs < baselineMtimeMs) {
      baselineMtimeMs = mtimeMs
      baselinePath = filePath
    }
  }

  return {
    trackedPaths: files,
    baselinePath,
    baselineFile: path.basename(baselinePath),
    baselineMtimeMs,
    ageMs: Math.max(0, Date.now() - baselineMtimeMs),
  }
}

function defaultFreshnessState(planning) {
  return {
    lastPlanningMtimeMs: planning?.baselineMtimeMs || 0,
    workEventsSincePlanning: 0,
    lastWorkTool: "",
    lastWorkAt: 0,
    toastPlanningMtimeMs: 0,
  }
}

function refreshFreshnessState(store, sessionID, task) {
  const planning = freshnessPlanningInfo(task)
  if (!sessionID) {
    return {
      state: defaultFreshnessState(planning),
      planning,
      planningUpdated: false,
    }
  }

  const state = store.get(sessionID) || defaultFreshnessState(planning)
  const planningUpdated = Boolean(planning && planning.baselineMtimeMs > state.lastPlanningMtimeMs)

  if (planningUpdated && planning) {
    state.lastPlanningMtimeMs = planning.baselineMtimeMs
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
    `[context-task-planning] ${urgency} \`${slug}\`: the freshness baseline is \`${planning.baselineFile}\` from about ${ageMinutes}m ago, and ${count} tracked work step(s) have happened since then.`,
    task?.binding_role === "observer"
      ? "This session is observe-only for main planning files; record observer results in a delegate lane or hand them to the writer session."
      : `Before more implementation or wrap-up, sync \`.planning/${slug}/\` with at least the current progress and next_action.`,
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

function normalizedToolName(toolName) {
  const value = String(toolName || "").trim().toLowerCase()
  if (!value) {
    return ""
  }

  return value.split("/").pop().split(".").pop()
}

function trackableTool(toolName) {
  const normalized = normalizedToolName(toolName)
  return normalized ? FRESHNESS_TRACKED_TOOLS.has(normalized) : false
}

function trackableParallelTool(args) {
  if (!args || typeof args !== "object" || !Array.isArray(args.tool_uses)) {
    return false
  }

  return args.tool_uses.some((toolUse) => trackableTool(toolUse?.recipient_name))
}

function trackableToolExecution(input) {
  if (trackableTool(input?.tool)) {
    return true
  }

  return normalizedToolName(input?.tool) === "parallel" && trackableParallelTool(input?.args)
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
  const resolvedDirectory = directory ? path.resolve(directory) : ""
  const resolvedWorktree = worktree ? path.resolve(worktree) : ""
  const baseCwd =
    (resolvedWorktree && resolvedWorktree !== "/" ? resolvedWorktree : "") ||
    resolvedDirectory ||
    process.cwd()
  const normalizedBaseCwd = path.resolve(baseCwd)

  // Resolve skill scripts path
  const SKILL_ROOT = resolveSkillRoot(resolvedDirectory)
  const skillMissing = !SKILL_ROOT
  if (skillMissing) {
    console.error(
      "[context-task-planning] Skill scripts not found at any known location. " +
      "Install the skill first: npx skills add excitedhaha/context-task-planning -g"
    )
  }
  const TASK_GUARD_SCRIPT = skillMissing ? "" : path.join(SKILL_ROOT, "scripts", "task_guard.py")
  const CURRENT_TASK_SCRIPT = skillMissing ? "" : path.join(SKILL_ROOT, "scripts", "current-task.sh")
  const CHECK_DRIFT_SCRIPT = skillMissing ? "" : path.join(SKILL_ROOT, "scripts", "check-task-drift.sh")
  const SUBAGENT_PREFLIGHT_SCRIPT = skillMissing ? "" : path.join(SKILL_ROOT, "scripts", "subagent-preflight.sh")
  let skillMissingToasted = false

  // Auto-install bundled slash commands (npm package mode)
  autoInstallCommands(SKILL_ROOT)
  const driftBySession = new Map()
  const promptBySession = new Map()
  const taskBySession = new Map()
  const completedTaskBySession = new Map()
  const fallbackAdvisoryBySession = new Set()
  const freshnessBySession = new Map()
  const planningRecoveryBySession = new Map()
  const userPromptByMessageID = new Map()
  const assistantStateByMessageID = new Map()
  const latestAssistantBySession = new Map()
  const latestDiffBySession = new Map()
  const pruneToastBySession = new Map()
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
  }

  function readCurrentTask(cwd = baseCwd, sessionID = "") {
    if (skillMissing) return null
    const args = ["--json", "--cwd", cwd]
    const sessionKey = pluginSessionKey(sessionID)
    if (sessionKey) {
      args.push("--session-key", sessionKey)
    }
    return runJsonScript(CURRENT_TASK_SCRIPT, args, cwd)
  }

  function readDrift(prompt, cwd = baseCwd, sessionID = "") {
    if (skillMissing) return null
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
    if (skillMissing) return null
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

  function readPruneStatus(task, cwd = baseCwd, sessionID = "") {
    if (skillMissing || !task?.found || !task?.slug) return null
    const args = [
      TASK_GUARD_SCRIPT,
      "context-prune",
      "--json",
      "--cwd",
      cwd,
      "--task",
      task.slug,
    ]
    const sessionKey = pluginSessionKey(sessionID)
    if (sessionKey) {
      args.push("--session-key", sessionKey)
    }
    return runJsonCommand("python3", args, cwd)
  }

  function pruneToastPayload(status) {
    const risk = String(status?.risk || "")
    if (!["recommend_prune", "strongly_recommend", "read_guard"].includes(risk)) {
      return null
    }
    const metrics = status?.metrics || {}
    return {
      title: risk === "read_guard" ? "Planning log is very large" : "Planning log can be pruned",
      message: `progress.md has ${metrics.lines || 0} lines and ${metrics.session_count || 0} sessions. Run context-prune --prepare when convenient.`,
      variant: risk === "read_guard" || risk === "strongly_recommend" ? "warning" : "info",
    }
  }

  function bindSessionTask(sessionID, taskSlug, role = "writer") {
    if (skillMissing) return { ok: false, message: "skill scripts not found" }
    const resolvedSessionKey = pluginSessionKey(sessionID)
    if (!resolvedSessionKey || !taskSlug) {
      return { ok: false, message: "missing session binding input" }
    }

    const args = [
      TASK_GUARD_SCRIPT,
      "bind-session-task",
      "--cwd",
      baseCwd,
      "--session-key",
      resolvedSessionKey,
      "--task",
      taskSlug,
      "--role",
      role,
    ]
    const result = spawnSync("python3", args, {
      cwd: baseCwd,
      encoding: "utf8",
    })
    const stderr = String(result.stderr || "").trim()
    const stdout = String(result.stdout || "").trim()
    return {
      ok: !result.error && result.status === 0,
      message: stderr || stdout,
    }
  }

  async function maybeAutoBindPlanningTask(sessionID, currentTask, input) {
    if (!sessionID || currentTask?.selection_source === "session_binding") {
      return currentTask
    }

    const slugs = writtenPlanningTaskSlugs(input)
    if (slugs.length !== 1) {
      return currentTask
    }

    const targetSlug = slugs[0]
    if (!targetSlug || targetSlug === currentTask?.slug) {
      return currentTask
    }

    const writerResult = bindSessionTask(sessionID, targetSlug, "writer")
    if (writerResult.ok) {
      const reboundTask = readCurrentTask(baseCwd, sessionID)
      await syncVisibleTask(sessionID, reboundTask, null)
      await showToast(
        "Task binding bootstrapped",
        `Bound this session to .planning/${targetSlug}/ as writer after direct planning edits.`,
        "info",
      )
      return reboundTask
    }

    const observerResult = bindSessionTask(sessionID, targetSlug, "observer")
    if (observerResult.ok) {
      const reboundTask = readCurrentTask(baseCwd, sessionID)
      await syncVisibleTask(sessionID, reboundTask, null)
      const detail = truncateLine(writerResult.message || "writer binding required additional isolation")
      await showToast(
        "Task binding bootstrapped as observer",
        `Direct planning edits matched .planning/${targetSlug}/, but writer binding was blocked. ${detail}`,
        "warning",
      )
      return reboundTask
    }

    return currentTask
  }

  function requirePlanningRecovery(sessionID) {
    if (!sessionID) {
      return
    }

    planningRecoveryBySession.set(sessionID, {
      needState: true,
      needProgress: true,
    })
  }

  function maybeClearPlanningRecovery(sessionID) {
    const recovery = planningRecoveryBySession.get(sessionID)
    if (!recovery) {
      return
    }

    if (!recovery.needState && !recovery.needProgress) {
      planningRecoveryBySession.delete(sessionID)
    }
  }

  function notePlanningRecoveryRead(sessionID, task, input) {
    const recovery = planningRecoveryBySession.get(sessionID)
    if (!recovery) {
      return
    }

    const targets = readFileTargetsFromTool(input?.tool, input?.args)
    if (targets.some((filePath) => matchesTaskPlanningFile(filePath, task, "state.json"))) {
      recovery.needState = false
    }
    if (targets.some((filePath) => matchesTaskPlanningFile(filePath, task, "progress.md"))) {
      recovery.needProgress = false
    }

    planningRecoveryBySession.set(sessionID, recovery)
    maybeClearPlanningRecovery(sessionID)
  }

  function assistantState(messageID) {
    if (!messageID) {
      return null
    }

    let existing = assistantStateByMessageID.get(messageID)
    if (!existing) {
      existing = {
        messageID,
        sessionID: "",
        parentID: "",
        createdAt: "",
        completedAt: "",
        cwd: "",
        actions: [],
        notes: [],
        files: [],
        tools: [],
      }
      assistantStateByMessageID.set(messageID, existing)
    }
    return existing
  }

  function mergeAssistantMessage(info) {
    if (!info || info.role !== "assistant" || !info.id) {
      return null
    }

    const state = assistantState(info.id)
    state.sessionID = String(info.sessionID || state.sessionID || "")
    state.parentID = String(info.parentID || state.parentID || "")
    state.createdAt = timestampFromUnixSeconds(info.time?.created) || state.createdAt
    state.completedAt = timestampFromUnixSeconds(info.time?.completed) || state.completedAt
    state.cwd = String(info.path?.cwd || state.cwd || "")
    latestAssistantBySession.set(state.sessionID, state)
    return state
  }

  function mergeAssistantPart(part) {
    if (!part || !part.messageID) {
      return null
    }

    const state = assistantState(part.messageID)
    state.sessionID = String(part.sessionID || state.sessionID || "")

    if (part.type === "patch" && Array.isArray(part.files)) {
      state.files = uniqueItems([...state.files, ...part.files.map((file) => String(file || "").trim())])
    }

    if (part.type === "tool") {
      state.tools = uniqueItems([...state.tools, String(part.tool || "").trim()])
      if (part.state?.status === "completed") {
        const title = truncateLine(part.state?.title || part.tool)
        if (title) {
          state.actions = uniqueItems([...state.actions, `Ran ${title}`])
        }
      }
    }

    if ((part.type === "text" || part.type === "reasoning") && typeof part.text === "string") {
      const summary = truncateLine(part.text)
      if (summary) {
        state.notes = uniqueItems([...state.notes, summary])
      }
    }

    latestAssistantBySession.set(state.sessionID, state)
    return state
  }

  function mergeSessionDiff(sessionID, diff) {
    if (!sessionID || !Array.isArray(diff)) {
      return
    }

    latestDiffBySession.set(
      sessionID,
      uniqueItems(diff.map((entry) => String(entry?.file || "").trim())),
    )
  }

  function recordUserPrompt(messageID, parts) {
    if (!messageID) {
      return
    }

    const prompt = collectPromptText(parts)
    if (!prompt) {
      return
    }

    userPromptByMessageID.set(messageID, prompt)
  }

  function readIdleSync(task, sessionID, payload) {
    if (skillMissing) return null
    if (!task?.found || !sessionID || !payload?.sourceID) {
      return null
    }

    const args = [
      TASK_GUARD_SCRIPT,
      "record-progress",
      "--json",
      "--cwd",
      payload.cwd || baseCwd,
      "--session-key",
      pluginSessionKey(sessionID),
      "--task",
      task.slug,
      "--source-id",
      payload.sourceID,
      "--timestamp",
      payload.timestamp,
      "--status",
      payload.status || "complete",
      "--checkpoint",
      payload.checkpoint,
      "--task-status",
      task.status || "",
      "--mode",
      task.mode || "",
      "--phase",
      task.current_phase || "",
      "--next-action",
      task.next_action || "",
      "--primary-repo",
      task.primary_repo || "",
    ]

    for (const repo of task.repo_scope || []) {
      args.push("--repo", String(repo))
    }
    for (const action of payload.actions || []) {
      args.push("--action", action)
    }
    for (const filePath of payload.files || []) {
      args.push("--file", filePath)
    }
    for (const note of payload.notes || []) {
      args.push("--note", note)
    }

    return runJsonCommand("python3", args, payload.cwd || baseCwd)
  }

  function idleSyncPayload(sessionID, trigger = "", task = null) {
    const assistant = latestAssistantBySession.get(sessionID)
    if (!assistant?.messageID || !assistant.completedAt) {
      return null
    }

    const files = uniqueItems([...(assistant.files || []), ...(latestDiffBySession.get(sessionID) || [])])
    const tools = uniqueItems(assistant.tools || [])
    if (files.length === 0 && tools.length === 0) {
      return null
    }

    if (allFilesAreMainPlanningFiles(files, task)) {
      return null
    }

    if (trigger !== "session.idle" && files.length === 0) {
      return null
    }

    const prompt = truncateLine(userPromptByMessageID.get(assistant.parentID) || "")
    const actions = uniqueItems([
      prompt ? `Handled: ${prompt}` : "Handled the latest OpenCode task turn.",
      ...(assistant.actions || []),
    ]).slice(0, 4)
    const notes = uniqueItems([
      tools.length > 0 ? `Tools: ${tools.join(", ")}` : "",
      ...(assistant.notes || []),
    ]).slice(0, 4)

    return {
      sourceID: `opencode-idle:${assistant.messageID}`,
      timestamp: assistant.completedAt || assistant.createdAt || new Date().toISOString(),
      status: "complete",
      checkpoint: actions[0] || "Recorded OpenCode idle sync progress.",
      actions,
      files,
      notes,
      cwd: assistant.cwd || baseCwd,
    }
  }

  function maybeSyncJournalFromActivity(task, session, sessionID, trigger) {
    if (!sessionID || !task?.found || task.binding_role === "observer") {
      return false
    }

    const payload = idleSyncPayload(sessionID, trigger, task)
    if (!payload) {
      return false
    }

    const result = readIdleSync(task, sessionID, payload)
    if (!result?.ok) {
      return false
    }

    latestDiffBySession.delete(sessionID)
    const cacheSessionID = sessionCacheKey(session, true)
    refreshFreshnessState(freshnessBySession, cacheSessionID, readCurrentTask(baseCwd, session?.readSessionID || sessionID))
    return true
  }

  async function maybeShowPruneToast(task, sessionID) {
    if (!sessionID || !task?.found) {
      return
    }
    const status = readPruneStatus(task, baseCwd, sessionID)
    const toast = pruneToastPayload(status)
    if (!toast) {
      return
    }
    const previous = pruneToastBySession.get(sessionID) || { at: 0, risk: "" }
    if (previous.risk === status.risk && Date.now() - previous.at < PRUNE_TOAST_COOLDOWN_MS) {
      return
    }
    pruneToastBySession.set(sessionID, { at: Date.now(), risk: status.risk })
    await showToast(toast.title, toast.message, toast.variant)
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

      recordUserPrompt(output.message?.id || input.messageID || "", output.parts)
      if (session.readSessionID) {
        latestDiffBySession.delete(session.readSessionID)
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
      const planningRecovery = visibleSessionID ? planningRecoveryBySession.get(visibleSessionID) || null : null
      const explicitTaskContext = explicitTaskContextEligible(task)

      if (task && task.found) {
        if (explicitTaskContext) {
          const planningRecoveryText = planningRecoveryReminder(task, planningRecovery)
          if (planningRecoveryText) {
            output.system.push(planningRecoveryText)
          }
          const reminder = driftReminder(drift)
          if (reminder) {
            output.system.push(reminder)
          }
          const freshness = freshnessReminder(task, freshnessState, planning)
          if (freshness) {
            output.system.push(freshness)
          }
        } else {
          const fallbackReminder = shouldShowFallbackReminder(fallbackAdvisoryBySession, visibleSessionID)
            ? workspaceFallbackReminder(task)
            : null
          if (fallbackReminder) {
            output.system.push(fallbackReminder)
          }
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
      const explicitTaskContext = explicitTaskContextEligible(currentTask)

      const prefixes = []

      if (explicitTaskContext && preflight) {
        const routingClassification = String(preflight.routing?.classification || "")
        if (
          (preflight.decision === "payload_only" ||
            preflight.decision === "payload_plus_delegate_recommended") &&
          preflight.prompt_prefix
        ) {
          prefixes.push(conciseTaskPreflightPrefix(preflight, currentTask))
        } else if (
          preflight.decision === "routing_only" &&
          (routingClassification === "related" || routingClassification === "unclear") &&
          (preflight.found || preflight.task?.slug)
        ) {
          prefixes.push(conciseTaskPreflightPrefix(preflight, currentTask))
        } else if (preflight.operator_message) {
          prefixes.push(preflight.operator_message)
        }
      } else if (drift) {
        const task = drift.task && drift.task.found ? drift.task : currentTask
        if (task && task.found) {
          prefixes.push(taskToolPrefix(task, drift))
        }
      }

      const prefix = prefixes.join("\n\n")
      if (!prefix || !output.args || typeof output.args !== "object") {
        return
      }

      if (typeof output.args.prompt === "string" && !output.args.prompt.includes("[context-task-planning]")) {
        output.args.prompt = `${prefix}\n\n${output.args.prompt}`
      }
    },

    "experimental.session.compacting": async (input, output) => {
      const session = sessionContext(input, output)
      const visibleSessionID = session.explicitSessionID || session.fallbackSessionID
      if (!visibleSessionID) {
        return
      }
      const task = readCurrentTask(baseCwd, session.readSessionID)
      if (explicitTaskContextEligible(task)) {
        requirePlanningRecovery(visibleSessionID)
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
      let task = readCurrentTask(baseCwd, session.readSessionID)
      if (!pluginEnabled(task)) {
        return
      }

      if (session.readSessionID) {
        task = await maybeAutoBindPlanningTask(session.readSessionID, task, input)
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
      if (cacheSessionID) {
        notePlanningRecoveryRead(cacheSessionID, task, input)
      }
      const { state, planning, planningUpdated } = refreshFreshnessState(
        freshnessBySession,
        cacheSessionID,
        task,
      )

      if (!planning || !trackableToolExecution(input) || planningUpdated || !cacheSessionID) {
        return
      }

      state.workEventsSincePlanning += 1
      state.lastWorkTool = toolName
      state.lastWorkAt = Date.now()
      freshnessBySession.set(cacheSessionID, state)

      const toast = freshnessToastMessage(task, state, planning)
      if (!toast || state.toastPlanningMtimeMs === planning.baselineMtimeMs) {
        return
      }

      state.toastPlanningMtimeMs = planning.baselineMtimeMs
      freshnessBySession.set(cacheSessionID, state)
      await showToast(toast.title, toast.message, toast.variant)
    },

    event: async ({ event }) => {
      if (event?.type === "message.updated") {
        mergeAssistantMessage(event.properties?.info)
      }

      if (event?.type === "message.part.updated") {
        mergeAssistantPart(event.properties?.part)
      }

      if (event?.type === "session.diff") {
        mergeSessionDiff(event.properties?.sessionID, event.properties?.diff)
      }

      if (event?.type === "session.idle") {
        const explicitSessionID = resolveExplicitSessionID(event)
        if (!explicitSessionID) {
          return
        }

        const session = sessionContext(event)
        const task = readCurrentTask(baseCwd, session.readSessionID)
        if (!pluginEnabled(task) || !task?.found || task.binding_role === "observer") {
          return
        }
        maybeSyncJournalFromActivity(task, session, explicitSessionID, "session.idle")
        await maybeShowPruneToast(task, explicitSessionID)
        return
      }

      if (
        event?.type !== "session.created" &&
        event?.type !== "session.updated" &&
        event?.type !== "tui.session.select" &&
        event?.type !== "session.status" &&
        event?.type !== "session.compacted" &&
        event?.type !== "message.updated" &&
        event?.type !== "session.diff"
      ) {
        return
      }

      // Show skill-missing toast once on session.created
      if (skillMissing && event?.type === "session.created" && !skillMissingToasted) {
        skillMissingToasted = true
        try {
          client.tui.showToast({
            body: {
              title: "context-task-planning: skill not found",
              message: "Run: npx skills add excitedhaha/context-task-planning -g",
              variant: "error",
              duration: 8000,
            },
            query: { directory: resolvedDirectory },
          })
        } catch { /* non-fatal */ }
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

      const task = readCurrentTask(baseCwd, session.readSessionID)
      if (!pluginEnabled(task)) {
        return
      }

      if (event?.type === "session.compacted") {
        if (explicitTaskContextEligible(task)) {
          requirePlanningRecovery(explicitSessionID)
        }
        return
      }

      const cacheSessionID = sessionCacheKey(session, true)
      refreshFreshnessState(freshnessBySession, cacheSessionID, task)
      if (
        event?.type === "session.updated" ||
        event?.type === "session.status" ||
        event?.type === "message.updated" ||
        event?.type === "session.diff"
      ) {
        maybeSyncJournalFromActivity(task, session, explicitSessionID, `event:${event.type}`)
      }
      await syncVisibleTask(session.explicitSessionID, task, null)
    },
  }
}
