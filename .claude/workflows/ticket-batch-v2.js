export const meta = {
  name: 'ticket-batch-v2',
  description: 'Implement Throughline tickets and builder pieces: implement, gate, review (lite or full), one retry',
  whenToUse: 'Orchestrator relay step (process v2): run a supervisor DISPATCH list of tickets and piece specs through implement -> gate -> review -> (retry -> gate -> re-review). Replaces ticket-batch.js.',
  phases: [
    { title: 'Implement', detail: 'one implementer (ticket) or builder (piece) per item in its own git worktree' },
    { title: 'Gate', detail: 'gate-runner runs the test gate on the branch; a red gate goes back to the author once before any reviewer' },
    { title: 'Review', detail: 'fresh reviewer per item: reviewer-lite for `review: lite` tickets, reviewer otherwise; reads the gate summary, re-runs nothing' },
    { title: 'Retry', detail: 'second attempt with the findings, then gate and re-review; a second changes-requested is two-strikes' },
  ],
}

// args: { repo, wtRoot, inc, base, trailer, gate, items: [{ id, path, branch, kind: 'ticket'|'piece', review: 'lite'|'full', tests: [paths], pg: bool }] }
// gate: optional override of the gate command; default per item: `just check && just gate[-pg] <item.tests> | tee .gate/summary.txt`.
const A = args
const REPO = A.repo
const WT = A.wtRoot
function gateCmd(t) {
  if (A.gate) return A.gate
  const recipe = t.pg ? 'just gate-pg' : 'just gate'
  return `just check && ${recipe} ${(t.tests || []).join(' ')} | tee .gate/summary.txt`
}

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
const GATE_SCHEMA = {
  type: 'object',
  properties: {
    green: { type: 'boolean' },
    summary: { type: 'string' },
    failing: { type: 'array', items: { type: 'string' } },
  },
  required: ['green', 'summary', 'failing'],
}
const REV_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['pass', 'changes-requested', 'escalate'] },
    findings: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'findings'],
}

function slug(id) { return id.toLowerCase() }
function wtOf(t) { return `${WT}/${slug(t.id)}` }
function isPiece(t) { return t.kind === 'piece' }

function implPrompt(t, attempt, findings, gateSummary) {
  const wt = wtOf(t)
  const role = isPiece(t) ? 'builder' : 'implementer'
  const what = isPiece(t) ? 'piece spec' : 'ticket'
  const setup = attempt === 1
    ? `cd ${REPO} && (test -d ${wt} || git worktree add ${wt} -b ${t.branch} ${A.base})`
    : `cd ${REPO} && (test -d ${wt} || git worktree add ${wt} ${t.branch})`
  let fix = ''
  if (findings && findings.length) {
    fix = `\n\nTHIS IS A SECOND ATTEMPT. A reviewer requested changes on your branch. Fix exactly these findings, nothing else:\n` +
      findings.map((f, i) => `${i + 1}. ${f}`).join('\n') + `\nAdd a new commit; do not amend or rewrite history.`
  } else if (gateSummary) {
    fix = `\n\nTHIS IS A GATE FIX. The test gate on your branch is red. Make it green, changing nothing outside the ${what}'s Allowed paths; never skip or weaken a test. Gate summary:\n${gateSummary}\nAdd a new commit; do not amend or rewrite history.`
  }
  return `You are the ${role} for ${t.id} (increment ${A.inc}).

Worktree setup (run first; it creates or reuses your worktree on branch ${t.branch}, based on ${A.base}):
  ${setup}
Your worktree is ${wt}. Every Bash command must start with \`cd ${wt} && \`. Use absolute paths under ${wt} for Read/Edit/Write.
If ${wt}/pyproject.toml exists, run \`cd ${wt} && uv sync --all-packages\` before any test (fall back to \`uv sync\`).

Read ${wt}/AGENTS.md, then the ${what} at ${wt}/${t.path}, then only the files its Context section lists (under ${wt}).
Your branch is ${t.branch}; if the ${what}'s Branch field says something else, ${t.branch} supersedes it and that is not a deviation.
Do exactly what the ${what} says inside its Allowed paths. Run every Acceptance command once and keep at most 5 decisive output lines per command. Do not poll logs and do not run the whole suite.

Commit on ${t.branch} with message "${t.id}: <imperative summary>" and a body, ending with the attribution trailer your
harness requires (a Co-Authored-By line naming your own model, then this session line):
${A.trailer}
Write your report (template docs/templates/haiku-report.md, at most 60 lines) to ${wt}/docs/reports/${A.inc}/${t.id}.md and include it in a commit.
Do not push, do not merge, do not remove the worktree, do not touch other branches.
If blocked, write the question under Blocked in the report, commit what you have, and return status "blocked".${fix}

Return: status, branch (${t.branch}), commit (final sha), report_path (repo-relative), summary (<= 3 sentences), blocked_reason if blocked.`
}

