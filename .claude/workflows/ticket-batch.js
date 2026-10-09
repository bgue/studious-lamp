export const meta = {
  name: 'ticket-batch',
  description: 'Implement a batch of Throughline tickets with implementer agents, review each in a fresh reviewer, retry once on changes requested',
  whenToUse: 'Orchestrator relay step: run a supervisor DISPATCH list of ready tickets through implement -> review -> (retry -> re-review).',
  phases: [
    { title: 'Implement', detail: 'one implementer per ticket in its own git worktree' },
    { title: 'Review', detail: 'fresh reviewer per ticket, detached worktree' },
    { title: 'Retry', detail: 'second implementer attempt with reviewer findings' },
    { title: 'Re-review', detail: 'final review; a second changes-requested hands the ticket to the supervisor' },
  ],
}

// args: { repo, wtRoot, inc, base, trailer, tickets: [{ id, path, branch }] }
const A = args
const REPO = A.repo
const WT = A.wtRoot

const IMPL_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    branch: { type: 'string' },
    commit: { type: 'string' },
    report_path: { type: 'string' },
    summary: { type: 'string' },
    blocked_reason: { type: 'string' },
  },
  required: ['status', 'branch', 'summary'],
}
const REV_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['pass', 'changes-requested', 'escalate'] },
    findings: { type: 'array', items: { type: 'string' } },
    checks_run: { type: 'string' },
  },
  required: ['verdict', 'findings', 'checks_run'],
}

function slug(id) { return id.toLowerCase() }

function implPrompt(t, attempt, findings) {
  const wt = `${WT}/${slug(t.id)}`
  const setup = attempt === 1
    ? `cd ${REPO} && (test -d ${wt} || git worktree add ${wt} -b ${t.branch} ${A.base})`
    : `cd ${REPO} && (test -d ${wt} || git worktree add ${wt} ${t.branch})`
  const fix = attempt === 1 ? '' :
    `\n\nTHIS IS ATTEMPT 2. A reviewer requested changes on your branch. Fix exactly these findings, nothing else:\n` +
    findings.map((f, i) => `${i + 1}. ${f}`).join('\n') +
    `\nAdd a new commit; do not amend or rewrite history.`
  return `You are the implementer for ticket ${t.id} (increment ${A.inc}).

Worktree setup (run first; it creates or reuses your worktree on branch ${t.branch}, based on ${A.base}):
  ${setup}
Your worktree is ${wt}. Every Bash command must start with \`cd ${wt} && \`. Use absolute paths under ${wt} for Read/Edit/Write.
If ${wt}/pyproject.toml exists, run \`cd ${wt} && uv sync --all-packages\` before any test (fall back to \`uv sync\`).

Read ${wt}/AGENTS.md, then the ticket at ${wt}/${t.path}, then only the files its Context section lists (under ${wt}).
Your branch is ${t.branch}; if the ticket's Branch field says something else, ${t.branch} supersedes it (convention fix, LEARNINGS L-P0-SETUP-10) and that is not a deviation.
Do exactly what the ticket says inside its Allowed paths. Run every Acceptance command and keep the decisive output lines.

Commit on ${t.branch} with message "${t.id}: <imperative summary>" and a body, ending with these exact lines:
${A.trailer}
Write your report (template docs/templates/haiku-report.md) to ${wt}/docs/reports/${A.inc}/${t.id}.md and include it in a commit.
Do not push, do not merge, do not remove the worktree, do not touch other branches.
If blocked, write the question under Blocked in the report, commit what you have, and return status "blocked".${fix}

Return: status, branch (${t.branch}), commit (final sha), report_path (repo-relative), summary (<= 3 sentences), blocked_reason if blocked.`
}

function reviewPrompt(t, attempt) {
  const rwt = `${WT}/review-${slug(t.id)}-${attempt}`
  return `You are the reviewer for ticket ${t.id} (increment ${A.inc}). You have not seen the author's work before.

Setup: cd ${REPO} && git worktree remove --force ${rwt} 2>/dev/null; git worktree add --detach ${rwt} ${t.branch}
Every Bash command must start with \`cd ${rwt} && \`. Do not modify any tracked file and do not commit.
Read ${rwt}/AGENTS.md, the ticket at ${rwt}/${t.path}, the diff \`git diff ${A.base}...${t.branch}\`, and docs/build-spec/02-task-protocol.md section 6 (review checklist).
If pyproject.toml exists run \`uv sync --all-packages\` (fall back to \`uv sync\`), then re-run \`just check\` and every test command in the ticket's Acceptance section yourself. Do not trust pasted output.
Walk the checklist in order. Verdict: "pass", "changes-requested" (each finding cites file:line and the ticket line or AGENTS.md rule it violates, and says concretely what to change), or "escalate" (the diff raises a question the ticket cannot answer).
Finally: cd ${REPO} && git worktree remove --force ${rwt}

Return: verdict, findings (empty if pass), checks_run (commands you ran and pass/fail for each).`
}

const results = await pipeline(
  A.tickets,
  (t) => agent(implPrompt(t, 1, []), { label: `impl ${t.id}`, phase: 'Implement', agentType: 'implementer', schema: IMPL_SCHEMA }),
  async (impl, t) => {
    if (!impl || impl.status !== 'done') return { id: t.id, outcome: 'blocked', attempts: 1, impl, reviews: [] }
    const r1 = await agent(reviewPrompt(t, 1), { label: `review ${t.id}`, phase: 'Review', agentType: 'reviewer', schema: REV_SCHEMA })
    if (!r1) return { id: t.id, outcome: 'review-failed', attempts: 1, impl, reviews: [] }
    if (r1.verdict !== 'changes-requested') return { id: t.id, outcome: r1.verdict, attempts: 1, impl, reviews: [r1] }
    const impl2 = await agent(implPrompt(t, 2, r1.findings), { label: `retry ${t.id}`, phase: 'Retry', agentType: 'implementer', schema: IMPL_SCHEMA })
    if (!impl2 || impl2.status !== 'done') return { id: t.id, outcome: 'blocked', attempts: 2, impl: impl2, reviews: [r1] }
    const r2 = await agent(reviewPrompt(t, 2), { label: `re-review ${t.id}`, phase: 'Re-review', agentType: 'reviewer', schema: REV_SCHEMA })
    const outcome = !r2 ? 'review-failed' : (r2.verdict === 'changes-requested' ? 'two-strikes' : r2.verdict)
    return { id: t.id, outcome, attempts: 2, impl: impl2, reviews: [r1, r2].filter(Boolean) }
  },
)

const out = results.map((r, i) => r || { id: A.tickets[i].id, outcome: 'agent-died', attempts: 0, reviews: [] })
log(out.map(r => `${r.id}: ${r.outcome}`).join(' | '))
return out
