import { existsSync } from "node:fs"
import { spawnSync } from "node:child_process"
import path from "node:path"
import { fileURLToPath } from "node:url"

const PLUGIN_DIR = path.dirname(fileURLToPath(import.meta.url))
const SKILL_ROOT = path.resolve(PLUGIN_DIR, "..")
const CURRENT_TASK_SCRIPT = path.join(SKILL_ROOT, "scripts", "current-task.sh")
const CHECK_DRIFT_SCRIPT = path.join(SKILL_ROOT, "scripts", "check-task-drift.sh")
const TASK_TITLE_PREFIX_RE = /^task:[^|]+\s+\|\s+/

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
  return [
    `[context-task-planning] Current task \`${task.slug}\` | status \`${task.status || "unknown"}\` | mode \`${task.mode || "unknown"}\` | phase \`${task.current_phase || "unknown"}\``,
    `Next action: ${task.next_action || "(none recorded)"}`,
    "Keep unrelated work out of this task; if the user's request does not belong here, confirm whether to continue, switch tasks, or initialize a new task before updating planning state.",
  ].join("\n")
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
  ].join("\n")
}

function stripTaskPrefix(title) {
  return String(title || "").replace(TASK_TITLE_PREFIX_RE, "")
}

function prefixedSessionTitle(taskSlug, title) {
  const baseTitle = stripTaskPrefix(title).trim() || "Session"
  return `task:${taskSlug} | ${baseTitle}`
}

function pluginEnabled(task) {
  if (task?.found) {
    return true
  }

  const planRoot = task?.plan_root
  return typeof planRoot === "string" && planRoot.length > 0 && existsSync(planRoot)
}

export const ContextTaskPlanningOpenCodePlugin = async ({ client, directory, worktree }) => {
  const baseCwd = worktree || directory || process.cwd()
  const driftBySession = new Map()
  const promptBySession = new Map()
  const taskBySession = new Map()

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
    if (!client?.session?.get || !client?.session?.update || !sessionID || !taskSlug) {
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

      const nextTitle = prefixedSessionTitle(taskSlug, session.title)
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
    if (!task?.found || !task.slug || !sessionID) {
      return
    }

    const previous = taskBySession.get(sessionID)
    taskBySession.set(sessionID, task.slug)

    await ensureSessionTitle(sessionID, task.slug)

    if (previous !== task.slug) {
      await showToast("Current task", task.slug, "info")
    }

    if (drift?.classification === "likely-unrelated") {
      await showToast(
        "Task drift",
        `Current task is ${task.slug}; confirm before switching work.`,
        "warning",
      )
    }
  }

  function readCurrentTask(cwd = baseCwd) {
    return runJsonScript(CURRENT_TASK_SCRIPT, ["--json", "--cwd", cwd], cwd)
  }

  function readDrift(prompt, cwd = baseCwd) {
    if (!prompt || !prompt.trim()) return null
    return runJsonScript(
      CHECK_DRIFT_SCRIPT,
      ["--json", "--cwd", cwd, "--prompt", prompt],
      cwd,
    )
  }

  return {
    "chat.message": async (input, output) => {
      const currentTask = readCurrentTask(baseCwd)
      if (!pluginEnabled(currentTask)) {
        driftBySession.delete(input.sessionID)
        promptBySession.delete(input.sessionID)
        taskBySession.delete(input.sessionID)
        return
      }

      const prompt = collectPromptText(output.parts)
      promptBySession.set(input.sessionID, prompt)

      const drift = readDrift(prompt)
      if (drift) {
        driftBySession.set(input.sessionID, drift)
      }

      const task = drift?.task?.found ? drift.task : currentTask
      await syncVisibleTask(input.sessionID, task, drift)
    },

    "experimental.chat.system.transform": async (input, output) => {
      const sessionID = input.sessionID || "default"
      const task = readCurrentTask(baseCwd)
      if (!pluginEnabled(task)) {
        return
      }

      const drift = driftBySession.get(sessionID) || readDrift(promptBySession.get(sessionID) || "")

      if (task && task.found) {
        output.system.push(currentTaskSummary(task))
        const reminder = driftReminder(drift)
        if (reminder) {
          output.system.push(reminder)
        }
        return
      }

      const noTaskHint = noActiveTaskReminder(drift)
      if (noTaskHint) {
        output.system.push(noTaskHint)
      }
    },

    "tool.execute.before": async (input, output) => {
      const currentTask = readCurrentTask(baseCwd)
      if (!pluginEnabled(currentTask)) {
        return
      }

      const toolName = String(input.tool || "").toLowerCase()
      if (toolName !== "task") {
        return
      }

      const drift = driftBySession.get(input.sessionID)
      if (!drift) {
        return
      }

      const task = drift.task && drift.task.found ? drift.task : currentTask
      if (!task || !task.found) {
        return
      }

      const prefix = taskToolPrefix(task, drift)
      if (!prefix || !output.args || typeof output.args !== "object") {
        return
      }

      if (typeof output.args.prompt === "string" && !output.args.prompt.includes("[context-task-planning]")) {
        output.args.prompt = `${prefix}\n\n${output.args.prompt}`
      }
    },

    "shell.env": async (input, output) => {
      const task = readCurrentTask(input.cwd || baseCwd)
      if (!pluginEnabled(task)) {
        return
      }

      if (!task || !task.found || !task.slug) {
        return
      }

      output.env = {
        ...output.env,
        PLAN_TASK: task.slug,
      }
    },

    event: async ({ event }) => {
      if (event?.type !== "session.created") {
        return
      }

      const sessionID = event.properties?.info?.id
      const task = readCurrentTask(baseCwd)
      if (!pluginEnabled(task)) {
        return
      }

      await syncVisibleTask(sessionID, task, null)
    },
  }
}
