# Runbook — forms: publish a template, fill and review submissions, bound forms, agents, signed-in intake

Purpose: run forms day to day: publish a template, fill and submit it from the command line, the terminal, or the web,
review what came in, use a form that an inspection or a permit offers, let an agent propose a submission, and handle
intake items that signed-in people send in. Module: [forms](../../packages/tl-modules/forms/README.md). Design:
[ADR-0031](../adr/0031-forms-engine.md) (forms engine) and [ADR-0032](../adr/0032-public-intake-forms.md) (public intake).
Source of the access words: `schema/settings/access-words.yaml` (the `forms.*` rows).

## When to use
- A form (a toolbox talk, a pre-use check, a hazard assessment, a near-miss report) must be filled and kept as a numbered
  submission.
- A template must be drafted, published, revised or retired.
- A submission waits for review, or must be returned with a note or voided.
- An inspection or a permit offers a form, and its answers must go through the record's own command.
- Someone outside the team sends a request through a code, and an item is waiting for a controller.

## Before you start
- Sign in (`uv run tl login <name>`). Writes take the ledger from `--db` or `TL_DB`. Every command that reads or writes a
  submission takes `--project P200` (the project ID).
- Words (`schema/settings/access-words.yaml`): reading needs `forms.view`. Filling, saving drafts, discarding drafts and
  editing a Draft template need `user` (`forms.submit`, `forms.template.edit`). Publishing and retiring a template, reviewing
  (accept or return), voiding, and issuing or revoking an intake code need `controller` (`forms.template.publish`,
  `forms.review`, `forms.void`, `forms.intake.issue`). Reviewing an intake item needs `controller` (`forms.intake.review`).
- Who holds which word: an account with the platform role `user` holds the `user` word on every module. The `controller` word
  needs an explicit grant on the `forms` module:
  `uv run tl admin roles grant <username> --project P200 --module forms --role superuser --reason "<why>"`.
  Use the bare username (`mokafor`), not `user:mokafor`. The demo gives `mokafor` (the administrator) that grant.
- The person who filled a form may not review it, even with the controller word. Another controller reviews it.
- A form is a template key (`TPL-0001`) or a template that is Published. A draft has its own id (printed by `fill`).

## Publish a template
1. Write the template as a YAML or JSON file (title, `format_version: 2`, `answer_class`, `fields`, and the other keys the
   fixtures use). The fixtures are in `schema/fixtures/forms/templates/` (`toolbox-talk.yaml`, `pre-use-check.yaml`,
   `job-hazard-assessment.yaml`).
2. `uv run tl form publish schema/fixtures/forms/templates/toolbox-talk.yaml`
   prints `published TPL-0005 v1`. The file is drafted and then published in one step. Publish does not take `--project`:
   templates are company-wide.
3. Publish refuses a template whose questions break a rule. Each problem is listed after the error text. Fix the file and
   publish again.
4. A published template never changes. To change one, `ReviseFormTemplate` makes a Draft (version + 1); publish the Draft
   when it is ready. Only one open Draft per template is allowed.
5. Read them: `uv run tl form ls` (templates) and `uv run tl form show TPL-0001` (its questions). Add `--as jsonschema` or
   `--as surveyjs` to `show` to print the form in one of those formats.

## Fill and submit from the command line
1. Start a draft. Answers may be partial:
   ```
   uv run tl form fill TPL-0001 --project P200 --answer topic="Working at height" --answer talk_date=2026-11-06
   ```
   Prints `saved <draft id>`. Give each answer as `--answer q=value` (repeat it), or as `--answers-file answers.json`
   (a JSON list of `{"q", "value", "note"}`, or an object `{"q": value}`). A `multi` or `photo` question takes comma-separated
   values.
2. Carry on later: `uv run tl form fill TPL-0001 --resume --project P200 --answer led_by="Foreman"` continues your latest draft
   of the template. Name the draft to choose another: `uv run tl form fill TPL-0001 --resume <draft id> --project P200`.
   Or give the draft id as the target: `uv run tl form fill <draft id> --project P200 --answer ...`.
