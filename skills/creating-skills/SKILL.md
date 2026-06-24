---
name: creating-skills
description: Create or update Agent Skills (SKILL.md) for this my-agent setup. Use when the user asks to make, add, write, or author a skill, teach a repeatable workflow, or capture domain knowledge for future sessions.
---

# Creating Skills

Skills are markdown playbooks the agent loads automatically when a task matches their `description`. A skill teaches *how* to do something; it does not add new tools by itself.

## Two locations

| Scope | Virtual path (agent file tools) | Filesystem path |
|-------|--------------------------------|-----------------|
| **Project** | `/skills/project/{name}/` | `./skills/{name}/` (repo root) |
| **User** | `/skills/{name}/` | `~/.my-agent/skills/{name}/` |

Project skills override user skills when names collide (project wins). Before creating, check both directories for an existing skill to update instead of duplicating.

Default paths come from `config.toml` `[paths].skills_project_dir` and `skills_user_dir`.

## When a skill is appropriate

Create or update a skill when:

- The same multi-step workflow will recur (deploy, backup, research pattern, tool usage).
- The user explicitly asks for a skill.
- You solved something non-obvious that future turns should reuse.

Do **not** create a skill for one-off tasks, trivial single-command answers, or facts that belong in a normal doc/README.

## Directory layout

```
{skill-name}/
├── SKILL.md              # required
├── references/           # optional deep docs
└── scripts/              # optional helper scripts
```

## SKILL.md format

1. YAML frontmatter between `---` lines.
2. Markdown body with steps, criteria, examples, edge cases.

**Required frontmatter**

- `name`: kebab-case, max 64 chars, **must match the parent directory name**
- `description`: third-person, specific; include WHAT it does and WHEN to use it (trigger keywords). Max 1024 chars.

**Optional frontmatter**

- `allowed-tools`: space-separated tool names this skill expects (e.g. `tavily_search execute`)
- `license`, `compatibility`, `metadata`

### Template

```markdown
---
name: my-skill-name
description: Does X for Y workflows. Use when the user mentions X, Y, or asks to Z.
allowed-tools: execute read_file
---

# My Skill Name

## When to use
- ...

## Procedure
1. ...
2. ...

## Examples
...

## Edge cases
- ...
```

## Authoring rules

1. **Concise** — assume the model is capable; only add non-obvious steps, project paths, and conventions.
2. **Actionable** — numbered procedures, decision branches, concrete commands.
3. **Discoverable** — pack trigger terms into `description` (the agent matches tasks to descriptions).
4. **Verbatim user copy** — if the user supplies exact wording for the skill, use it unchanged.
5. **No secrets** — never put API keys or credentials in skills; reference `.env` keys by name.
6. **Prefer update over duplicate** — extend an existing skill if scope overlaps.

Keep `SKILL.md` under ~500 lines; move long reference material to `references/`.

## Skills vs tools

| | Skill | Tool |
|---|-------|------|
| What | Instructions in `SKILL.md` | Python function the agent can call |
| Adds capability | Guides behavior | Enables new actions (API, search, etc.) |
| Where | `./skills/` or `~/.my-agent/skills/` | `src/my_agent/tools/` + wire in `agent.py` |

If the user needs a **new capability** (e.g. a new API), you must also add a tool in code — a skill alone cannot invent tools. If they only need a **repeatable workflow** with existing tools, a skill is enough.

## Workflow when asked to create a skill

1. Clarify scope if unclear: project vs user, skill name, triggers.
2. List existing skills in `./skills/` and `~/.my-agent/skills/`; update if one fits.
3. Pick a kebab-case name (nouns or verb-noun, e.g. `tavily-web-search`, `brew-maintenance`).
4. Write `SKILL.md` with frontmatter + body (use template above).
5. Add `references/` or `scripts/` only when they save tokens or reduce errors.
6. Tell the user the path and a one-line summary of what triggers it.

## Example request

**User:** "Make a skill for checking disk space on my Mac."

**Result:** `./skills/disk-diagnostics/SKILL.md` with `description` mentioning disk space, `df`, `du`, storage cleanup; body listing safe read-only commands and when to warn before deletes.

## Validation checklist

- [ ] Directory name equals `name` in frontmatter
- [ ] `description` has trigger keywords and is third-person
- [ ] Procedure is step-by-step with examples
- [ ] No secrets in the file
- [ ] Existing skill wasn't duplicated unnecessarily