function gatePrompt(t) {
  const wt = wtOf(t)
  return `Run the test gate for ${t.id} on branch ${t.branch}.
Worktree: ${wt} (it exists; do not create or remove worktrees). Every Bash command must start with \`cd ${wt} && \`.
If ${wt}/pyproject.toml exists run \`uv sync --all-packages\` once (fall back to \`uv sync\`), then run exactly once, in the foreground with a 10-minute timeout per part:
  ${gateCmd(t)}
Do not edit, commit, re-run or poll. Return green (just check exit 0 and the last summary line is `gate: PASS`), summary (the just check exit code, then \`.gate/summary.txt\` verbatim), failing.`
}

function reviewPrompt(t, attempt, gate) {
  const wt = wtOf(t)
  const lite = !isPiece(t) && t.review === 'lite'
  return `You are the reviewer for ${t.id} (increment ${A.inc}), review ${attempt}. You have not seen the author's work before.

Read-only worktree: ${wt} on branch ${t.branch}. Every Bash command must start with \`cd ${wt} && \`. Do not modify any file, do not commit, do not run uv sync, do not run the test suite.
Read ${wt}/AGENTS.md, the ${isPiece(t) ? 'piece spec' : 'ticket'} at ${wt}/${t.path}, the diff \`git diff ${A.base}...${t.branch}\`${lite ? '' : ', and docs/build-spec/02-task-protocol.md section 6 (review checklist)'}.
The test gate already ran on this branch by an agent independent of the author. Its result (green=${gate.green}):
${gate.summary}
Trust this summary for verification; if it does not cover a package the diff touches, say so as a finding instead of running it.
The author's report at docs/reports/${A.inc}/${t.id}.md is required by the workflow and always inside the boundary; never raise it as a finding. A ticket Branch field that differs from ${t.branch} is not a finding.
Verdict: "pass", "changes-requested" (each finding cites file:line and the ticket line or AGENTS.md rule it violates, and says concretely what to change), or "escalate" (the diff raises a question the ticket cannot answer, or a lite ticket needs a full review).

Return: verdict, findings (empty if pass).`
}

function reviewerType(t) { return (!isPiece(t) && t.review === 'lite') ? 'reviewer-lite' : 'reviewer' }

async function runGate(t, label) {
  const g = await agent(gatePrompt(t), { label, phase: 'Gate', agentType: 'gate-runner', schema: GATE_SCHEMA, effort: 'low' })
  return g || { green: false, summary: 'gate-runner died', failing: ['agent-died'] }
}