3. See your drafts: `uv run tl form drafts --project P200` (`form drafts: <n>`, then one line per draft).
4. Submit. The answers must be complete:
   ```
   uv run tl form submit TPL-0001 --project P200 --answers-file answers.json
   uv run tl form submit <draft id> --project P200 --answer attendees=7
   ```
   Prints `submitted P200-FRM-0013`. The number is taken now. A draft submitted from its id keeps the answers saved in it;
   `--answer` changes some of them.
5. A draft has no discard verb in the CLI or the terminal yet (`DiscardFormDraft` exists in the module but has no surface).
   A draft you no longer need stays in `tl form drafts` until it is submitted.
6. A `fill` that is saved as often as the module allows is refused with the module's words
   (`the draft was saved as often as it may be; submit it or discard it`). Submit it or discard it.

## Fill in the terminal
1. Start the terminal app with `just tui` (the project comes from `TL_PROJECT`, default `P123`; use `P200` for the demo).
2. Open the command palette and choose `forms`. The Forms log opens on the submissions (view `1`); view `2` shows the templates.
   Tab moves between the two; `/` filters; `F5` reloads; `Esc` goes back.
3. On a submission, Enter opens its details: each question in words with its answer, and the review text.
4. On a published template (view `2`), `f` or Enter opens the runner. The runner asks one question at a time:
   - Enter sends the answer to the step, and the next question shows.
   - An empty line skips an optional question. A required question must have an answer.
   - Up goes back one question. Esc cancels; nothing is written.
   - After the last question the review page shows every answer. Enter sends it. The status line shows what the server
     refused, in the same words `tl form` prints.
5. Your own draft in the log opens the runner with its saved answers in place (resume). A draft that is not yours is not in
   the log at all.

## Fill on the web
1. Sign in to the web client first (see [web-client.md](web-client.md)).
2. Open `/web/forms?project=P200`. It lists the published general templates and your own drafts.
3. Open a template with its link (`/web/forms/t/<template id>?project=P200`), fill it, then save a draft or submit it. A
   submitted form shows its number on the done page.
4. A record's card in the scan view opens `/web/forms/for/<key>?project=P200` when that record offers a form (see the
   bound forms section). The card's "Open record" link goes there.

## Review the submissions
1. Find what waits: `uv run tl form ls --submissions --project P200 --state Submitted`.
2. Read one: `uv run tl form show P200-FRM-0004 --submission --project P200`.
3. Decide:
   ```
   uv run tl form review P200-FRM-0004 accept --project P200
   uv run tl form review P200-FRM-0004 return --project P200 --note "Add the tag, resubmit."
   uv run tl form review P200-FRM-0004 void --project P200 --note "Wrong machine."
   ```
   Accept makes it Accepted. Return (the refusal that sends it back) needs a note. A returned submission keeps its number.
   Void needs the reason in `--note`.
4. Refusals: `error: forbidden` (you lack the controller word); `the person who filled a form may not review it`.
   A submission that is hidden from you is `error: no submission <key>`, the same text as a missing one.
5. Agent proposals of a submission wait in the proposal queue, not here. Accept or reject them with
   [proposal review queue](proposal-review-queue.md): `uv run tl proposal ls`, `uv run tl proposal accept <id>`,
   `uv run tl proposal reject <id>`. Accepting makes you the author, so the submitter rule holds for the next review.

## Bound forms (an inspection or a permit)
A bound form is the form an inspection or a permit offers for its own command. Its answers go through the record's typed
command in one unit of work. A refusal writes nothing.
1. See the form a record offers: `uv run tl form for P200-INS-0004 --project P200`. It prints the template, the typed
   command (`RecordInspectionResult` for an inspection) and the questions.
2. Fill it and send it through the record's command:
   ```
   uv run tl form record P200-INS-0004 --project P200 --answers-file answers.json
   ```
   The record's own access word decides, and the record's own rules apply (an inspection must be Scheduled before it is
   recorded, and so on).
3. A record that is hidden, absent, or has no form prints `error: no form for <key>`. The same text covers all three.

## Agents (MCP)
Five tools; agents only read and propose:

| Tool | Does |
|---|---|
| `list_form_templates` | the published templates (company-wide) |
| `get_form` | one template version, its questions |
| `list_form_submissions` | the submissions the agent may read (hidden ones are absent) |
| `get_form_submission` | one submission, when the agent may read it |
| `propose_form_submission` | files a pending proposal of `SubmitForm`; a person accepts it |

No agent tool saves a draft, submits, reviews, voids, publishes or issues a code. The routes of the module stay closed to
agents. An agent never reads a draft, because a draft belongs to its author.

## Signed-in intake (codes and the queue)
Intake lets a person outside the team send a form through a code. A code is made by the CLI and only its hash is sent to
the server. The code is printed once and cannot be shown again.

1. Issue a code for a Published public template (a template with `intake: public`):
   ```
   uv run tl intake code issue --project P200 --template <TPL key> --heading "Site visitor sign-on" --controller-role "site engineer" --expires-on 2026-12-31
   ```
   Prints `issued <id>  expires <date>` and the code. Keep the code; it is shown once. The expiry may be at most
   `forms.intake.code_max_days` days from today. The template must be Published and open to public intake.
2. List codes (no code and no hash is shown): `uv run tl intake code ls --project P200 --state Active` (states `Active`
   and `Revoked`).
3. Revoke a code that should open nothing: `uv run tl intake code revoke <id> --project P200 --reason "Visit cancelled"`.
   A revoked code opens nothing.
4. Read the queue, oldest first: `uv run tl intake ls --project P200 --state Pending` (`--code-id` narrows it to one code).
5. Open an item. A Pending item prints the sender's answers, one per line:
   `uv run tl intake show <item id> --project P200`.
6. Accept an item as the record the template proposes. The command runs as you, so you need its access word; a refusal leaves
   the item Pending:
   ```
   uv run tl intake accept <item id> --project P200 --as SubmitForm --args-file accept.json
   ```
   `accept.json` is a JSON object of that command's arguments; the template's `accepts_as` names the command.
7. Reject an item with one reason, `spam`, `duplicate`, `not_ours` or `unclear`:
   `uv run tl intake reject <item id> --project P200 --reason spam`. Its text stays until the purge.
8. Purge the text of items older than `forms.intake.retention_days`. Run it daily; a second run finds nothing:
   `uv run tl intake purge --project P200` prints `purged <n>`.
9. In the terminal, the palette entry `intake` opens the Intake log. Items come in as Pending; its state filter is `s`.
   A hidden item is not listed. An agent is refused.

The public link `/i/<code>` (a sender filling the form with no sign-in) is not built. It needs the owner's gate
(see Known limits).

## Reports
- `uv run tl report form-submissions --project P200` writes one row per submission the signed-in person may read (CSV;
  `--format jsonl` for JSON lines; `--out FILE` to write a file).
- `uv run tl report form-templates` writes the company templates.
- Hidden submissions are left out exactly as missing ones are.

## Verify
- `uv run tl form ls --submissions --project P200` lists the submissions with their states.
- `uv run tl report form-submissions --project P200` has one row per listed submission.
- After a review: `uv run tl form ls --submissions --project P200 --state Accepted` shows the accepted one.

## Known limits
- Hidden records leave key gaps. A number taken by a record a viewer may not read is a gap in the keys that viewer sees.
  This is accepted (ADR-0016, decision D41). A per-project option is later work (DEFERRED).
- The `/web/` routes take at most 64 KiB of body (the app's body cap, `tl_api.auth.BODY_LIMITS`). A longer form is refused
  there; split it or use the CLI or the terminal.
- The public intake link `/i/<code>` is not built. The owner has not approved it (the owner gate, DEFERRED). Intake is
  signed-in only until then.
- A privileged form (for example a near-miss report) is visible to its author only (decision D40). A controller who did not
  fill it does not see it, and `tl form ls` does not list it for them.
- A draft is read by its author alone, and an agent never reads one.

## Related
- [Package README](../../packages/tl-modules/forms/README.md), [ADR-0031](../adr/0031-forms-engine.md),
  [ADR-0032](../adr/0032-public-intake-forms.md).
- [Inspections](inspections.md) and [accounts and access](accounts-and-access.md) for the words and the grants.
- [Proposal review queue](proposal-review-queue.md) for agent proposals.
- [Web client](web-client.md) for signing in to `/web`.