const results = await pipeline(
  A.items,
  (t) => agent(implPrompt(t, 1, [], null), {
    label: `${isPiece(t) ? 'build' : 'impl'} ${t.id}`, phase: 'Implement',
    agentType: isPiece(t) ? 'builder' : 'implementer', schema: IMPL_SCHEMA,
  }),
  async (impl, t) => {
    if (!impl || impl.status !== 'done') return { id: t.id, outcome: 'blocked', attempts: 1, impl, gate: null, reviews: [] }

    // Gate 1; one gate-fix attempt by the author before any reviewer is spent.
    let gate = await runGate(t, `gate ${t.id}`)
    let attempts = 1
    if (!gate.green) {
      if (gate.failing.includes('env')) return { id: t.id, outcome: 'gate-env', attempts, impl, gate, reviews: [] }
      const fix = await agent(implPrompt(t, 2, [], gate.summary), {
        label: `gate-fix ${t.id}`, phase: 'Retry', agentType: isPiece(t) ? 'builder' : 'implementer', schema: IMPL_SCHEMA,
      })
      attempts = 2
      if (!fix || fix.status !== 'done') return { id: t.id, outcome: 'blocked', attempts, impl: fix, gate, reviews: [] }
      impl = fix
      gate = await runGate(t, `re-gate ${t.id}`)
      if (!gate.green) return { id: t.id, outcome: 'gate-red', attempts, impl, gate, reviews: [] }
    }

    const r1 = await agent(reviewPrompt(t, 1, gate), { label: `review ${t.id}`, phase: 'Review', agentType: reviewerType(t), schema: REV_SCHEMA })
    if (!r1) return { id: t.id, outcome: 'review-failed', attempts, impl, gate, reviews: [] }
    if (r1.verdict !== 'changes-requested') return { id: t.id, outcome: r1.verdict, attempts, impl, gate, reviews: [r1] }
    if (attempts >= 2) return { id: t.id, outcome: 'two-strikes', attempts, impl, gate, reviews: [r1] }

    const impl2 = await agent(implPrompt(t, 2, r1.findings, null), {
      label: `retry ${t.id}`, phase: 'Retry', agentType: isPiece(t) ? 'builder' : 'implementer', schema: IMPL_SCHEMA,
    })
    if (!impl2 || impl2.status !== 'done') return { id: t.id, outcome: 'blocked', attempts: 2, impl: impl2, gate, reviews: [r1] }
    const gate2 = await runGate(t, `re-gate ${t.id}`)
    if (!gate2.green) return { id: t.id, outcome: 'gate-red', attempts: 2, impl: impl2, gate: gate2, reviews: [r1] }
    const r2 = await agent(reviewPrompt(t, 2, gate2), { label: `re-review ${t.id}`, phase: 'Review', agentType: reviewerType(t), schema: REV_SCHEMA })
    const outcome = !r2 ? 'review-failed' : (r2.verdict === 'changes-requested' ? 'two-strikes' : r2.verdict)
    return { id: t.id, outcome, attempts: 2, impl: impl2, gate: gate2, reviews: [r1, r2].filter(Boolean) }
  },
)

// Outcomes: pass | escalate | two-strikes | gate-red | gate-env | blocked | review-failed | agent-died
// (changes-requested is never returned: it becomes the retry).
const TL92 = { pass: 'P', escalate: 'esc', 'two-strikes': '2s', 'gate-red': 'gr', 'gate-env': 'ge', blocked: 'blk', 'review-failed': 'rvF', 'agent-died': 'died' }
const out = results.map((r, i) => r || { id: A.items[i].id, outcome: 'agent-died', attempts: 0, gate: null, reviews: [] })
// One TL92 line per item (skill "TL92"): <id> <outcome>@<sha7> g<0|1|-> <l|f|p> <attempts> [F1 F2 ...]
function tl92(r, t) {
  const sha = r.impl && r.impl.commit ? '@' + String(r.impl.commit).slice(0, 7) : ''
  const g = r.gate ? (r.gate.green ? 'g0' : 'g1') : 'g-'
  const tier = isPiece(t) ? 'p' : (t.review === 'lite' ? 'l' : 'f')
  const fs = (r.reviews || []).flatMap(x => x.findings || []).map((_, i) => `F${i + 1}`).join(' ')
  return `${r.id} ${TL92[r.outcome] || r.outcome}${sha} ${g} ${tier} ${r.attempts}${fs ? ' ' + fs : ''}`
}
const lines = out.map((r, i) => tl92(r, A.items[i]))
log(lines.join(' | ') + ' | 30')
// The orchestrator relays `tl92` lines to the next supervisor round (<= 20 lines) and keeps `findings` for the author.
return out.map((r, i) => ({
  id: r.id, outcome: r.outcome, attempts: r.attempts, tl92: lines[i],
  commit: r.impl && r.impl.commit, report_path: r.impl && r.impl.report_path,
  gate_summary: r.gate && r.gate.summary,
  findings: (r.reviews || []).flatMap(x => x.findings || []),
}))
