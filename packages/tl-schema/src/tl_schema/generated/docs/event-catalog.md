# Throughline event catalog

Every ledger event type that can reach a webhook subscriber, generated from the LinkML event classes. Each event arrives as a CloudEvents 1.0 JSON message signed with Standard Webhooks headers; the payload modes are `thin`, `delta` and `full`. Receivers dedupe on the event `id`. A request sent by `tl webhook test` carries the extra header `webhook-test: 1`; real deliveries never do.

## Event types

| Event type | CloudEvents type | Summary |
|---|---|---|
| [`Account.Created`](#accountcreated) | `tl.core.Account.Created.v1` | An account was created. |
| [`Account.Disabled`](#accountdisabled) | `tl.core.Account.Disabled.v1` | An account was disabled: it cannot sign in and its sessions and agent tokens stop working. |
| [`Account.Enabled`](#accountenabled) | `tl.core.Account.Enabled.v1` | A disabled account was enabled again. |
| [`Account.PasswordChanged`](#accountpasswordchanged) | `tl.core.Account.PasswordChanged.v1` | The password of an account was set or changed. |
| [`Account.RolesSet`](#accountrolesset) | `tl.core.Account.RolesSet.v1` | The roles of an account were replaced. |
| [`Action.Completed`](#actioncompleted) | `tl.core.Action.Completed.v1` | The executor finished the action. |
| [`Action.Failed`](#actionfailed) | `tl.core.Action.Failed.v1` | The action failed for good (not retried any more). |
| [`Action.Requested`](#actionrequested) | `tl.core.Action.Requested.v1` | An action was requested on records. |
| [`Action.Running`](#actionrunning) | `tl.core.Action.Running.v1` | A worker started an attempt. |
| [`ActionDefinition.Defined`](#actiondefinitiondefined) | `tl.core.ActionDefinition.Defined.v1` | An action was defined (version 1). |
| [`ActionDefinition.Retired`](#actiondefinitionretired) | `tl.core.ActionDefinition.Retired.v1` | An action was retired: it can no longer be invoked; its invocations stay readable. |
| [`ActionDefinition.Revised`](#actiondefinitionrevised) | `tl.core.ActionDefinition.Revised.v1` | An action was revised; the event carries the whole new definition and the row is replaced. |
| [`ActionDefinition.SecretRotated`](#actiondefinitionsecretrotated) | `tl.core.ActionDefinition.SecretRotated.v1` | A new signing secret was issued for a webhook action; the previous one keeps verifying until the overlap ends. |
| [`ActivityRef.Defined`](#activityrefdefined) | `tl.core.ActivityRef.Defined.v1` | The first link to an activity made its reference. |
| [`ActivityRef.PresenceChanged`](#activityrefpresencechanged) | `tl.core.ActivityRef.PresenceChanged.v1` | A publication found the activity gone from the schedule (present false) or back (present true). |
| [`Adoption.Pinned`](#adoptionpinned) | `tl.core.Adoption.Pinned.v1` | A project pinned a version of a company package. |
| [`AgentToken.Issued`](#agenttokenissued) | `tl.core.AgentToken.Issued.v1` | An agent token was issued. |
| [`AgentToken.Revoked`](#agenttokenrevoked) | `tl.core.AgentToken.Revoked.v1` | An agent token was revoked and no longer authenticates. |
| [`CodeValue.Closed`](#codevalueclosed) | `tl.core.CodeValue.Closed.v1` | A code value was superseded by another or retired; it still resolves for old records. |
| [`CodeValue.Defined`](#codevaluedefined) | `tl.core.CodeValue.Defined.v1` | A value was added to a code list. |
| [`Commercial.Assessed`](#commercialassessed) | `tl.core.Commercial.Assessed.v1` | The other party assessed an issued Commercial item: agreed, disputed or partially agreed, with the value they assessed. |
| [`Commercial.Defined`](#commercialdefined) | `tl.core.Commercial.Defined.v1` | A Commercial item (early warning, change notice, claim ...) was raised. |
| [`Commercial.Updated`](#commercialupdated) | `tl.core.Commercial.Updated.v1` | The domain fields of a Commercial item that is not yet issued changed. |
| [`ContractClause.Defined`](#contractclausedefined) | `tl.core.ContractClause.Defined.v1` | A contract clause was entered. |
| [`ContractClause.Retired`](#contractclauseretired) | `tl.core.ContractClause.Retired.v1` | A clause was retired; clocks that cited it keep their reference. |
| [`Correspondence.ClearanceGranted`](#correspondenceclearancegranted) | `tl.core.Correspondence.ClearanceGranted.v1` | An account was named as able to read a privileged item (ADR-0016). |
| [`Correspondence.ClearanceWithdrawn`](#correspondenceclearancewithdrawn) | `tl.core.Correspondence.ClearanceWithdrawn.v1` | An account was removed from the readers of a privileged item. |
| [`Correspondence.ConfidentialityChanged`](#correspondenceconfidentialitychanged) | `tl.core.Correspondence.ConfidentialityChanged.v1` | The confidentiality class of an item changed (a controller's act, ADR-0016). |
| [`Correspondence.Defined`](#correspondencedefined) | `tl.core.Correspondence.Defined.v1` | A correspondence item was received, drafted or logged. |
| [`Correspondence.Issued`](#correspondenceissued) | `tl.core.Correspondence.Issued.v1` | An outgoing item was issued: its text was rendered to a PDF (stored in the slot `rendition`) and sent. |
| [`Correspondence.Reclassified`](#correspondencereclassified) | `tl.core.Correspondence.Reclassified.v1` | The domain or subtype of an item changed before it was issued. |
| [`Correspondence.Responded`](#correspondenceresponded) | `tl.core.Correspondence.Responded.v1` | An answer to an item was issued or received. |
| [`Correspondence.Superseded`](#correspondencesuperseded) | `tl.core.Correspondence.Superseded.v1` | An item was replaced by another item; it stays in the ledger. |
| [`Correspondence.ThreadAssigned`](#correspondencethreadassigned) | `tl.core.Correspondence.ThreadAssigned.v1` | An item joined a thread, and optionally answers another item. |
| [`Correspondence.Triaged`](#correspondencetriaged) | `tl.core.Correspondence.Triaged.v1` | A person confirmed the domain and subtype of a received item, with the records it refers to and the clocks that were started. |
| [`Correspondence.Updated`](#correspondenceupdated) | `tl.core.Correspondence.Updated.v1` | The register fields of a draft or received item changed (the subject changes through the core `Record.Updated`). |
| [`CorrespondenceThread.Defined`](#correspondencethreaddefined) | `tl.core.CorrespondenceThread.Defined.v1` | A thread was opened by its first item. |
| [`CorrespondenceThread.ItemAdded`](#correspondencethreaditemadded) | `tl.core.CorrespondenceThread.ItemAdded.v1` | An item joined the thread. |
| [`CorrespondenceThread.StateChanged`](#correspondencethreadstatechanged) | `tl.core.CorrespondenceThread.StateChanged.v1` | A thread was closed or reopened. |
| [`CostCode.Defined`](#costcodedefined) | `tl.core.CostCode.Defined.v1` | A cost code was registered (by the first snapshot that names it). |
| [`CostCode.MeasuresRecorded`](#costcodemeasuresrecorded) | `tl.core.CostCode.MeasuresRecorded.v1` | A snapshot stated the figures of a cost code. |
| [`CostCode.Revised`](#costcoderevised) | `tl.core.CostCode.Revised.v1` | A snapshot changed the description, parent or unit of measure of an existing cost code. |
| [`CostSnapshot.Defined`](#costsnapshotdefined) | `tl.core.CostSnapshot.Defined.v1` | A period of figures was imported. |
| [`DerivedDocument.ContentRecorded`](#deriveddocumentcontentrecorded) | `tl.core.DerivedDocument.ContentRecorded.v1` | One extractor pass over a source file finished: a new content revision of the derived document. |
| [`DerivedDocument.Defined`](#deriveddocumentdefined) | `tl.core.DerivedDocument.Defined.v1` | A derived document was opened for a source revision and a document schema. |
| [`DerivedDocument.PublicationCompensated`](#deriveddocumentpublicationcompensated) | `tl.core.DerivedDocument.PublicationCompensated.v1` | The publication of a derived document was rolled back: reversing events for everything its import made were appended under a correlation id of their own. |
| [`DerivedDocument.Published`](#deriveddocumentpublished) | `tl.core.DerivedDocument.Published.v1` | The rows of a valid content revision were published into target records as one correlated import. |
| [`DerivedDocument.Validated`](#deriveddocumentvalidated) | `tl.core.DerivedDocument.Validated.v1` | A content revision was checked against a document schema version. |
| [`Document.CurrentRevisionChanged`](#documentcurrentrevisionchanged) | `tl.core.Document.CurrentRevisionChanged.v1` | The revision in force for a document changed (an issue, a supersession or a void). |
| [`Document.Defined`](#documentdefined) | `tl.core.Document.Defined.v1` | A document was registered under its number. |
| [`Document.Superseded`](#documentsuperseded) | `tl.core.Document.Superseded.v1` | A document was replaced by another document; it stays in the ledger and its links go stale. |
| [`Document.Updated`](#documentupdated) | `tl.core.Document.Updated.v1` | The register fields of a document changed (the title changes through the core `Record.Updated`). |
| [`DocumentSchema.Defined`](#documentschemadefined) | `tl.core.DocumentSchema.Defined.v1` | A version of a document schema was registered. |
| [`DocumentSchema.Retired`](#documentschemaretired) | `tl.core.DocumentSchema.Retired.v1` | A version of a document schema was retired; documents that named it keep it. |
| [`Enricher.Disabled`](#enricherdisabled) | `tl.core.Enricher.Disabled.v1` | An enricher was switched off. |
| [`Enricher.Enabled`](#enricherenabled) | `tl.core.Enricher.Enabled.v1` | An enricher was switched on. |
| [`Enricher.Registered`](#enricherregistered) | `tl.core.Enricher.Registered.v1` | An enricher was registered. |
| [`Enricher.Revised`](#enricherrevised) | `tl.core.Enricher.Revised.v1` | An enricher's registration changed; the event carries the whole new registration. |
| [`Enrichment.Accepted`](#enrichmentaccepted) | `tl.core.Enrichment.Accepted.v1` | A person (or the enricher's own auto policy) accepted a value: it is now written to the enricher's layer of the record. |
| [`Enrichment.Proposed`](#enrichmentproposed) | `tl.core.Enrichment.Proposed.v1` | An enricher proposed a value for a property of its own layer of a record. |
| [`Enrichment.Rejected`](#enrichmentrejected) | `tl.core.Enrichment.Rejected.v1` | A value was rejected by a person, or replaced by a newer proposal. |
| [`Feed.Edited`](#feededited) | `tl.core.Feed.Edited.v1` | A post was edited. |
| [`Feed.Posted`](#feedposted) | `tl.core.Feed.Posted.v1` | A post was made in a project feed. |
| [`Feed.Reacted`](#feedreacted) | `tl.core.Feed.Reacted.v1` | A reaction was set or cleared on a post. |
| [`Feed.Retracted`](#feedretracted) | `tl.core.Feed.Retracted.v1` | A post was retracted. |
| [`File.Processed`](#fileprocessed) | `tl.core.File.Processed.v1` | A file passed its scan and is available. |
| [`File.Rejected`](#filerejected) | `tl.core.File.Rejected.v1` | A file failed its scan and was rejected. |
| [`File.Uploaded`](#fileuploaded) | `tl.core.File.Uploaded.v1` | A file was uploaded and attached to a record; it is quarantined until its scan finishes. |
| [`Inbound.Applied`](#inboundapplied) | `tl.core.Inbound.Applied.v1` | A delivery was mapped and its commands ran (or, for a dry-run endpoint, were planned). |
| [`Inbound.Failed`](#inboundfailed) | `tl.core.Inbound.Failed.v1` | A delivery could not be applied; it is in the error queue until an admin retries it. |
| [`Inbound.Received`](#inboundreceived) | `tl.core.Inbound.Received.v1` | A signed POST was accepted and queued for mapping. |
| [`Inbound.Retried`](#inboundretried) | `tl.core.Inbound.Retried.v1` | An admin re-ran a failed delivery, optionally with a corrected payload. |
| [`InboundEndpoint.Created`](#inboundendpointcreated) | `tl.core.InboundEndpoint.Created.v1` | An inbound endpoint was created. |
| [`InboundEndpoint.Disabled`](#inboundendpointdisabled) | `tl.core.InboundEndpoint.Disabled.v1` | An endpoint stopped accepting deliveries; it answers 404. |
| [`InboundEndpoint.Enabled`](#inboundendpointenabled) | `tl.core.InboundEndpoint.Enabled.v1` | An endpoint started accepting deliveries. |
| [`InboundEndpoint.Revised`](#inboundendpointrevised) | `tl.core.InboundEndpoint.Revised.v1` | An endpoint was revised; the event carries the whole new definition (no secret). |
| [`InboundEndpoint.SecretRotated`](#inboundendpointsecretrotated) | `tl.core.InboundEndpoint.SecretRotated.v1` | A new secret was issued; the previous one keeps verifying until the overlap ends (at most 24 hours). |
| [`IntegrationApp.Disabled`](#integrationappdisabled) | `tl.core.IntegrationApp.Disabled.v1` | An app was switched off: its endpoints answer 404 and its rules, actions and enrichers do nothing. |
| [`IntegrationApp.Enabled`](#integrationappenabled) | `tl.core.IntegrationApp.Enabled.v1` | An app was switched on: its endpoints, rules, actions and enrichers run again. |
| [`IntegrationApp.Registered`](#integrationappregistered) | `tl.core.IntegrationApp.Registered.v1` | An integration app was registered. |
| [`IntegrationApp.Revised`](#integrationapprevised) | `tl.core.IntegrationApp.Revised.v1` | An app's label, description or owner changed. |
| [`Link.Accepted`](#linkaccepted) | `tl.core.Link.Accepted.v1` | A suggested link was accepted and is now active. |
| [`Link.Added`](#linkadded) | `tl.core.Link.Added.v1` | A link between two records became active. |
| [`Link.Declined`](#linkdeclined) | `tl.core.Link.Declined.v1` | A suggested link was declined; it will not be suggested again. |
| [`Link.Flagged`](#linkflagged) | `tl.core.Link.Flagged.v1` | A link was flagged stale or broken. |
| [`Link.Repinned`](#linkrepinned) | `tl.core.Link.Repinned.v1` | The pin of a link was set to another revision. |
| [`Link.Retracted`](#linkretracted) | `tl.core.Link.Retracted.v1` | A link was retracted. |
| [`Link.Suggested`](#linksuggested) | `tl.core.Link.Suggested.v1` | A link was suggested and waits for a person to accept or decline. |
| [`Link.Verified`](#linkverified) | `tl.core.Link.Verified.v1` | A person verified an active link. |
| [`LoadRun.Bronzed`](#loadrunbronzed) | `tl.core.LoadRun.Bronzed.v1` | The rows were copied, as they are, to the lake bronze table of the system and table. |
| [`LoadRun.Compensated`](#loadruncompensated) | `tl.core.LoadRun.Compensated.v1` | The records the load created were taken back, by the ids the load recorded. |
| [`LoadRun.Extracted`](#loadrunextracted) | `tl.core.LoadRun.Extracted.v1` | The rows of the file were read in the resource envelope and stored. |
| [`LoadRun.Failed`](#loadrunfailed) | `tl.core.LoadRun.Failed.v1` | A stage failed; the run stays in its state and says why (fixed text, no value of the file). |
| [`LoadRun.Loaded`](#loadrunloaded) | `tl.core.LoadRun.Loaded.v1` | The load wrote records through the module commands, as one correlated batch. |
| [`LoadRun.Opened`](#loadrunopened) | `tl.core.LoadRun.Opened.v1` | A load run was opened for a file. |
| [`LoadRun.Planned`](#loadrunplanned) | `tl.core.LoadRun.Planned.v1` | The rows were mapped and a dry run counted what a load would do. |
| [`LoadRun.Profiled`](#loadrunprofiled) | `tl.core.LoadRun.Profiled.v1` | The rows were profiled: columns, value shapes, keys and repeats. |
| [`LoadRun.Reconciled`](#loadrunreconciled) | `tl.core.LoadRun.Reconciled.v1` | The load was compared with the file; the report is stored and registered as a document. |
| [`LoadRun.Voided`](#loadrunvoided) | `tl.core.LoadRun.Voided.v1` | The run was abandoned before it loaded anything. |
| [`Numbering.Allocated`](#numberingallocated) | `tl.core.Numbering.Allocated.v1` | A number was allocated from a counter. |
| [`Party.ContactAdded`](#partycontactadded) | `tl.core.Party.ContactAdded.v1` | A contact was added to a party. |
| [`Party.ContactEnded`](#partycontactended) | `tl.core.Party.ContactEnded.v1` | A contact was ended. |
| [`Party.Defined`](#partydefined) | `tl.core.Party.Defined.v1` | A party was entered, with its first contacts. |
| [`Party.Retired`](#partyretired) | `tl.core.Party.Retired.v1` | A party was retired. |
| [`ProcessingJob.Cancelled`](#processingjobcancelled) | `tl.core.ProcessingJob.Cancelled.v1` | A queued job was cancelled before a worker took it. |
| [`ProcessingJob.Defined`](#processingjobdefined) | `tl.core.ProcessingJob.Defined.v1` | A processing job was queued. |
| [`ProcessingJob.Failed`](#processingjobfailed) | `tl.core.ProcessingJob.Failed.v1` | The claimed attempt failed. |
| [`ProcessingJob.Started`](#processingjobstarted) | `tl.core.ProcessingJob.Started.v1` | A worker claimed a job (attempt n). |
| [`ProcessingJob.Succeeded`](#processingjobsucceeded) | `tl.core.ProcessingJob.Succeeded.v1` | The claimed attempt finished and its results were recorded. |
| [`Proposal.Accepted`](#proposalaccepted) | `tl.core.Proposal.Accepted.v1` | A person accepted a proposal and its command ran in the same transaction. |
| [`Proposal.Created`](#proposalcreated) | `tl.core.Proposal.Created.v1` | An agent proposed a change. |
| [`Proposal.Failed`](#proposalfailed) | `tl.core.Proposal.Failed.v1` | A person accepted a proposal, but the command was refused (the record changed since, a guard failed). |
| [`Proposal.Rejected`](#proposalrejected) | `tl.core.Proposal.Rejected.v1` | A person rejected a proposal. |
| [`Pset.ValuesSet`](#psetvaluesset) | `tl.core.Pset.ValuesSet.v1` | Values of a property set were written on a record. |
| [`Record.BodyStored`](#recordbodystored) | `tl.core.Record.BodyStored.v1` | The body of an object-backed record was stored as a content-addressed object. |
| [`Record.Corrected`](#recordcorrected) | `tl.core.Record.Corrected.v1` | A recorded value was corrected after the fact; history keeps the original. |
| [`Record.Created`](#recordcreated) | `tl.core.Record.Created.v1` | A record was created. |
| [`Record.Updated`](#recordupdated) | `tl.core.Record.Updated.v1` | One or more fields of a record changed. |
| [`Record.Voided`](#recordvoided) | `tl.core.Record.Voided.v1` | A record was voided. |
| [`Rendition.Defined`](#renditiondefined) | `tl.core.Rendition.Defined.v1` | A file was registered as a rendition of a revision. |
| [`Rendition.Superseded`](#renditionsuperseded) | `tl.core.Rendition.Superseded.v1` | A rendition was replaced by a newer one of the same kind on the same revision. |
| [`ResponseClock.Cancelled`](#responseclockcancelled) | `tl.core.ResponseClock.Cancelled.v1` | The clock was cancelled: no answer is needed any more. |
| [`ResponseClock.Expired`](#responseclockexpired) | `tl.core.ResponseClock.Expired.v1` | The sweep found a running clock past its due date. |
| [`ResponseClock.Met`](#responseclockmet) | `tl.core.ResponseClock.Met.v1` | The clock was met: the answer came in time (or late; the date says which). |
| [`ResponseClock.Paused`](#responseclockpaused) | `tl.core.ResponseClock.Paused.v1` | A clock was paused; the days of the pause do not count. |
| [`ResponseClock.Restarted`](#responseclockrestarted) | `tl.core.ResponseClock.Restarted.v1` | A clock started its count again from a new day zero, with the same parameters. |
| [`ResponseClock.Resumed`](#responseclockresumed) | `tl.core.ResponseClock.Resumed.v1` | A paused clock ran again; the due date moved by the days of the pause. |
| [`ResponseClock.Started`](#responseclockstarted) | `tl.core.ResponseClock.Started.v1` | A response clock started. |
| [`ResponseClock.Warned`](#responseclockwarned) | `tl.core.ResponseClock.Warned.v1` | The sweep found a running clock at or inside a warning threshold smaller than the last one raised. |
| [`ReviewCycle.Closed`](#reviewcycleclosed) | `tl.core.ReviewCycle.Closed.v1` | A review cycle was closed with an overall outcome. |
| [`ReviewCycle.Defined`](#reviewcycledefined) | `tl.core.ReviewCycle.Defined.v1` | A review of a revision was opened with its reviewers. |
| [`ReviewCycle.OutcomeRecorded`](#reviewcycleoutcomerecorded) | `tl.core.ReviewCycle.OutcomeRecorded.v1` | A reviewer answered. |
| [`Revision.Defined`](#revisiondefined) | `tl.core.Revision.Defined.v1` | A revision of a document was created, as a draft. |
| [`Revision.Issued`](#revisionissued) | `tl.core.Revision.Issued.v1` | A revision was issued with an issue status; it is now current for its status class. |
| [`Revision.Superseded`](#revisionsuperseded) | `tl.core.Revision.Superseded.v1` | An issued revision stopped being current because a later one replaced it. |
| [`Rule.Blocked`](#ruleblocked) | `tl.core.Rule.Blocked.v1` | A matched event did not run the rule: the step was refused, the causation depth limit or a budget stopped it. |
| [`Rule.Created`](#rulecreated) | `tl.core.Rule.Created.v1` | A rule was created. |
| [`Rule.Disabled`](#ruledisabled) | `tl.core.Rule.Disabled.v1` | A rule was switched off. |
| [`Rule.Enabled`](#ruleenabled) | `tl.core.Rule.Enabled.v1` | A rule was switched on, from this event on. |
| [`Rule.Revised`](#rulerevised) | `tl.core.Rule.Revised.v1` | A rule was revised; the event carries the whole new rule. |
| [`Schedule.Defined`](#scheduledefined) | `tl.core.Schedule.Defined.v1` | A schedule was registered. |
| [`Schedule.OrphansChecked`](#scheduleorphanschecked) | `tl.core.Schedule.OrphansChecked.v1` | One run of the job that makes the links to a schedule's activities agree with its current snapshot (ADR-0015 section 5): activity references whose presence changed, links flagged stale (their activity is gone) and links restored (it came back). |
| [`Schedule.SnapshotPublished`](#schedulesnapshotpublished) | `tl.core.Schedule.SnapshotPublished.v1` | A snapshot became the schedule's current one. |
| [`ScheduleSnapshot.BuildFailed`](#schedulesnapshotbuildfailed) | `tl.core.ScheduleSnapshot.BuildFailed.v1` | A build attempt failed (a limit breach, a crash, a lease that ran out). |
| [`ScheduleSnapshot.BuildStarted`](#schedulesnapshotbuildstarted) | `tl.core.ScheduleSnapshot.BuildStarted.v1` | A worker claimed the build. |
| [`ScheduleSnapshot.Built`](#schedulesnapshotbuilt) | `tl.core.ScheduleSnapshot.Built.v1` | The file was read and passed the XER document schema; the typed rows were written. |
| [`ScheduleSnapshot.Defined`](#schedulesnapshotdefined) | `tl.core.ScheduleSnapshot.Defined.v1` | A snapshot was opened for a schedule; the XER file is attached next. |
| [`ScheduleSnapshot.MadeCurrent`](#schedulesnapshotmadecurrent) | `tl.core.ScheduleSnapshot.MadeCurrent.v1` | A snapshot was made the schedule's current one. |
| [`ScheduleSnapshot.Queued`](#schedulesnapshotqueued) | `tl.core.ScheduleSnapshot.Queued.v1` | The build of a snapshot was queued: the XER file is fixed. |
| [`ScheduleSnapshot.Rejected`](#schedulesnapshotrejected) | `tl.core.ScheduleSnapshot.Rejected.v1` | The file was read and is not a valid schedule snapshot (or could not be read): the snapshot is Invalid and no rows were written. |
| [`Schema.EffectiveChanged`](#schemaeffectivechanged) | `tl.core.Schema.EffectiveChanged.v1` | The effective schema of a scope changed. |
| [`SchemaPackage.Analysed`](#schemapackageanalysed) | `tl.core.SchemaPackage.Analysed.v1` | The classification and impact reports of the draft were made, for the content with the stated hash. |
| [`SchemaPackage.Approved`](#schemapackageapproved) | `tl.core.SchemaPackage.Approved.v1` | An administrator approved the package, having read the classification report with this digest. |
| [`SchemaPackage.ChangesRequested`](#schemapackagechangesrequested) | `tl.core.SchemaPackage.ChangesRequested.v1` | A reviewer sent the package back to Draft. |
| [`SchemaPackage.Deprecated`](#schemapackagedeprecated) | `tl.core.SchemaPackage.Deprecated.v1` | A published version was deprecated: projects that pinned it keep it, nobody can adopt it. |
| [`SchemaPackage.Drafted`](#schemapackagedrafted) | `tl.core.SchemaPackage.Drafted.v1` | A package version was drafted. |
| [`SchemaPackage.Published`](#schemapackagepublished) | `tl.core.SchemaPackage.Published.v1` | A schema package version was published. |
| [`SchemaPackage.Retired`](#schemapackageretired) | `tl.core.SchemaPackage.Retired.v1` | A deprecated version was retired: it is out of every effective schema. |
| [`SchemaPackage.Revised`](#schemapackagerevised) | `tl.core.SchemaPackage.Revised.v1` | The author changed the content of a draft. |
| [`SchemaPackage.Submitted`](#schemapackagesubmitted) | `tl.core.SchemaPackage.Submitted.v1` | The author sent the package to review. |
| [`Setting.Changed`](#settingchanged) | `tl.core.Setting.Changed.v1` | One key was set, or reset to what the layer above gives, at one layer. |
| [`Setting.Locked`](#settinglocked) | `tl.core.Setting.Locked.v1` | The company locked a key for its projects, unlocked it, or changed the bounds projects must keep to. |
| [`Standard.Closed`](#standardclosed) | `tl.core.Standard.Closed.v1` | A registry entry was superseded by another or retired; it stays resolvable for history. |
| [`Standard.Defined`](#standarddefined) | `tl.core.Standard.Defined.v1` | A registry entry (a code list, a mnemonic or a numbering pattern) was defined. |
| [`Tag.Defined`](#tagdefined) | `tl.core.Tag.Defined.v1` | A tag was created, with its number parsed into segments and its class. |
| [`Tag.Reclassified`](#tagreclassified) | `tl.core.Tag.Reclassified.v1` | A tag moved to another class; the new class may bind other property sets. |
| [`Tag.Superseded`](#tagsuperseded) | `tl.core.Tag.Superseded.v1` | A tag was replaced by one or more others (a rename, a split or a merge); it stays in the ledger as history. |
| [`TagClass.Closed`](#tagclassclosed) | `tl.core.TagClass.Closed.v1` | A tag class was retired; tags already of that class keep it. |
| [`TagClass.Defined`](#tagclassdefined) | `tl.core.TagClass.Defined.v1` | A tag class was defined. |
| [`TagClass.Revised`](#tagclassrevised) | `tl.core.TagClass.Revised.v1` | A tag class changed. |
| [`Technical.Answered`](#technicalanswered) | `tl.core.Technical.Answered.v1` | The answer to a Technical item was recorded, with the answerer's statement on cost and schedule. |
| [`Technical.Defined`](#technicaldefined) | `tl.core.Technical.Defined.v1` | A Technical item (RFI, technical query or deviation request) was raised. |
| [`Technical.Reissued`](#technicalreissued) | `tl.core.Technical.Reissued.v1` | A rejected Technical item went back to internal review to be issued again. |
| [`Technical.Reviewed`](#technicalreviewed) | `tl.core.Technical.Reviewed.v1` | The raiser accepted or rejected the answer. |
| [`Technical.Updated`](#technicalupdated) | `tl.core.Technical.Updated.v1` | The domain fields of a Technical item that is a draft or in internal review changed. |
| [`Thread.Dispatched`](#threaddispatched) | `tl.core.Thread.Dispatched.v1` | A slash command in a thread was confirmed and its commands ran, in the same transaction as the message of kind `dispatch` that carries the command line. |
| [`Thread.MessageEdited`](#threadmessageedited) | `tl.core.Thread.MessageEdited.v1` | The author replaced the body of a message. |
| [`Thread.MessagePosted`](#threadmessageposted) | `tl.core.Thread.MessagePosted.v1` | A message was posted in a record thread. |
| [`Thread.MessageRetracted`](#threadmessageretracted) | `tl.core.Thread.MessageRetracted.v1` | The author retracted a message. |
| [`Transmittal.Defined`](#transmittaldefined) | `tl.core.Transmittal.Defined.v1` | A transmittal was drafted with the revisions it carries and its recipients. |
| [`Transmittal.Issued`](#transmittalissued) | `tl.core.Transmittal.Issued.v1` | A transmittal was issued to its recipients. |
| [`Transmittal.ResponseRecorded`](#transmittalresponserecorded) | `tl.core.Transmittal.ResponseRecorded.v1` | The recipients answered a transmittal. |
| [`TypeRegistration.Deprecated`](#typeregistrationdeprecated) | `tl.core.TypeRegistration.Deprecated.v1` | The owner retired a version. |
| [`TypeRegistration.Quarantined`](#typeregistrationquarantined) | `tl.core.TypeRegistration.Quarantined.v1` | A type package failed validation, or its files changed under a version that is already registered. |
| [`TypeRegistration.Registered`](#typeregistrationregistered) | `tl.core.TypeRegistration.Registered.v1` | A type package validated and was registered. |
| [`Waiver.Approved`](#waiverapproved) | `tl.core.Waiver.Approved.v1` | An administrator approved the waiver; the effective schema of the project changes. |
| [`Waiver.Requested`](#waiverrequested) | `tl.core.Waiver.Requested.v1` | Someone asked to relax one property for a project until a date. |
| [`Waiver.Revoked`](#waiverrevoked) | `tl.core.Waiver.Revoked.v1` | An administrator revoked the waiver (or refused a request). |
| [`WebhookSubscription.Created`](#webhooksubscriptioncreated) | `tl.core.WebhookSubscription.Created.v1` | A webhook subscription was created. |
| [`WebhookSubscription.Disabled`](#webhooksubscriptiondisabled) | `tl.core.WebhookSubscription.Disabled.v1` | A subscription stopped receiving events. |
| [`WebhookSubscription.Enabled`](#webhooksubscriptionenabled) | `tl.core.WebhookSubscription.Enabled.v1` | A disabled subscription started receiving events again, from this event on. |
| [`WebhookSubscription.SecretRotated`](#webhooksubscriptionsecretrotated) | `tl.core.WebhookSubscription.SecretRotated.v1` | A new signing secret was issued; the previous one keeps signing until the overlap ends. |
| [`WebhookSubscription.Updated`](#webhooksubscriptionupdated) | `tl.core.WebhookSubscription.Updated.v1` | A subscription's name, target, filter or payload mode changed. |
| [`Workflow.Transitioned`](#workflowtransitioned) | `tl.core.Workflow.Transitioned.v1` | A record moved from one workflow state to another. |

## Account.Created

An account was created. A password, if any, is held outside the ledger. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.Created.v1`
- Ledger payload class: `AccountCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `display_name` | string | yes | Name shown in lists. |
| `kind` | string | yes | person, agent or sim. |
| `roles` | any | yes |  |
| `username` | string | yes | Normalised username. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "display_name": "Demo User",
      "kind": "person",
      "roles": [
        "admin"
      ],
      "username": "demo"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Account.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.Created.v1"
}
```

## Account.Disabled

An account was disabled: it cannot sign in and its sessions and agent tokens stop working. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.Disabled.v1`
- Ledger payload class: `AccountDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `reason` | string or null | no | Why it was disabled. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "reason": "left the project"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Account.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.Disabled.v1"
}
```

## Account.Enabled

A disabled account was enabled again. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.Enabled.v1`
- Ledger payload class: `AccountEnabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `reason` | string or null | no | Why it was enabled. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "reason": "returned"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Account.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.Enabled.v1"
}
```

## Account.PasswordChanged

The password of an account was set or changed. The event records that it happened, never the password or its hash. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.PasswordChanged.v1`
- Ledger payload class: `AccountPasswordChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `by` | string | yes | Actor that changed it. |
| `forced` | boolean | yes | True for an admin reset or a bootstrap, false for the person changing their own. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "by": "user:demo",
      "forced": true
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Account.PasswordChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.PasswordChanged.v1"
}
```

## Account.RolesSet

The roles of an account were replaced. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.Account.RolesSet.v1`
- Ledger payload class: `AccountRolesSetPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | Account id. |
| `reason` | string or null | no | Why the roles changed. |
| `roles` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "reason": "promoted to run the admin module",
      "roles": [
        "admin",
        "user"
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Account.RolesSet/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Account.RolesSet.v1"
}
```

## Action.Completed

The executor finished the action.

- CloudEvents type: `tl.core.Action.Completed.v1`
- Ledger payload class: `ActionCompletedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | Attempt number. |
| `http_status` | integer or null | no | HTTP status of a webhook action. |
| `invocation_id` | string | yes | Invocation id. |
| `result` | any | no | The executor's bounded JSON result. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 1,
      "http_status": 200,
      "invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "result": {
        "accepted": true
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Action.Completed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Action.Completed.v1"
}
```

## Action.Failed

The action failed for good (not retried any more).

- CloudEvents type: `tl.core.Action.Failed.v1`
- Ledger payload class: `ActionFailedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | Attempt number. |
| `http_status` | integer or null | no | HTTP status of a webhook action. |
| `invocation_id` | string | yes | Invocation id. |
| `problems` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 3,
      "http_status": 503,
      "invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "problems": [
        {
          "code": "http_error",
          "message": "The receiver answered 503."
        }
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Action.Failed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Action.Failed.v1"
}
```

## Action.Requested

An action was requested on records. The execution is queued as a job.

- CloudEvents type: `tl.core.Action.Requested.v1`
- Ledger payload class: `ActionRequestedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `action` | string | yes | Action name. |
| `action_version` | integer | yes | Definition version run. |
| `definition_id` | string | yes | Definition id. |
| `invocation_id` | string | yes | Invocation id. |
| `invoked_by` | string | yes | Who asked. |
| `parameters` | any | yes |  |
| `proposal_id` | string or null | no | The accepted proposal this came from, when the action requires approval. |
| `targets` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "action": "send_to_nde",
      "action_version": 1,
      "definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2",
      "invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "invoked_by": "user:jsmith",
      "parameters": {
        "method": "RT"
      },
      "targets": [
        {
          "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
          "key": "47-1234-W012",
          "record_type": "core.Record",
          "version": 3
        }
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Action.Requested/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Action.Requested.v1"
}
```

## Action.Running

A worker started an attempt.

- CloudEvents type: `tl.core.Action.Running.v1`
- Ledger payload class: `ActionRunningPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | Attempt number, from 1. |
| `invocation_id` | string | yes | Invocation id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 1,
      "invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Action.Running/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Action.Running.v1"
}
```

## ActionDefinition.Defined

An action was defined (version 1). A webhook action's signing secret is held outside the ledger.

- CloudEvents type: `tl.core.ActionDefinition.Defined.v1`
- Ledger payload class: `ActionDefinitionDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `access` | string | yes | user, controller or admin. |
| `applies_to` | any | yes |  |
| `definition_id` | string | yes | Definition id. |
| `description` | string or null | no | Description. |
| `enabled` | boolean or null | no | Whether it can be invoked. |
| `executor` | string | yes | job or webhook. |
| `executor_config` | any | yes |  |
| `integration_app` | string or null | no | Integration app name. |
| `label` | string | yes | Label. |
| `name` | string | yes | Action name (slug). |
| `owner` | string | yes | Owner actor. |
| `parameters` | any | yes |  |
| `requires_approval` | boolean or null | no | Whether an invocation waits for a second person. |
| `result_handling` | any | yes |  |
| `secret_id` | string or null | no | Id of the first signing secret of a webhook action (not the secret). |
| `side_effect_class` | string | yes | read, propose, write or external. |
| `version` | integer | yes | Definition version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "access": "user",
      "applies_to": {
        "condition": null,
        "record_types": [
          "core.Record"
        ]
      },
      "definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2",
      "description": "Send an inspection request to the NDE contractor",
      "enabled": true,
      "executor": "webhook",
      "executor_config": {
        "kind": "webhook",
        "timeout_s": 10.0,
        "url": "https://nde.example.net/hooks/request"
      },
      "integration_app": "acme-nde",
      "label": "Send to NDE",
      "name": "send_to_nde",
      "owner": "user:jsmith",
      "parameters": [
        {
          "choices": [
            "RT",
            "UT"
          ],
          "kind": "string",
          "label": "Method",
          "max_length": null,
          "name": "method",
          "required": true
        }
      ],
      "requires_approval": false,
      "result_handling": [
        "store"
      ],
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P3",
      "side_effect_class": "external",
      "version": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ActionDefinition.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ActionDefinition.Defined.v1"
}
```

## ActionDefinition.Retired

An action was retired: it can no longer be invoked; its invocations stay readable.

- CloudEvents type: `tl.core.ActionDefinition.Retired.v1`
- Ledger payload class: `ActionDefinitionRetiredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `definition_id` | string | yes | Definition id. |
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2",
      "reason": "replaced by send_to_nde_v2"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ActionDefinition.Retired/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ActionDefinition.Retired.v1"
}
```

## ActionDefinition.Revised

An action was revised; the event carries the whole new definition and the row is replaced.

- CloudEvents type: `tl.core.ActionDefinition.Revised.v1`
- Ledger payload class: `ActionDefinitionRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `definition` | any | yes |  |
| `definition_id` | string | yes | Definition id. |
| `reason` | string | yes | Why. |
| `version` | integer | yes | The new definition version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "definition": {
        "label": "Send to NDE contractor",
        "name": "send_to_nde",
        "version": 2
      },
      "definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2",
      "reason": "label",
      "version": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ActionDefinition.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ActionDefinition.Revised.v1"
}
```

## ActionDefinition.SecretRotated

A new signing secret was issued for a webhook action; the previous one keeps verifying until the overlap ends.

- CloudEvents type: `tl.core.ActionDefinition.SecretRotated.v1`
- Ledger payload class: `ActionDefinitionSecretRotatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `definition_id` | string | yes | Definition id. |
| `previous_expires_at` | string or null | no | ISO-8601 time when the previous secret stops. |
| `previous_secret_id` | string or null | no | Id of the secret being replaced. |
| `secret_id` | string | yes | Id of the new secret (not the secret). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "definition_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2",
      "previous_expires_at": "2026-10-18T03:14:07.000000Z",
      "previous_secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P3",
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P4"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ActionDefinition.SecretRotated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ActionDefinition.SecretRotated.v1"
}
```

## ActivityRef.Defined

The first link to an activity made its reference.

- CloudEvents type: `tl.core.ActivityRef.Defined.v1`
- Ledger payload class: `ActivityRefDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `activity_id` | string | yes | The P6 activity id. |
| `first_snapshot_id` | string | yes | The snapshot that had the activity. |
| `first_snapshot_number` | integer | yes | Its number. |
| `schedule_code` | string | yes | Its code. |
| `schedule_id` | string | yes | The schedule. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "activity_id": "A1230",
      "first_snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "first_snapshot_number": 1,
      "schedule_code": "MAIN",
      "schedule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ActivityRef.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ActivityRef.Defined.v1"
}
```

## ActivityRef.PresenceChanged

A publication found the activity gone from the schedule (present false) or back (present true).

- CloudEvents type: `tl.core.ActivityRef.PresenceChanged.v1`
- Ledger payload class: `ActivityRefPresencePayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `last_seen_number` | integer | yes | Its number. |
| `last_seen_snapshot_id` | string | yes | The latest published snapshot that had the activity. |
| `present` | boolean | yes | Whether the published snapshot has the activity. |
| `snapshot_id` | string | yes | The snapshot that was published. |
| `snapshot_number` | integer | yes | Its number. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "last_seen_number": 1,
      "last_seen_snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "present": false,
      "snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "snapshot_number": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ActivityRef.PresenceChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ActivityRef.PresenceChanged.v1"
}
```

## Adoption.Pinned

A project pinned a version of a company package. The record is created by the first pin.

- CloudEvents type: `tl.core.Adoption.Pinned.v1`
- Ledger payload class: `AdoptionPinnedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `adopted_by` | string | yes | The administrator that pinned it, or the publisher for an automatic pin. |
| `auto` | boolean or null | no | True when publication pinned it (an additive version, auto-adoption on). |
| `impact_sha256` | string or null | no | The SHA-256 of the project impact report the adopter saw, or null for an additive pin. |
| `package` | string | yes | The company package name. |
| `previous_version` | string or null | no | The version pinned before, or null. |
| `project` | string | yes | The project id. |
| `version` | string | yes | The pinned version. |
| `worst_class` | string or null | no | The worst class of the change from the previous version, or null for a first pin. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "adopted_by": "user:admin",
      "auto": false,
      "impact_sha256": null,
      "package": "co.acme.engineering",
      "previous_version": "3.2.0",
      "project": "P123",
      "version": "3.3.0",
      "worst_class": "additive"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Adoption.Pinned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Adoption.Pinned.v1"
}
```

## AgentToken.Issued

An agent token was issued. The event holds its metadata; the token is shown once and stored only as a hash. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.AgentToken.Issued.v1`
- Ledger payload class: `AgentTokenIssuedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | The agent account. |
| `expires_at` | string or null | no | ISO-8601 time after which the token stops working; null for none. |
| `label` | string | yes | What the token is for. |
| `token_id` | string | yes | Token id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "expires_at": "2027-01-09T03:14:07.000000Z",
      "label": "triage assistant",
      "token_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/AgentToken.Issued/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.AgentToken.Issued.v1"
}
```

## AgentToken.Revoked

An agent token was revoked and no longer authenticates. Internal: never delivered to webhooks.

- CloudEvents type: `tl.core.AgentToken.Revoked.v1`
- Ledger payload class: `AgentTokenRevokedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account_id` | string | yes | The agent account. |
| `reason` | string or null | no | Why it was revoked. |
| `token_id` | string | yes | Token id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "reason": "rotated",
      "token_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/AgentToken.Revoked/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.AgentToken.Revoked.v1"
}
```

## CodeValue.Closed

A code value was superseded by another or retired; it still resolves for old records.

- CloudEvents type: `tl.core.CodeValue.Closed.v1`
- Ledger payload class: `CodeValueClosedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `effective_to` | string or null | no | ISO date the value stops applying. |
| `lifecycle` | string | yes | superseded or retired. |
| `reason` | string | yes | Why. |
| `superseded_by` | string or null | no | Record id of the value that replaced this one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "effective_to": null,
      "lifecycle": "retired",
      "reason": "No longer used on site",
      "superseded_by": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CodeValue.Closed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CodeValue.Closed.v1"
}
```

## CodeValue.Defined

A value was added to a code list.

- CloudEvents type: `tl.core.CodeValue.Defined.v1`
- Ledger payload class: `CodeValueDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attributes` | any | no | List-specific content. |
| `code` | string | yes | The value's code. |
| `code_list` | string | yes | Code of the list. |
| `crosswalk` | string or null | no | The company code a project-added value maps to. |
| `edition` | string | yes | The standards edition that supplied the value. |
| `effective_from` | string or null | no | ISO date from which the value applies. |
| `effective_to` | string or null | no | ISO date after which it no longer applies. |
| `label` | string | yes | Display text. |
| `meaning` | string or null | no | IRI that says what the value means. |
| `origin` | string | yes | company or project. |
| `sort_order` | integer or null | no | Position in the list. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attributes": {},
      "code": "PIP",
      "code_list": "Discipline",
      "crosswalk": null,
      "edition": "co.acme.standards@1.0.0",
      "effective_from": null,
      "effective_to": null,
      "label": "Piping",
      "meaning": null,
      "origin": "company",
      "sort_order": 10
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CodeValue.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CodeValue.Defined.v1"
}
```

## Commercial.Assessed

The other party assessed an issued Commercial item: agreed, disputed or partially agreed, with the value they assessed.

- CloudEvents type: `tl.core.Commercial.Assessed.v1`
- Ledger payload class: `CommercialAssessedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `assessed_on` | string | yes | ISO date of the assessment. |
| `assessed_value` | string or null | no | Decimal text, at most two places. |
| `date_reason` | string or null | no | Why the date is before the day it was recorded; null when it is that day. |
| `feed_policy` | string or null | no | full, minimal or none: what the feed shows (the domain's policy at the time). |
| `feed_text` | string or null | no | The line of the feed card when the policy is full or minimal. |
| `note` | string or null | no | The assessor's reasoning. |
| `status` | string | yes | agreed, disputed or partially_agreed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "assessed_on": "2026-11-10",
      "assessed_value": "9000.00",
      "date_reason": null,
      "note": "Hours reduced",
      "status": "partially_agreed"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Commercial.Assessed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Commercial.Assessed.v1"
}
```

## Commercial.Defined

A Commercial item (early warning, change notice, claim ...) was raised. It follows the `Correspondence.Defined` event of the same item in the same append and holds the domain data.

- CloudEvents type: `tl.core.Commercial.Defined.v1`
- Ledger payload class: `CommercialDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `aware_on` | string or null | no | ISO date the contractor became aware; the time bar runs from it. |
| `contract_clause_id` | string or null | no | Record id of the contract clause the notice is given under. |
| `cost_code_impacts` | any | yes |  |
| `currency` | string or null | no | ISO 4217 code of every amount. |
| `derived_from_id` | string or null | no | Record id of the item this one was escalated from. |
| `entitlement_basis` | string or null | no | Why the contractor is entitled. |
| `estimated_hours` | string or null | no | Decimal text, at most one place. |
| `estimated_value` | string or null | no | Decimal text, at most two places. |
| `schedule_impact_days` | integer or null | no | Days of delay, negative for acceleration. |
| `schedule_impact_note` | string or null | no | The schedule impact in words. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "aware_on": "2026-10-20",
      "contract_clause_id": null,
      "cost_code_impacts": [
        {
          "amount": "12500.00",
          "cost_code": "2.3.1",
          "hours": null,
          "quantity": null,
          "uom": null
        }
      ],
      "currency": "USD",
      "derived_from_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "entitlement_basis": "Clause 20.1: instruction changing the routing",
      "estimated_hours": "240.5",
      "estimated_value": "12500.00",
      "schedule_impact_days": 3,
      "schedule_impact_note": "Piping spool S-14 is re-fabricated"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Commercial.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Commercial.Defined.v1"
}
```

## Commercial.Updated

The domain fields of a Commercial item that is not yet issued changed.

- CloudEvents type: `tl.core.Commercial.Updated.v1`
- Ledger payload class: `CommercialUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string or null | no | Why it changed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "estimated_value": [
        "12500.00",
        "14000.00"
      ]
    },
    "detail": {
      "changes": {
        "estimated_value": [
          "12500.00",
          "14000.00"
        ]
      },
      "reason": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Commercial.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Commercial.Updated.v1"
}
```

## ContractClause.Defined

A contract clause was entered.

- CloudEvents type: `tl.core.ContractClause.Defined.v1`
- Ledger payload class: `ContractClauseDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `clause_number` | string | yes | The clause number. |
| `contract` | string | yes | The contract. |
| `contract_document_id` | string or null | no | Record id of the contract document. |
| `domains` | any | yes |  |
| `notice_requirements` | string or null | no | What the notice must contain. |
| `required_recipients` | any | yes |  |
| `service_method` | string or null | no | email, letter, portal or hand. |
| `time_bar_day_type` | string or null | no | calendar or working. |
| `time_bar_days` | integer or null | no | Days allowed; null when none. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "clause_number": "20.1",
      "contract": "MSA-2026",
      "contract_document_id": null,
      "domains": [
        "general"
      ],
      "notice_requirements": "State the event and the date it was noticed",
      "required_recipients": [
        "project_manager"
      ],
      "service_method": "letter",
      "time_bar_day_type": "calendar",
      "time_bar_days": 28
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ContractClause.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ContractClause.Defined.v1"
}
```

## ContractClause.Retired

A clause was retired; clocks that cited it keep their reference.

- CloudEvents type: `tl.core.ContractClause.Retired.v1`
- Ledger payload class: `ContractClauseRetiredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Replaced by the amended contract"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ContractClause.Retired/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ContractClause.Retired.v1"
}
```

## Correspondence.ClearanceGranted

An account was named as able to read a privileged item (ADR-0016).

- CloudEvents type: `tl.core.Correspondence.ClearanceGranted.v1`
- Ledger payload class: `CorrespondenceClearanceGrantedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account` | string | yes | The account name. |
| `granted_on` | string | yes | ISO date. |
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account": "user:amy",
      "granted_on": "2026-10-17",
      "reason": "Counsel"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.ClearanceGranted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.ClearanceGranted.v1"
}
```

## Correspondence.ClearanceWithdrawn

An account was removed from the readers of a privileged item.

- CloudEvents type: `tl.core.Correspondence.ClearanceWithdrawn.v1`
- Ledger payload class: `CorrespondenceClearanceWithdrawnPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `account` | string | yes | The account name. |
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "account": "user:amy",
      "reason": "Matter closed"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.ClearanceWithdrawn/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.ClearanceWithdrawn.v1"
}
```

## Correspondence.ConfidentialityChanged

The confidentiality class of an item changed (a controller's act, ADR-0016).

- CloudEvents type: `tl.core.Correspondence.ConfidentialityChanged.v1`
- Ledger payload class: `CorrespondenceConfidentialityChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `from_class` | string | yes | Class before. |
| `reason` | string | yes | Why. |
| `to_class` | string | yes | Class after. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "from_class": "internal",
      "reason": "Contains commercial terms",
      "to_class": "restricted"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.ConfidentialityChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.ConfidentialityChanged.v1"
}
```

## Correspondence.Defined

A correspondence item was received, drafted or logged. The subject is the title of the `Record.Created` event that comes first.

- CloudEvents type: `tl.core.Correspondence.Defined.v1`
- Ledger payload class: `CorrespondenceDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `body` | string or null | no | Plain text of the item or its summary. |
| `cc` | any | yes |  |
| `confidentiality` | string | yes | internal, restricted or privileged. |
| `direction` | string | yes | in, out or internal. |
| `domain` | string or null | no | Domain code when known at creation (an outgoing item). |
| `external_ref` | string or null | no | The sender's own reference. |
| `from_name` | string or null | no | Who sent it, as written. |
| `from_party_id` | string or null | no | Record id of the sending party, when known. |
| `in_reply_to` | string or null | no | Email In-Reply-To, normalised. |
| `medium` | string | yes | letter, email, portal, minutes or other. |
| `message_id` | string or null | no | Email Message-ID, normalised. |
| `number` | string | yes | The item number. |
| `received_on` | string or null | no | ISO date it arrived. |
| `received_via` | string | yes | upload, email or manual. |
| `responds_to_id` | string or null | no | Record id of the item this one answers, when stated. |
| `response_due` | string or null | no | ISO date an answer is due. |
| `response_required` | boolean or null | no | True when an answer is expected. |
| `sent_on` | string or null | no | ISO date the sender dated it. |
| `subtype` | string or null | no | Subtype when known at creation. |
| `to` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "body": "Please confirm the revised programme.",
      "cc": [],
      "confidentiality": "internal",
      "direction": "in",
      "external_ref": "MER/L/0042",
      "from_name": "Meridian Energy",
      "medium": "letter",
      "number": "P123-COR-0001",
      "received_on": "2026-10-17",
      "received_via": "upload",
      "response_required": true,
      "sent_on": "2026-10-16",
      "to": [
        {
          "email": null,
          "name": "Project manager",
          "party_id": null
        }
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.Defined.v1"
}
```

## Correspondence.Issued

An outgoing item was issued: its text was rendered to a PDF (stored in the slot `rendition`) and sent. Sending is a stub in Phase 1; nothing leaves the machine.

- CloudEvents type: `tl.core.Correspondence.Issued.v1`
- Ledger payload class: `CorrespondenceIssuedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `clock_ids` | any | yes |  |
| `date_reason` | string or null | no | Why the date is before the day it was recorded; null when it is that day. |
| `delivery` | string | yes | stub: no message was sent. |
| `feed_policy` | string or null | no | full, minimal or none: what the feed shows of the issue (the domain's policy, fixed when the event is written). Absent means the generic card. |
| `feed_text` | string or null | no | The line of the feed card when the policy is full or minimal. |
| `issued_on` | string | yes | ISO date of the issue. |
| `rendition_file_id` | string | yes | File id of the PDF rendition. |
| `rendition_sha256` | string | yes | Hex SHA-256 of the rendition. |
| `template` | string | yes | The letter template used. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "clock_ids": [],
      "date_reason": null,
      "delivery": "stub",
      "issued_on": "2026-10-17",
      "rendition_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "rendition_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "template": "general-letter"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.Issued/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.Issued.v1"
}
```

## Correspondence.Reclassified

The domain or subtype of an item changed before it was issued. After issue a misfiled item gets a linked item in the right domain instead.

- CloudEvents type: `tl.core.Correspondence.Reclassified.v1`
- Ledger payload class: `CorrespondenceReclassifiedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `domain` | string | yes | Domain after. |
| `from_domain` | string or null | no | Domain before. |
| `from_subtype` | string or null | no | Subtype before. |
| `reason` | string | yes | Why. |
| `subtype` | string | yes | Subtype after. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "domain": "document_control",
      "from_domain": "general",
      "from_subtype": "letter",
      "reason": "It transmits drawings",
      "subtype": "submittal"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.Reclassified/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.Reclassified.v1"
}
```

## Correspondence.Responded

An answer to an item was issued or received.

- CloudEvents type: `tl.core.Correspondence.Responded.v1`
- Ledger payload class: `CorrespondenceRespondedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `responded_on` | string | yes | ISO date of the answer. |
| `response_id` | string or null | no | Record id of the answering item; null when the answer is not an item of the register (a Technical item answered in the form). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "responded_on": "2026-10-17",
      "response_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.Responded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.Responded.v1"
}
```

## Correspondence.Superseded

An item was replaced by another item; it stays in the ledger.

- CloudEvents type: `tl.core.Correspondence.Superseded.v1`
- Ledger payload class: `CorrespondenceSupersededPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |
| `superseded_by_id` | string | yes | Record id of the replacing item. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Corrected figures",
      "superseded_by_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.Superseded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.Superseded.v1"
}
```

## Correspondence.ThreadAssigned

An item joined a thread, and optionally answers another item.

- CloudEvents type: `tl.core.Correspondence.ThreadAssigned.v1`
- Ledger payload class: `CorrespondenceThreadAssignedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `matched_by` | string | yes | header, reference_key, subject or manual. |
| `responds_to_id` | string or null | no | Record id of the item this one answers. |
| `thread_id` | string | yes | Record id of the thread. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "matched_by": "header",
      "responds_to_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "thread_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.ThreadAssigned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.ThreadAssigned.v1"
}
```

## Correspondence.Triaged

A person confirmed the domain and subtype of a received item, with the records it refers to and the clocks that were started. A proposal by an agent is a proposal, not this event.

- CloudEvents type: `tl.core.Correspondence.Triaged.v1`
- Ledger payload class: `CorrespondenceTriagedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `clock_ids` | any | yes |  |
| `domain` | string | yes | Domain code. |
| `referenced_ids` | any | yes |  |
| `subtype` | string | yes | Subtype code. |
| `suggestion` | string or null | no | The domain the suggestion engine proposed, when it differs from the confirmed one; null otherwise. |
| `triaged_on` | string | yes | ISO date. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "clock_ids": [],
      "domain": "general",
      "referenced_ids": [],
      "subtype": "letter",
      "suggestion": null,
      "triaged_on": "2026-10-17"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.Triaged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.Triaged.v1"
}
```

## Correspondence.Updated

The register fields of a draft or received item changed (the subject changes through the core `Record.Updated`).

- CloudEvents type: `tl.core.Correspondence.Updated.v1`
- Ledger payload class: `CorrespondenceUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string or null | no | Why it changed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "body": [
        "Draft",
        "Final text"
      ]
    },
    "detail": {
      "changes": {
        "body": [
          "Draft",
          "Final text"
        ]
      },
      "reason": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Correspondence.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Correspondence.Updated.v1"
}
```

## CorrespondenceThread.Defined

A thread was opened by its first item.

- CloudEvents type: `tl.core.CorrespondenceThread.Defined.v1`
- Ledger payload class: `CorrespondenceThreadDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `domain` | string or null | no | Domain code, when known. |
| `governing_item_id` | string | yes | Record id of the first item. |
| `item_on` | string or null | no | ISO date of the first item. |
| `number` | string | yes | The thread number. |
| `subject_key` | string | yes | The normalised subject. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "domain": null,
      "governing_item_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "item_on": "2026-10-17",
      "number": "P123-THR-0001",
      "subject_key": "revised programme"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CorrespondenceThread.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CorrespondenceThread.Defined.v1"
}
```

## CorrespondenceThread.ItemAdded

An item joined the thread.

- CloudEvents type: `tl.core.CorrespondenceThread.ItemAdded.v1`
- Ledger payload class: `CorrespondenceThreadItemAddedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `item_id` | string | yes | Record id of the item. |
| `item_on` | string or null | no | ISO date of the item. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "item_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "item_on": "2026-10-18"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CorrespondenceThread.ItemAdded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CorrespondenceThread.ItemAdded.v1"
}
```

## CorrespondenceThread.StateChanged

A thread was closed or reopened.

- CloudEvents type: `tl.core.CorrespondenceThread.StateChanged.v1`
- Ledger payload class: `CorrespondenceThreadStateChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why. |
| `state` | string | yes | open or closed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Every question answered",
      "state": "closed"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CorrespondenceThread.StateChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CorrespondenceThread.StateChanged.v1"
}
```

## CostCode.Defined

A cost code was registered (by the first snapshot that names it).

- CloudEvents type: `tl.core.CostCode.Defined.v1`
- Ledger payload class: `CostCodeDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | The cost code. |
| `level` | integer | yes | Depth in the hierarchy. |
| `parent_code` | string or null | no | The parent code, or null. |
| `uom` | string or null | no | Unit of measure of the quantity figures. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "4210-PIP-WLD",
      "level": 3,
      "parent_code": "4210-PIP",
      "uom": "in-dia"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CostCode.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CostCode.Defined.v1"
}
```

## CostCode.MeasuresRecorded

A snapshot stated the figures of a cost code.

- CloudEvents type: `tl.core.CostCode.MeasuresRecorded.v1`
- Ledger payload class: `CostCodeMeasuresRecordedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `as_of` | string | yes | YYYY-MM-DD. |
| `measures` | any | yes |  |
| `period` | string | yes | YYYY-MM. |
| `revision` | integer | yes | The snapshot's revision of the period. |
| `snapshot_id` | string | yes | The snapshot. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "as_of": "2026-09-30",
      "measures": {
        "amount_actual": 51240.0,
        "amount_budget": 96000.0,
        "amount_eac": 102440.0,
        "amount_earned": 48000.0,
        "amount_ftc": 51200.0,
        "hours_actual": 640.5,
        "hours_budget": 1200.0,
        "hours_eac": 1280.5,
        "hours_earned": 600.0,
        "hours_ftc": 640.0,
        "quantity_actual": 250.0,
        "quantity_budget": 480.0,
        "quantity_eac": 480.0,
        "quantity_earned": 250.0,
        "quantity_ftc": 230.0
      },
      "period": "2026-09",
      "revision": 1,
      "snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CostCode.MeasuresRecorded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CostCode.MeasuresRecorded.v1"
}
```

## CostCode.Revised

A snapshot changed the description, parent or unit of measure of an existing cost code.

- CloudEvents type: `tl.core.CostCode.Revised.v1`
- Ledger payload class: `CostCodeRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `snapshot_id` | string | yes | The snapshot that brought the change. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "changes": {
        "uom": [
          "ea",
          "in-dia"
        ]
      },
      "snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CostCode.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CostCode.Revised.v1"
}
```

## CostSnapshot.Defined

A period of figures was imported.

- CloudEvents type: `tl.core.CostSnapshot.Defined.v1`
- Ledger payload class: `CostSnapshotDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `as_of` | string | yes | YYYY-MM-DD. |
| `currency` | string or null | no | ISO 4217 code, or null. |
| `new_code_count` | integer | yes | Codes created. |
| `period` | string | yes | YYYY-MM. |
| `revised_code_count` | integer | yes | Codes revised. |
| `revision` | integer | yes | 1 for the first import of the period. |
| `row_count` | integer | yes | Codes with figures. |
| `source_name` | string or null | no | Display name of the file. |
| `source_sha256` | string or null | no | SHA-256 of the file. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "as_of": "2026-09-30",
      "currency": "USD",
      "new_code_count": 3,
      "period": "2026-09",
      "revised_code_count": 0,
      "revision": 1,
      "row_count": 12,
      "source_name": "cost-2026-09.csv",
      "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/CostSnapshot.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.CostSnapshot.Defined.v1"
}
```

## DerivedDocument.ContentRecorded

One extractor pass over a source file finished: a new content revision of the derived document. The rows are in the result file; this event keeps the counts, the file's hash and the extractor's real metadata.

- CloudEvents type: `tl.core.DerivedDocument.ContentRecorded.v1`
- Ledger payload class: `DerivedDocumentContentRecordedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `column_count` | integer | yes | Columns read. |
| `content_rev` | integer | yes | Content revision, from 1. |
| `extraction_status` | string | yes | ok, metadata_only, unsupported or failed. |
| `extractor` | string | yes | Extractor name. |
| `extractor_notes` | any | no | The extractor's notes. |
| `extractor_version` | string | yes | Extractor version. |
| `file_metadata` | any | no | The real file metadata. |
| `job_id` | string or null | no | Record id of the processing job. |
| `method` | string | yes | manual, automated or hybrid, after this pass. |
| `problem_count` | integer | yes | Reading problems reported by the extractor. |
| `result_file_id` | string or null | no | The result file, when the pass produced rows. |
| `result_sha256` | string or null | no | Hex SHA-256 of the result file. |
| `row_count` | integer | yes | Rows read. |
| `source_file_id` | string | yes | The file the extractor read. |
| `source_kind` | string | yes | rendition or upload. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "column_count": 0,
      "content_rev": 1,
      "extraction_status": "metadata_only",
      "extractor": "pdf",
      "extractor_notes": [
        "content extraction stubbed (ADR-0008 decision 8)"
      ],
      "extractor_version": "1",
      "file_metadata": {
        "content_type": "application/pdf",
        "page_count": 2,
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "size": 1024
      },
      "job_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "method": "automated",
      "problem_count": 0,
      "result_file_id": null,
      "result_sha256": null,
      "row_count": 0,
      "source_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "source_kind": "rendition"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/DerivedDocument.ContentRecorded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.DerivedDocument.ContentRecorded.v1"
}
```

## DerivedDocument.Defined

A derived document was opened for a source revision and a document schema.

- CloudEvents type: `tl.core.DerivedDocument.Defined.v1`
- Ledger payload class: `DerivedDocumentDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `method` | string | yes | manual, automated or hybrid. |
| `previous_derived_id` | string or null | no | Record id of the derived document of the previous revision, when there is one. |
| `schema_code` | string | yes | The schema code. |
| `schema_id` | string | yes | Record id of the document schema version. |
| `schema_version` | string | yes | The schema version. |
| `source_document_id` | string | yes | Record id of the source document. |
| `source_document_number` | string | yes | The document number. |
| `source_ref` | string | yes | The provenance string src.doc.<number>@<revision>. |
| `source_revision_code` | string | yes | The revision code. |
| `source_revision_id` | string | yes | Record id of the source revision. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "method": "automated",
      "previous_derived_id": null,
      "schema_code": "instrument-index",
      "schema_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "schema_version": "1.0.0",
      "source_document_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "source_document_number": "ISD-001",
      "source_ref": "src.doc.ISD-001@A",
      "source_revision_code": "A",
      "source_revision_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/DerivedDocument.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.DerivedDocument.Defined.v1"
}
```

## DerivedDocument.PublicationCompensated

The publication of a derived document was rolled back: reversing events for everything its import made were appended under a correlation id of their own. The original events stay in the ledger.

- CloudEvents type: `tl.core.DerivedDocument.PublicationCompensated.v1`
- Ledger payload class: `DerivedDocumentPublicationCompensatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `compensation_correlation_id` | string | yes | The correlation id of the reversing events. |
| `content_rev` | integer | yes | The content revision whose publication was rolled back. |
| `import_correlation_id` | string | yes | The correlation id of the import that was rolled back. |
| `reason` | string | yes | Why. |
| `reversed_count` | integer | yes | Records reversed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "compensation_correlation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC",
      "content_rev": 2,
      "import_correlation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "reason": "Loaded against the wrong revision",
      "reversed_count": 40
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/DerivedDocument.PublicationCompensated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.DerivedDocument.PublicationCompensated.v1"
}
```

## DerivedDocument.Published

The rows of a valid content revision were published into target records as one correlated import. The payload names the records and links the import made, by id; the import's events also carry `import_correlation_id`, but that is a convenience for reading the ledger, not what compensation trusts.

- CloudEvents type: `tl.core.DerivedDocument.Published.v1`
- Ledger payload class: `DerivedDocumentPublishedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_rev` | integer | yes | The content revision published. |
| `created_count` | integer | yes | Records created. |
| `import_correlation_id` | string | yes | The correlation id of every event of the import. |
| `link_ids` | array | yes | The ids of the `derived_from` links the import created, exactly. |
| `mapping_hash` | string | yes | Hex SHA-256 of the mapping applied. |
| `record_ids` | array | yes | The ids of the records the import created, exactly. Compensation reverses these and nothing else; it never reads 'the events that carry this correlation id' (a client can set a correlation id). |
| `result_sha256` | string | yes | Hex SHA-256 of the rows published. |
| `target_kind` | string | yes | tags or documents. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_rev": 2,
      "created_count": 40,
      "import_correlation_id": "derive:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "link_ids": [],
      "mapping_hash": "0000000000000000000000000000000000000000000000000000000000000000",
      "record_ids": [],
      "result_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "target_kind": "tags"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/DerivedDocument.Published/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.DerivedDocument.Published.v1"
}
```

## DerivedDocument.Validated

A content revision was checked against a document schema version. The row and field problems are in the report file; this event keeps the verdict and the counts.

- CloudEvents type: `tl.core.DerivedDocument.Validated.v1`
- Ledger payload class: `DerivedDocumentValidatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_rev` | integer | yes | The content revision checked. |
| `error_count` | integer | yes | Errors found. |
| `job_id` | string or null | no | Record id of the processing job, when one ran it. |
| `report_file_id` | string or null | no | The report file. |
| `report_sha256` | string or null | no | Hex SHA-256 of the report. |
| `schema_code` | string | yes | Schema code. |
| `schema_id` | string | yes | Record id of the schema version. |
| `schema_version` | string | yes | Schema version. |
| `validation_status` | string | yes | valid or invalid. |
| `warning_count` | integer | yes | Warnings found. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_rev": 1,
      "error_count": 1,
      "job_id": null,
      "report_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "report_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "schema_code": "instrument-index",
      "schema_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "schema_version": "1.0.0",
      "validation_status": "invalid",
      "warning_count": 0
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/DerivedDocument.Validated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.DerivedDocument.Validated.v1"
}
```

## Document.CurrentRevisionChanged

The revision in force for a document changed (an issue, a supersession or a void). Carries the new denormalised values; all null when no revision is current.

- CloudEvents type: `tl.core.Document.CurrentRevisionChanged.v1`
- Ledger payload class: `DocumentCurrentRevisionChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `current_revision_class` | string or null | no | Its status class. |
| `current_revision_code` | string or null | no | Its revision code. |
| `current_revision_id` | string or null | no | Record id of the new current revision; null when none. |
| `current_revision_issued_on` | string or null | no | ISO date it was issued. |
| `current_revision_status` | string or null | no | Its issue status. |
| `previous_revision_id` | string or null | no | Record id of the revision that was current before. |
| `reason` | string | yes | Why: issued, superseded, voided. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "current_revision_class": "construction",
      "current_revision_code": "B",
      "current_revision_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "current_revision_issued_on": "2026-10-13",
      "current_revision_status": "IFC",
      "previous_revision_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reason": "issued"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Document.CurrentRevisionChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Document.CurrentRevisionChanged.v1"
}
```

## Document.Defined

A document was registered under its number.

- CloudEvents type: `tl.core.Document.Defined.v1`
- Ledger payload class: `DocumentDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `confidentiality` | string or null | no | Confidentiality class label. |
| `discipline` | string or null | no | Discipline code. |
| `doc_type` | string or null | no | Document type code. |
| `number` | string | yes | The document number. |
| `originator` | string or null | no | Who produced the document. |
| `pattern_code` | string or null | no | Code of the numbering pattern the number was checked against. |
| `revision_scheme` | string | yes | Code of the revision scheme. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "confidentiality": "internal",
      "discipline": "PIP",
      "doc_type": "ISO",
      "number": "ISO-1234",
      "originator": "Acme Engineering",
      "pattern_code": "document",
      "revision_scheme": "alpha"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Document.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Document.Defined.v1"
}
```

## Document.Superseded

A document was replaced by another document; it stays in the ledger and its links go stale.

- CloudEvents type: `tl.core.Document.Superseded.v1`
- Ledger payload class: `DocumentSupersededPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |
| `superseded_by` | string | yes | Record id of the document that replaces this one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Merged into the new isometric set",
      "superseded_by": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Document.Superseded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Document.Superseded.v1"
}
```

## Document.Updated

The register fields of a document changed (the title changes through the core `Record.Updated`).

- CloudEvents type: `tl.core.Document.Updated.v1`
- Ledger payload class: `DocumentUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string or null | no | Why it changed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "discipline": [
        "MEC",
        "PIP"
      ]
    },
    "detail": {
      "changes": {
        "discipline": [
          "MEC",
          "PIP"
        ]
      },
      "reason": "Moved to the piping group"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Document.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Document.Updated.v1"
}
```

## DocumentSchema.Defined

A version of a document schema was registered.

- CloudEvents type: `tl.core.DocumentSchema.Defined.v1`
- Ledger payload class: `DocumentSchemaDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | The schema's name. |
| `content_hash` | string | yes | Hex SHA-256 of the canonical schema and mapping. |
| `doc_types` | any | no | Document type codes it applies to; empty means any. |
| `json_schema` | any | yes |  |
| `key_column` | string or null | no | The column that identifies a row. |
| `mapping` | any | no | The publish mapping, or null. |
| `mapping_notes` | string or null | no | Notes. |
| `ordinal` | integer | yes | Position among the versions of the code in the scope, from 1. |
| `sample` | any | no | Example rows. |
| `semver` | string | yes | Semantic version `major.minor.patch`. |
| `target_kind` | string or null | no | tags, documents or null. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "instrument-index",
      "content_hash": "0000000000000000000000000000000000000000000000000000000000000000",
      "doc_types": [
        "IDX"
      ],
      "json_schema": {
        "properties": {
          "tag": {
            "type": "string"
          }
        },
        "required": [
          "tag"
        ],
        "type": "object"
      },
      "key_column": "tag",
      "mapping": null,
      "mapping_notes": null,
      "ordinal": 1,
      "sample": [
        {
          "tag": "47-FV-1001"
        }
      ],
      "semver": "1.0.0",
      "target_kind": "tags"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/DocumentSchema.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.DocumentSchema.Defined.v1"
}
```

## DocumentSchema.Retired

A version of a document schema was retired; documents that named it keep it.

- CloudEvents type: `tl.core.DocumentSchema.Retired.v1`
- Ledger payload class: `DocumentSchemaRetiredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Replaced by 1.1.0"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/DocumentSchema.Retired/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.DocumentSchema.Retired.v1"
}
```

## Enricher.Disabled

An enricher was switched off.

- CloudEvents type: `tl.core.Enricher.Disabled.v1`
- Ledger payload class: `EnricherDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `enricher_id` | string | yes | Enricher id. |
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "enricher_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P13",
      "reason": "wrong labels"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Enricher.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Enricher.Disabled.v1"
}
```

## Enricher.Enabled

An enricher was switched on.

- CloudEvents type: `tl.core.Enricher.Enabled.v1`
- Ledger payload class: `EnricherEnabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `enricher_id` | string | yes | Enricher id. |
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "enricher_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P13",
      "reason": "after evaluation"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Enricher.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Enricher.Enabled.v1"
}
```

## Enricher.Registered

An enricher was registered. It starts disabled.

- CloudEvents type: `tl.core.Enricher.Registered.v1`
- Ledger payload class: `EnricherRegisteredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `access` | string | yes | user or controller. |
| `code_version` | string | yes | The plugin's own version. |
| `enabled` | boolean or null | no | Whether it runs. |
| `enricher_id` | string | yes | Enricher id. |
| `integration_app` | string or null | no | Integration app name. |
| `model_ref` | string or null | no | Null for a deterministic enricher. |
| `name` | string | yes | Enricher name; one path segment of the enrich. layer. |
| `owner` | string | yes | Owner actor. |
| `properties` | any | yes |  |
| `service_actor` | string | yes | svc:enricher-<slug>. |
| `version` | integer | yes | Registration version. |
| `when` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "access": "user",
      "code_version": "1.0.0",
      "enabled": false,
      "enricher_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P13",
      "integration_app": null,
      "model_ref": null,
      "name": "doc_classifier",
      "owner": "user:jsmith",
      "properties": [
        {
          "kind": "string",
          "name": "doc_type",
          "policy": "propose",
          "threshold": 0.9
        }
      ],
      "service_actor": "svc:enricher-doc-classifier",
      "version": 1,
      "when": {
        "event_types": [
          "File.Processed"
        ]
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Enricher.Registered/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Enricher.Registered.v1"
}
```

## Enricher.Revised

An enricher's registration changed; the event carries the whole new registration.

- CloudEvents type: `tl.core.Enricher.Revised.v1`
- Ledger payload class: `EnricherRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `enricher` | any | yes |  |
| `enricher_id` | string | yes | Enricher id. |
| `reason` | string | yes | Why. |
| `version` | integer | yes | The new registration version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "enricher": {
        "name": "doc_classifier",
        "version": 2
      },
      "enricher_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P13",
      "reason": "auto-accept above 0.95",
      "version": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Enricher.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Enricher.Revised.v1"
}
```

## Enrichment.Accepted

A person (or the enricher's own auto policy) accepted a value: it is now written to the enricher's layer of the record.

- CloudEvents type: `tl.core.Enrichment.Accepted.v1`
- Ledger payload class: `EnrichmentAcceptedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `automatic` | boolean | yes | True for the auto policy. |
| `by` | string | yes | The accepting person, or the enricher's service actor. |
| `value_id` | string | yes | Value id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "automatic": false,
      "by": "user:mlee",
      "value_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P14"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Enrichment.Accepted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Enrichment.Accepted.v1"
}
```

## Enrichment.Proposed

An enricher proposed a value for a property of its own layer of a record. A shadow value is for evaluation and admins only.

- CloudEvents type: `tl.core.Enrichment.Proposed.v1`
- Ledger payload class: `EnrichmentProposedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `acceptance_state` | string | yes | shadow or proposed. |
| `confidence` | number | yes | 0 to 1. |
| `enricher` | string | yes | Enricher name. |
| `enricher_version` | string | yes | The plugin's version. |
| `inputs` | any | yes |  |
| `model_ref` | string or null | no | Null for a deterministic enricher. |
| `produced_at` | string | yes | ISO-8601 time. |
| `property_path` | string | yes | enrich.<enricher>.<property>. |
| `target` | any | yes |  |
| `value` | any | no | A scalar or a list of scalars. |
| `value_id` | string | yes | Value id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "acceptance_state": "proposed",
      "confidence": 0.9,
      "enricher": "doc_classifier",
      "enricher_version": "1.0.0",
      "inputs": [
        {
          "file_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
          "record": {
            "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
            "key": "ISD-001",
            "record_type": "documents.Document",
            "version": 4
          }
        }
      ],
      "model_ref": null,
      "produced_at": "2026-10-17T03:14:07.000000Z",
      "property_path": "enrich.doc_classifier.doc_type",
      "target": {
        "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
        "key": "ISD-001",
        "record_type": "documents.Document",
        "version": 4
      },
      "value": "ISO",
      "value_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P14"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Enrichment.Proposed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Enrichment.Proposed.v1"
}
```

## Enrichment.Rejected

A value was rejected by a person, or replaced by a newer proposal.

- CloudEvents type: `tl.core.Enrichment.Rejected.v1`
- Ledger payload class: `EnrichmentRejectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes | The person, or the enricher's service actor for a replacement. |
| `reason` | string | yes | Why. |
| `value_id` | string | yes | Value id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:mlee",
      "reason": "wrong type",
      "value_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P14"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Enrichment.Rejected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Enrichment.Rejected.v1"
}
```

## Feed.Edited

A post was edited. The payload is a full replacement of the body and its tags; the earlier text stays in the ledger, so edits are visible history (brief 21.1).

- CloudEvents type: `tl.core.Feed.Edited.v1`
- Ledger payload class: `FeedEditedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `body` | string | yes |  |
| `post_id` | string | yes |  |
| `record_ids` | array or null | no |  |
| `tags` | array or null | no |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "body": "Spool arrived, bevels damaged",
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_ids": [],
      "tags": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Feed.Edited/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Edited.v1"
}
```

## Feed.Posted

A post was made in a project feed. It is the first event of the post stream. The projection derives the effective importance from `importance` and the tags.

- CloudEvents type: `tl.core.Feed.Posted.v1`
- Ledger payload class: `FeedPostedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `author` | string | yes | Actor that posted. |
| `body` | string | yes | Text of the post. |
| `importance` | string | yes | Importance the author gave. The projection derives the effective level from it and the tags. |
| `post_id` | string | yes |  |
| `record_ids` | array or null | no | Records the post references, without repeats. |
| `tags` | array or null | no | Tags found in the body, after resolution. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "author": "user:mlee",
      "body": "Spool arrived #P123-REC-0003 #hold",
      "importance": "normal",
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_ids": [
        "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
      ],
      "tags": [
        {
          "end": 28,
          "kind": "record",
          "namespace": null,
          "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
          "start": 14,
          "text": "P123-REC-0003"
        },
        {
          "end": 34,
          "kind": "signal",
          "namespace": null,
          "record_id": null,
          "start": 29,
          "text": "hold"
        }
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Feed.Posted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Posted.v1"
}
```

## Feed.Reacted

A reaction was set or cleared on a post. The actor of the event sets (`on` true) or clears (`on` false) one acknowledgement. Reactions are limited to `ack`, `+1` and `resolved` (brief 21.1).

- CloudEvents type: `tl.core.Feed.Reacted.v1`
- Ledger payload class: `FeedReactedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `on` | boolean | yes | True to set the reaction, false to clear it. |
| `post_id` | string | yes |  |
| `reaction` | string | yes | One of `ack`, `+1`, `resolved`. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "on": true,
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reaction": "ack"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Feed.Reacted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Reacted.v1"
}
```

## Feed.Retracted

A post was retracted. The projection keeps a tombstone row and drops the body.

- CloudEvents type: `tl.core.Feed.Retracted.v1`
- Ledger payload class: `FeedRetractedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `post_id` | string | yes |  |
| `reason` | string | yes | Why the post was retracted. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "post_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reason": "Wrong project"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Feed.Retracted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Feed.Retracted.v1"
}
```

## File.Processed

A file passed its scan and is available.

- CloudEvents type: `tl.core.File.Processed.v1`
- Ledger payload class: `FileProcessedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `file_id` | string | yes | File id. |
| `report` | any | no | Scan report. |
| `status` | string or null | no | available. |
| `supersedes` | any | no | Ids of the files this one replaced in a single-file slot. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "report": {
        "scanner": "stub"
      },
      "status": "available",
      "supersedes": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/File.Processed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.File.Processed.v1"
}
```

## File.Rejected

A file failed its scan and was rejected.

- CloudEvents type: `tl.core.File.Rejected.v1`
- Ledger payload class: `FileRejectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `file_id` | string | yes | File id. |
| `reason` | string | yes | Why it was rejected. |
| `report` | any | no | Scan report. |
| `status` | string or null | no | rejected. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "reason": "malware signature",
      "report": {
        "scanner": "stub"
      },
      "status": "rejected"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/File.Rejected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.File.Rejected.v1"
}
```

## File.Uploaded

A file was uploaded and attached to a record; it is quarantined until its scan finishes.

- CloudEvents type: `tl.core.File.Uploaded.v1`
- Ledger payload class: `FileUploadedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_type` | string | yes | Media type. |
| `deduplicated` | boolean or null | no | True when the bytes already existed. |
| `file_id` | string | yes | File id. |
| `filename` | string | yes | Original file name. |
| `record_id` | string | yes | The record the file is attached to. |
| `revision` | integer or null | no | Position in the slot. |
| `sha256` | string | yes | SHA-256 of the bytes. |
| `size` | integer | yes | Size in bytes. |
| `slot` | string or null | no | File slot; null for a generic attachment. |
| `status` | string or null | no | quarantined. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_type": "application/pdf",
      "deduplicated": false,
      "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "filename": "mtr.pdf",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "revision": 1,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "size": 1024,
      "slot": "mtr",
      "status": "quarantined"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/File.Uploaded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.File.Uploaded.v1"
}
```

## Inbound.Applied

A delivery was mapped and its commands ran (or, for a dry-run endpoint, were planned).

- CloudEvents type: `tl.core.Inbound.Applied.v1`
- Ledger payload class: `InboundAppliedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `command_count` | integer | yes | Commands run or planned. |
| `delivery_id` | string | yes | Delivery id. |
| `dry_run` | boolean | yes | True when nothing ran. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "command_count": 2,
      "delivery_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P12",
      "dry_run": false
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Inbound.Applied/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Inbound.Applied.v1"
}
```

## Inbound.Failed

A delivery could not be applied; it is in the error queue until an admin retries it.

- CloudEvents type: `tl.core.Inbound.Failed.v1`
- Ledger payload class: `InboundFailedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | A fixed code. |
| `delivery_id` | string | yes | Delivery id. |
| `message` | string | yes | A bounded message; never a payload excerpt. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "key_not_found",
      "delivery_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P12",
      "message": "No record has the key 47-1234-W099."
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Inbound.Failed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Inbound.Failed.v1"
}
```

## Inbound.Received

A signed POST was accepted and queued for mapping. The payload and the headers are not in the event.

- CloudEvents type: `tl.core.Inbound.Received.v1`
- Ledger payload class: `InboundReceivedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `delivery_id` | string | yes | Delivery id. |
| `endpoint_id` | string | yes | Endpoint id. |
| `endpoint_version` | integer | yes | The endpoint version it will be mapped by. |
| `payload_sha256` | string | yes | SHA-256 of the raw body. |
| `payload_size` | integer | yes | Body size in bytes. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "delivery_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P12",
      "endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "endpoint_version": 2,
      "payload_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "payload_size": 412
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Inbound.Received/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Inbound.Received.v1"
}
```

## Inbound.Retried

An admin re-ran a failed delivery, optionally with a corrected payload.

- CloudEvents type: `tl.core.Inbound.Retried.v1`
- Ledger payload class: `InboundRetriedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes | The admin. |
| `corrected_sha256` | string or null | no | SHA-256 of the corrected body, when one was supplied. |
| `delivery_id` | string | yes | Delivery id. |
| `original_sha256` | string | yes | SHA-256 of the received body. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:jsmith",
      "corrected_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
      "delivery_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P12",
      "original_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Inbound.Retried/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Inbound.Retried.v1"
}
```

## InboundEndpoint.Created

An inbound endpoint was created. It starts disabled and in dry-run mode. Its secret is held outside the ledger.

- CloudEvents type: `tl.core.InboundEndpoint.Created.v1`
- Ledger payload class: `InboundEndpointCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `access` | string | yes | user or controller. |
| `allowed_commands` | any | yes |  |
| `app` | string | yes | Integration app name. |
| `auth` | string | yes | hmac_sha256 or jwt_hs256. |
| `dry_run` | boolean or null | no | Verify, map and plan only. |
| `enabled` | boolean or null | no | Whether it accepts deliveries. |
| `endpoint_id` | string | yes | Endpoint id. |
| `external_schema` | string or null | no | Which external schema the mapping reads. |
| `mapping` | string | yes | Restricted JSONata expression. |
| `mapping_language` | string | yes | jsonata-restricted@1. |
| `max_body_bytes` | integer | yes | Body cap. |
| `name` | string | yes | Endpoint name (slug). |
| `owner` | string | yes | Owner actor. |
| `rate_per_minute` | integer | yes | Rate bound. |
| `secret_id` | string | yes | Id of the first secret (not the secret). |
| `service_actor` | string | yes | svc:inbound-<app>.<endpoint>. |
| `version` | integer | yes | Endpoint version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "access": "user",
      "allowed_commands": [
        "SetPsetValues"
      ],
      "app": "acme-nde",
      "auth": "hmac_sha256",
      "dry_run": true,
      "enabled": false,
      "endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "external_schema": null,
      "mapping": "results.{\"command\": \"SetPsetValues\", \"args\": {\"stream_id\": {\"$key\": weld}, \"pset\": \"nde\", \"values\": {\"result\": result}}}",
      "mapping_language": "jsonata-restricted@1",
      "max_body_bytes": 262144,
      "name": "results",
      "owner": "user:jsmith",
      "rate_per_minute": 60,
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P10",
      "service_actor": "svc:inbound-acme-nde.results",
      "version": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/InboundEndpoint.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.InboundEndpoint.Created.v1"
}
```

## InboundEndpoint.Disabled

An endpoint stopped accepting deliveries; it answers 404.

- CloudEvents type: `tl.core.InboundEndpoint.Disabled.v1`
- Ledger payload class: `InboundEndpointDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `endpoint_id` | string | yes | Endpoint id. |
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "reason": "key leaked"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/InboundEndpoint.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.InboundEndpoint.Disabled.v1"
}
```

## InboundEndpoint.Enabled

An endpoint started accepting deliveries.

- CloudEvents type: `tl.core.InboundEndpoint.Enabled.v1`
- Ledger payload class: `InboundEndpointEnabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `endpoint_id` | string | yes | Endpoint id. |
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "reason": "go live"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/InboundEndpoint.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.InboundEndpoint.Enabled.v1"
}
```

## InboundEndpoint.Revised

An endpoint was revised; the event carries the whole new definition (no secret).

- CloudEvents type: `tl.core.InboundEndpoint.Revised.v1`
- Ledger payload class: `InboundEndpointRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `endpoint` | any | yes |  |
| `endpoint_id` | string | yes | Endpoint id. |
| `reason` | string | yes | Why. |
| `version` | integer | yes | The new endpoint version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "endpoint": {
        "dry_run": false,
        "name": "results",
        "version": 2
      },
      "endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "reason": "go live",
      "version": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/InboundEndpoint.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.InboundEndpoint.Revised.v1"
}
```

## InboundEndpoint.SecretRotated

A new secret was issued; the previous one keeps verifying until the overlap ends (at most 24 hours).

- CloudEvents type: `tl.core.InboundEndpoint.SecretRotated.v1`
- Ledger payload class: `InboundEndpointSecretRotatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `endpoint_id` | string | yes | Endpoint id. |
| `previous_expires_at` | string or null | no | ISO-8601 time when the previous secret stops. |
| `previous_secret_id` | string or null | no | Id of the secret being replaced. |
| `secret_id` | string | yes | Id of the new secret (not the secret). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "endpoint_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "previous_expires_at": "2026-10-18T03:14:07.000000Z",
      "previous_secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P10",
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P11"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/InboundEndpoint.SecretRotated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.InboundEndpoint.SecretRotated.v1"
}
```

## IntegrationApp.Disabled

An app was switched off: its endpoints answer 404 and its rules, actions and enrichers do nothing.

- CloudEvents type: `tl.core.IntegrationApp.Disabled.v1`
- Ledger payload class: `IntegrationAppDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "contractor offboarded"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/IntegrationApp.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.IntegrationApp.Disabled.v1"
}
```

## IntegrationApp.Enabled

An app was switched on: its endpoints, rules, actions and enrichers run again.

- CloudEvents type: `tl.core.IntegrationApp.Enabled.v1`
- Ledger payload class: `IntegrationAppEnabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "contract renewed"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/IntegrationApp.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.IntegrationApp.Enabled.v1"
}
```

## IntegrationApp.Registered

An integration app was registered. Its name is the first segment of its inbound paths.

- CloudEvents type: `tl.core.IntegrationApp.Registered.v1`
- Ledger payload class: `IntegrationAppRegisteredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `app_id` | string | yes | App id. |
| `description` | string or null | no | Description. |
| `enabled` | boolean or null | no | Whether its endpoints, rules, actions and enrichers run. |
| `label` | string | yes | Label. |
| `name` | string | yes | Slug, unique across the ledger. |
| `owner` | string | yes | Owner actor. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "app_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P1",
      "description": "Results from the NDE contractor",
      "enabled": true,
      "label": "Acme NDE",
      "name": "acme-nde",
      "owner": "user:jsmith"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/IntegrationApp.Registered/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.IntegrationApp.Registered.v1"
}
```

## IntegrationApp.Revised

An app's label, description or owner changed.

- CloudEvents type: `tl.core.IntegrationApp.Revised.v1`
- Ledger payload class: `IntegrationAppRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "changes": {
        "label": [
          "Acme NDE",
          "Acme NDE results"
        ]
      },
      "reason": "renamed"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/IntegrationApp.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.IntegrationApp.Revised.v1"
}
```

## Link.Accepted

A suggested link was accepted and is now active.

- CloudEvents type: `tl.core.Link.Accepted.v1`
- Ledger payload class: `LinkAcceptedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `note` | string or null | no | Free-text note. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "note": "Confirmed on site"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Accepted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Accepted.v1"
}
```

## Link.Added

A link between two records became active.

- CloudEvents type: `tl.core.Link.Added.v1`
- Ledger payload class: `LinkAddedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `confidence` | number or null | no | Confidence of a suggested link, 0 to 1. |
| `from_ref` | string | yes | Record id at the start of the link. |
| `note` | string or null | no | Free-text note. |
| `pin` | string or null | no | Revision the link is pinned to; null for a floating link. |
| `relation` | string | yes | Relation code. |
| `source` | string or null | no | Who or what made the link: manual, rule, ai or import. |
| `to_ref` | string | yes | Record id at the end of the link. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "confidence": null,
      "from_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "note": null,
      "pin": null,
      "relation": "raised_against",
      "source": "manual",
      "to_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [
      {
        "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
        "rel": "raised_against"
      }
    ],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Added/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Added.v1"
}
```

## Link.Declined

A suggested link was declined; it will not be suggested again.

- CloudEvents type: `tl.core.Link.Declined.v1`
- Ledger payload class: `LinkDeclinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why it was declined. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Different valve"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Declined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Declined.v1"
}
```

## Link.Flagged

A link was flagged stale or broken.

- CloudEvents type: `tl.core.Link.Flagged.v1`
- Ledger payload class: `LinkFlaggedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why it was flagged. |
| `status` | string | yes | stale or broken. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "revision B issued",
      "status": "stale"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Flagged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Flagged.v1"
}
```

## Link.Repinned

The pin of a link was set to another revision.

- CloudEvents type: `tl.core.Link.Repinned.v1`
- Ledger payload class: `LinkRepinnedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `pin` | string or null | no | The new pin; null makes the link floating. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "pin": "B"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Repinned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Repinned.v1"
}
```

## Link.Retracted

A link was retracted. Its row and history stay.

- CloudEvents type: `tl.core.Link.Retracted.v1`
- Ledger payload class: `LinkRetractedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why it was retracted. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Wrong record"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Retracted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Retracted.v1"
}
```

## Link.Suggested

A link was suggested and waits for a person to accept or decline.

- CloudEvents type: `tl.core.Link.Suggested.v1`
- Ledger payload class: `LinkSuggestedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `confidence` | number or null | no | Confidence, 0 to 1. |
| `from_ref` | string | yes | Record id at the start of the link. |
| `note` | string or null | no | Free-text note. |
| `pin` | string or null | no | Revision the link is pinned to. |
| `relation` | string | yes | Relation code. |
| `source` | string or null | no | Origin of the suggestion: rule, ai or import. |
| `to_ref` | string | yes | Record id at the end of the link. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "confidence": 0.82,
      "from_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "note": null,
      "pin": null,
      "relation": "references",
      "source": "ai",
      "to_ref": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [
      {
        "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
        "rel": "references"
      }
    ],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Suggested/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Suggested.v1"
}
```

## Link.Verified

A person verified an active link.

- CloudEvents type: `tl.core.Link.Verified.v1`
- Ledger payload class: `LinkVerifiedPayload`
- Version: 1

### Payload fields

No fields.

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {},
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Link.Verified/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Link.Verified.v1"
}
```

## LoadRun.Bronzed

The rows were copied, as they are, to the lake bronze table of the system and table. Every reader of the lake can read the copy, so this is a step of its own that an administrator takes.

- CloudEvents type: `tl.core.LoadRun.Bronzed.v1`
- Ledger payload class: `LoadRunBronzedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `bronze_rows` | integer | yes | Rows written to the lake bronze table. |
| `include_confidential` | boolean or null | no | True: the administrator said the copy may hold rows of confidential records. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "bronze_rows": 40
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Bronzed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Bronzed.v1"
}
```

## LoadRun.Compensated

The records the load created were taken back, by the ids the load recorded.

- CloudEvents type: `tl.core.LoadRun.Compensated.v1`
- Ledger payload class: `LoadRunCompensatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `correlation_id` | string | yes | The correlation id of the compensation. |
| `reversed` | integer | yes | Records reversed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "correlation_id": "load:01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "reversed": 39
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Compensated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Compensated.v1"
}
```

## LoadRun.Extracted

The rows of the file were read in the resource envelope and stored.

- CloudEvents type: `tl.core.LoadRun.Extracted.v1`
- Ledger payload class: `LoadRunExtractedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `column_count` | integer | yes | Columns. |
| `extracted_file_id` | string | yes | The stored rows. |
| `extracted_sha256` | string | yes | SHA-256 of the stored rows. |
| `extractor` | string | yes | The extractor that read the file. |
| `row_count` | integer | yes | Data rows. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "column_count": 8,
      "extracted_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P1",
      "extracted_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
      "extractor": "tabular",
      "row_count": 40
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Extracted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Extracted.v1"
}
```

## LoadRun.Failed

A stage failed; the run stays in its state and says why (fixed text, no value of the file).

- CloudEvents type: `tl.core.LoadRun.Failed.v1`
- Ledger payload class: `LoadRunFailedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | A fixed code. |
| `message` | string | yes | Fixed text. |
| `stage` | string | yes | extract, profile, plan, load or reconcile. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "extraction_limit",
      "message": "The file is too large or too complex to read.",
      "stage": "extract"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Failed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Failed.v1"
}
```

## LoadRun.Loaded

The load wrote records through the module commands, as one correlated batch.

- CloudEvents type: `tl.core.LoadRun.Loaded.v1`
- Ledger payload class: `LoadRunLoadedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `correlation_id` | string | yes | The correlation id of the load. |
| `loaded_count` | integer | yes | Records created. |
| `record_ids` | array | yes | Ids of the records created, in file order. |
| `skipped_existing` | integer | yes | Rows left alone because their key exists. |
| `skipped_invalid` | integer | yes | Rows left out because they cannot be loaded. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "correlation_id": "load:01J9Z6Q4W3X2Y1V0T9S8R7Q6P3",
      "loaded_count": 1,
      "record_ids": [
        "01J9Z6Q4W3X2Y1V0T9S8R7Q6P4"
      ],
      "skipped_existing": 0,
      "skipped_invalid": 0
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Loaded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Loaded.v1"
}
```

## LoadRun.Opened

A load run was opened for a file.

- CloudEvents type: `tl.core.LoadRun.Opened.v1`
- Ledger payload class: `LoadRunOpenedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `confidentiality` | string or null | no | The class of the run: internal or restricted. |
| `loader` | string | yes | The loader. |
| `opened_by` | string | yes | The administrator. |
| `run_number` | integer | yes | The number of the run. |
| `source_name` | string or null | no | Display name of the file. |
| `source_sha256` | string or null | no | SHA-256 of the file. |
| `source_size` | integer or null | no | Size of the file in bytes. |
| `source_system` | string | yes | The legacy system. |
| `source_table` | string | yes | The table or list. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "loader": "dms-register",
      "opened_by": "user:admin",
      "run_number": 1,
      "source_name": "register.csv",
      "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "source_size": 1200,
      "source_system": "dms",
      "source_table": "register"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Opened/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Opened.v1"
}
```

## LoadRun.Planned

The rows were mapped and a dry run counted what a load would do.

- CloudEvents type: `tl.core.LoadRun.Planned.v1`
- Ledger payload class: `LoadRunPlannedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `mapping_name` | string | yes | The mapping template. |
| `mapping_sha256` | string | yes | SHA-256 of the mapping template text. |
| `plan_existing` | integer | yes | Rows whose key exists. |
| `plan_invalid` | integer | yes | Rows that cannot be loaded. |
| `plan_new` | integer | yes | Rows that would be created. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "mapping_name": "dms-register",
      "mapping_sha256": "3333333333333333333333333333333333333333333333333333333333333333",
      "plan_existing": 0,
      "plan_invalid": 1,
      "plan_new": 39
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Planned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Planned.v1"
}
```

## LoadRun.Profiled

The rows were profiled: columns, value shapes, keys and repeats.

- CloudEvents type: `tl.core.LoadRun.Profiled.v1`
- Ledger payload class: `LoadRunProfiledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `profile_file_id` | string | yes | The stored profile. |
| `profile_sha256` | string | yes | SHA-256 of the stored profile. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "profile_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2",
      "profile_sha256": "2222222222222222222222222222222222222222222222222222222222222222"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Profiled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Profiled.v1"
}
```

## LoadRun.Reconciled

The load was compared with the file; the report is stored and registered as a document.

- CloudEvents type: `tl.core.LoadRun.Reconciled.v1`
- Ledger payload class: `LoadRunReconciledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `mismatches` | integer | yes | Differences found. |
| `report_document_id` | string or null | no | The document that registers the report. |
| `report_file_id` | string | yes | The stored report. |
| `report_sha256` | string | yes | SHA-256 of the stored report. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "mismatches": 0,
      "report_document_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "report_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "report_sha256": "4444444444444444444444444444444444444444444444444444444444444444"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Reconciled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Reconciled.v1"
}
```

## LoadRun.Voided

The run was abandoned before it loaded anything.

- CloudEvents type: `tl.core.LoadRun.Voided.v1`
- Ledger payload class: `LoadRunVoidedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Wrong file."
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/LoadRun.Voided/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.LoadRun.Voided.v1"
}
```

## Numbering.Allocated

A number was allocated from a counter.

- CloudEvents type: `tl.core.Numbering.Allocated.v1`
- Ledger payload class: `NumberingAllocatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `key` | string | yes | The key built. |
| `pattern` | string | yes | Numbering pattern id. |
| `prefix` | string or null | no | The key without its sequence. |
| `record_id` | string or null | no | The record the number was allocated for. |
| `record_type` | string or null | no | Record type. |
| `sequence` | integer | yes | The sequence number. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "key": "P123-REC-0001",
      "pattern": "rec",
      "prefix": "P123-REC-",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_type": "core.Record",
      "sequence": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Numbering.Allocated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Numbering.Allocated.v1"
}
```

## Party.ContactAdded

A contact was added to a party.

- CloudEvents type: `tl.core.Party.ContactAdded.v1`
- Ledger payload class: `PartyContactAddedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `domain` | string or null | no | Domain code; null for every domain. |
| `email` | string or null | no | Lower-case email. |
| `is_authorised` | boolean | yes | True for an authorised representative. |
| `name` | string | yes | The person's name. |
| `position` | integer | yes | Position among the party's contacts. |
| `title` | string or null | no | Job title. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "domain": null,
      "email": "lee@meridian.example",
      "is_authorised": false,
      "name": "Lee Wong",
      "position": 2,
      "title": "Planner"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Party.ContactAdded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Party.ContactAdded.v1"
}
```

## Party.ContactEnded

A contact was ended.

- CloudEvents type: `tl.core.Party.ContactEnded.v1`
- Ledger payload class: `PartyContactEndedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `position` | integer | yes | Position of the contact. |
| `reason` | string or null | no | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "position": 2,
      "reason": "Left the project"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Party.ContactEnded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Party.ContactEnded.v1"
}
```

## Party.Defined

A party was entered, with its first contacts.

- CloudEvents type: `tl.core.Party.Defined.v1`
- Ledger payload class: `PartyDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | The party code. |
| `contacts` | any | yes |  |
| `email_domains` | any | yes |  |
| `project_role` | string | yes | client, engineer, contractor, subcontractor, supplier, authority, internal or other. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "CLIENT",
      "contacts": [
        {
          "domain": null,
          "email": "pm@meridian.example",
          "is_authorised": true,
          "name": "Dana Cole",
          "title": "Project manager"
        }
      ],
      "email_domains": [
        "meridian.example"
      ],
      "project_role": "client"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Party.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Party.Defined.v1"
}
```

## Party.Retired

A party was retired.

- CloudEvents type: `tl.core.Party.Retired.v1`
- Ledger payload class: `PartyRetiredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Contract complete"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Party.Retired/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Party.Retired.v1"
}
```

## ProcessingJob.Cancelled

A queued job was cancelled before a worker took it.

- CloudEvents type: `tl.core.ProcessingJob.Cancelled.v1`
- Ledger payload class: `ProcessingJobCancelledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Wrong file"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ProcessingJob.Cancelled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ProcessingJob.Cancelled.v1"
}
```

## ProcessingJob.Defined

A processing job was queued.

- CloudEvents type: `tl.core.ProcessingJob.Defined.v1`
- Ledger payload class: `ProcessingJobDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `derived_id` | string | yes | Record id of the derived document. |
| `derived_key` | string | yes | Its key. |
| `extractor` | string or null | no | The extractor asked for, or null. |
| `kind` | string | yes | extract or validate. |
| `max_attempts` | integer | yes | Claims allowed. |
| `options` | any | no | Extractor options. |
| `requested_by` | string | yes | The actor who asked. |
| `schema_id` | string | yes | Record id of the schema version. |
| `source_file_id` | string or null | no | The file to read. |
| `source_ref` | string | yes | The provenance string. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "derived_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PD",
      "derived_key": "ISD-001@A/instrument-index",
      "extractor": null,
      "kind": "extract",
      "max_attempts": 3,
      "options": {},
      "requested_by": "user:demo",
      "schema_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "source_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
      "source_ref": "src.doc.ISD-001@A"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ProcessingJob.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ProcessingJob.Defined.v1"
}
```

## ProcessingJob.Failed

The claimed attempt failed. When `final` is false the job is queued again at `retry_at`.

- CloudEvents type: `tl.core.ProcessingJob.Failed.v1`
- Ledger payload class: `ProcessingJobFailedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | The attempt that failed. |
| `error_code` | string | yes | Short code. |
| `error_message` | string | yes | What went wrong, in words, without paths or stack traces. |
| `final` | boolean | yes | True when no attempt is left. |
| `retry_at` | string or null | no | ISO-8601 UTC of the next attempt when not final. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 1,
      "error_code": "source_not_available",
      "error_message": "the file is still in quarantine",
      "final": false,
      "retry_at": "2026-10-17T10:01:00.000000Z"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ProcessingJob.Failed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ProcessingJob.Failed.v1"
}
```

## ProcessingJob.Started

A worker claimed a job (attempt n).

- CloudEvents type: `tl.core.ProcessingJob.Started.v1`
- Ledger payload class: `ProcessingJobStartedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | The claim number, from 1. |
| `lease_until` | string | yes | ISO-8601 UTC at which the claim expires. |
| `worker` | string | yes | The worker that holds the claim. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 1,
      "lease_until": "2026-10-17T10:05:00.000000Z",
      "worker": "worker-1"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ProcessingJob.Started/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ProcessingJob.Started.v1"
}
```

## ProcessingJob.Succeeded

The claimed attempt finished and its results were recorded.

- CloudEvents type: `tl.core.ProcessingJob.Succeeded.v1`
- Ledger payload class: `ProcessingJobSucceededPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | The attempt that finished. |
| `result` | any | no | A small summary: extraction status, rows, content revision, validation status. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 1,
      "result": {
        "content_rev": 1,
        "extraction_status": "ok",
        "rows": 40,
        "validation_status": "valid"
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ProcessingJob.Succeeded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ProcessingJob.Succeeded.v1"
}
```

## Proposal.Accepted

A person accepted a proposal and its command ran in the same transaction.

- CloudEvents type: `tl.core.Proposal.Accepted.v1`
- Ledger payload class: `ProposalAcceptedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes | The accepting person, `user:<id>`. |
| `proposal_id` | string | yes |  |
| `result_stream_id` | string | yes | Stream the command wrote to (the new record, the changed record, the link). |
| `result_version` | integer | yes | Stream version after the command. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:mlee",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "result_stream_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "result_version": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Proposal.Accepted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Accepted.v1"
}
```

## Proposal.Created

An agent proposed a change. `command` is the command model as the agent built it, with `actor` set to the agent and `source` to `mcp:<agent>`; accepting re-runs it as the accepting person.

- CloudEvents type: `tl.core.Proposal.Created.v1`
- Ledger payload class: `ProposalCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | string | yes | The proposing actor, `agent:<id>`. |
| `command` | any | yes |  |
| `command_type` | string | yes | Name of the command model (`CreateRecord`, `SetPsetValues`, `AddLink`, `TransitionWorkflow`). |
| `proposal_id` | string | yes |  |
| `summary` | string | yes | One line for the review queue. |
| `tool` | string | yes | The MCP tool that was called (`create_record`, `update_psets`, `link_records`, `transition_workflow`). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "agent": "agent:triage",
      "command": {
        "actor": "agent:triage",
        "numbering": {},
        "psets": {},
        "record_type": "core.Record",
        "scope": "project:P123",
        "source": "mcp:triage",
        "title": "Weld NCR"
      },
      "command_type": "CreateRecord",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "summary": "Create record: Weld NCR",
      "tool": "create_record"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Proposal.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Created.v1"
}
```

## Proposal.Failed

A person accepted a proposal, but the command was refused (the record changed since, a guard failed). The command's own writes were rolled back; this event is written in a fresh transaction.

- CloudEvents type: `tl.core.Proposal.Failed.v1`
- Ledger payload class: `ProposalFailedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes |  |
| `error` | string | yes | `<ErrorClass>: <message>` of the refusal. |
| `proposal_id` | string | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:mlee",
      "error": "ConcurrencyError: expected version 3, stream is at 4",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Proposal.Failed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Failed.v1"
}
```

## Proposal.Rejected

A person rejected a proposal. Nothing else was written.

- CloudEvents type: `tl.core.Proposal.Rejected.v1`
- Ledger payload class: `ProposalRejectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes |  |
| `proposal_id` | string | yes |  |
| `reason` | string | yes | Why, for the agent and the audit trail. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "by": "user:mlee",
      "proposal_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reason": "Duplicate of NCR-0042"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Proposal.Rejected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Proposal.Rejected.v1"
}
```

## Pset.ValuesSet

Values of a property set were written on a record.

- CloudEvents type: `tl.core.Pset.ValuesSet.v1`
- Ledger payload class: `PsetValuesSetPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `conformance` | string or null | no | Conformance after the write: ok, warning, nonconformant or waived. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `layer` | string | yes | Pset layer: standard, custom or project. |
| `pset` | string | yes | Property-set name. |
| `units` | any | no | Units of the written properties, when the schema declares them. |
| `values` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "psets.valve_data.size_in": [
        null,
        4
      ]
    },
    "detail": {
      "conformance": "ok",
      "effective_schema_hash": "9f2c",
      "layer": "standard",
      "pset": "valve_data",
      "units": {
        "size_in": "in"
      },
      "values": {
        "size_in": 4
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Pset.ValuesSet/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Pset.ValuesSet.v1"
}
```

## Record.BodyStored

The body of an object-backed record was stored as a content-addressed object. The body itself is never in the ledger. A new body is a new object (a new hash); the old one stays, and `previous_hash` chains the versions.

- CloudEvents type: `tl.core.Record.BodyStored.v1`
- Ledger payload class: `RecordBodyStoredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `pointer` | any | yes |  |
| `previous_hash` | string or null | no | Hash of the body this one replaces; null for the first body. |
| `stream_id` | string | yes | The record (this stream). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "pointer": {
        "hash": "9c1f0e3a5b7d2c4f6a8b0d1e3f5a7c9b2d4f6a8c0e1b3d5f7a9c2e4b6d8f0a1c",
        "schema_hash": "7a3b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b",
        "size": 412,
        "uri": "records/co.acme.LiftPlan/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5/9c1f0e3a5b7d2c4f6a8b0d1e3f5a7c9b2d4f6a8c0e1b3d5f7a9c2e4b6d8f0a1c.json"
      },
      "previous_hash": null,
      "stream_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.BodyStored/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.BodyStored.v1"
}
```

## Record.Corrected

A recorded value was corrected after the fact; history keeps the original.

- CloudEvents type: `tl.core.Record.Corrected.v1`
- Ledger payload class: `RecordCorrectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string | yes | Why it was corrected. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "title": [
        "Gate vlave",
        "Gate valve"
      ]
    },
    "detail": {
      "changes": {
        "title": [
          "Gate vlave",
          "Gate valve"
        ]
      },
      "reason": "Typo"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Corrected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Corrected.v1"
}
```

## Record.Created

A record was created.

- CloudEvents type: `tl.core.Record.Created.v1`
- Ledger payload class: `RecordCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string or null | no | Description. |
| `key` | string or null | no | Human-readable key; null until numbering assigns one. |
| `psets` | any | no | Initial property-set values keyed by pset name. |
| `record_type` | string | yes | Fully qualified record type. |
| `title` | string | yes | Title. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "key": [
        null,
        "P123-REC-0001"
      ],
      "title": [
        null,
        "Gate valve 47-1234"
      ]
    },
    "detail": {
      "description": null,
      "key": "P123-REC-0001",
      "psets": {},
      "record_type": "core.Record",
      "title": "Gate valve 47-1234"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Created.v1"
}
```

## Record.Updated

One or more fields of a record changed.

- CloudEvents type: `tl.core.Record.Updated.v1`
- Ledger payload class: `RecordUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "title": [
        "Gate valve",
        "Gate valve 47-1234"
      ]
    },
    "detail": {
      "changes": {
        "title": [
          "Gate valve",
          "Gate valve 47-1234"
        ]
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Updated.v1"
}
```

## Record.Voided

A record was voided. The record stays in the ledger.

- CloudEvents type: `tl.core.Record.Voided.v1`
- Ledger payload class: `RecordVoidedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why it was voided. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Entered in error"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Record.Voided/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Record.Voided.v1"
}
```

## Rendition.Defined

A file was registered as a rendition of a revision.

- CloudEvents type: `tl.core.Rendition.Defined.v1`
- Ledger payload class: `RenditionDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_type` | string | yes | Media type. |
| `document_id` | string | yes | Record id of the document. |
| `file_id` | string | yes | File id in the file service. |
| `filename` | string | yes | File name. |
| `kind` | string | yes | native, pdf, markup or signed. |
| `page_count` | integer or null | no | Number of pages, when known. |
| `replace_reason` | string or null | no | The admin's reason when a signed copy was registered or replaced; null for every other rendition. |
| `revision_id` | string | yes | Record id of the revision. |
| `sha256` | string | yes | Hex SHA-256 of the bytes. |
| `size` | integer | yes | Size in bytes. |
| `supersedes` | any | no | Record ids of the renditions of the same kind this one replaces. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_type": "application/pdf",
      "document_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "filename": "ISO-1234-A.pdf",
      "kind": "pdf",
      "page_count": 3,
      "revision_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
      "size": 48213,
      "supersedes": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Rendition.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Rendition.Defined.v1"
}
```

## Rendition.Superseded

A rendition was replaced by a newer one of the same kind on the same revision.

- CloudEvents type: `tl.core.Rendition.Superseded.v1`
- Ledger payload class: `RenditionSupersededPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `superseded_by` | string | yes | Record id of the newer rendition. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "superseded_by": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Rendition.Superseded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Rendition.Superseded.v1"
}
```

## ResponseClock.Cancelled

The clock was cancelled: no answer is needed any more.

- CloudEvents type: `tl.core.ResponseClock.Cancelled.v1`
- Ledger payload class: `ResponseClockCancelledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `day` | string | yes | ISO date. |
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "day": "2026-10-25",
      "reason": "Withdrawn by the client"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Cancelled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Cancelled.v1"
}
```

## ResponseClock.Expired

The sweep found a running clock past its due date. A late answer still ends it with `ResponseClock.Met`.

- CloudEvents type: `tl.core.ResponseClock.Expired.v1`
- Ledger payload class: `ResponseClockExpiredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `day` | string | yes | ISO date of the sweep. |
| `days_overdue` | integer | yes | Days past the due date on the clock's own count. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "day": "2026-11-01",
      "days_overdue": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Expired/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Expired.v1"
}
```

## ResponseClock.Met

The clock was met: the answer came in time (or late; the date says which).

- CloudEvents type: `tl.core.ResponseClock.Met.v1`
- Ledger payload class: `ResponseClockMetPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `day` | string | yes | ISO date of the answer. |
| `reason` | string or null | no | How it was met. |
| `response_id` | string or null | no | Record id of the answering item, when there is one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "day": "2026-10-25",
      "reason": null,
      "response_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Met/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Met.v1"
}
```

## ResponseClock.Paused

A clock was paused; the days of the pause do not count.

- CloudEvents type: `tl.core.ResponseClock.Paused.v1`
- Ledger payload class: `ResponseClockPausedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `day` | string | yes | ISO date of the pause. |
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "day": "2026-10-20",
      "reason": "Waiting for the client to send the drawing"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Paused/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Paused.v1"
}
```

## ResponseClock.Restarted

A clock started its count again from a new day zero, with the same parameters.

- CloudEvents type: `tl.core.ResponseClock.Restarted.v1`
- Ledger payload class: `ResponseClockRestartedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `due_on` | string | yes | The new due date. |
| `reason` | string | yes | Why. |
| `start_on` | string | yes | ISO date of the new day zero. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "due_on": "2026-11-10",
      "reason": "A revised letter was issued",
      "start_on": "2026-10-27"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Restarted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Restarted.v1"
}
```

## ResponseClock.Resumed

A paused clock ran again; the due date moved by the days of the pause.

- CloudEvents type: `tl.core.ResponseClock.Resumed.v1`
- Ledger payload class: `ResponseClockResumedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `day` | string | yes | ISO date of the resume. |
| `due_on` | string | yes | The new due date. |
| `reason` | string or null | no | Why, when the date is before today. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "day": "2026-10-23",
      "due_on": "2026-11-03",
      "reason": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Resumed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Resumed.v1"
}
```

## ResponseClock.Started

A response clock started. The first event of a clock; it carries every parameter of the count and the due date the engine computed from them and the named calendar version.

- CloudEvents type: `tl.core.ResponseClock.Started.v1`
- Ledger payload class: `ResponseClockStartedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `calendar` | string | yes | Calendar and version, code@version. |
| `clause_id` | string or null | no | Record id of the contract clause. |
| `day_type` | string | yes | calendar or working. |
| `due_on` | string | yes | ISO date the clock expires. |
| `duration_days` | integer | yes | Length in days of the unit. |
| `item_id` | string | yes | Record id of the item. |
| `item_number` | string | yes | Its number. |
| `kind` | string | yes | response_from_them, response_from_us or time_bar. |
| `label` | string | yes | What the clock waits for. |
| `owner` | string or null | no | The actor responsible. |
| `start_on` | string | yes | ISO date of day zero. |
| `trigger` | string | yes | What started it: receipt, issue, triage, awareness (a time bar counted from the day the contractor became aware) or manual. |
| `warn_days` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "calendar": "P123-default@1",
      "clause_id": null,
      "day_type": "calendar",
      "due_on": "2026-10-31",
      "duration_days": 14,
      "item_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "item_number": "P123-COR-0002",
      "kind": "response_from_them",
      "label": "Reply expected",
      "owner": "user:amy",
      "start_on": "2026-10-17",
      "trigger": "issue",
      "warn_days": [
        7,
        3,
        1
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Started/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Started.v1"
}
```

## ResponseClock.Warned

The sweep found a running clock at or inside a warning threshold smaller than the last one raised. The smallest crossed threshold is recorded.

- CloudEvents type: `tl.core.ResponseClock.Warned.v1`
- Ledger payload class: `ResponseClockWarnedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `day` | string | yes | ISO date of the sweep. |
| `days_left` | integer | yes | Days left on the clock's own count when the sweep ran. |
| `level` | integer | yes | The threshold in days that was crossed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "day": "2026-10-28",
      "days_left": 3,
      "level": 3
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ResponseClock.Warned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ResponseClock.Warned.v1"
}
```

## ReviewCycle.Closed

A review cycle was closed with an overall outcome.

- CloudEvents type: `tl.core.ReviewCycle.Closed.v1`
- Ledger payload class: `ReviewCycleClosedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `closed_on` | string | yes | ISO date it was closed. |
| `outcome` | string | yes | approved, approved_with_comments or rejected; withdrawn when nobody answered. |
| `reason` | string or null | no | Why it was closed, when not every reviewer answered or the outcome was stated. |
| `worst_answer` | string or null | no | The worst recorded answer when an admin closed with a milder outcome; null otherwise. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "closed_on": "2026-10-16",
      "outcome": "approved_with_comments",
      "reason": null,
      "worst_answer": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ReviewCycle.Closed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ReviewCycle.Closed.v1"
}
```

## ReviewCycle.Defined

A review of a revision was opened with its reviewers.

- CloudEvents type: `tl.core.ReviewCycle.Defined.v1`
- Ledger payload class: `ReviewCycleDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `document_id` | string | yes | Record id of the document. |
| `due_date` | string or null | no | ISO date by which every reviewer should answer. |
| `opened_on` | string | yes | ISO date the cycle was opened. |
| `reviewers` | any | yes |  |
| `revision_id` | string | yes | Record id of the revision under review. |
| `round` | integer | yes | Review round of the revision, from 1. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "document_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "due_date": "2026-10-20",
      "opened_on": "2026-10-13",
      "reviewers": [
        {
          "due_date": null,
          "reviewer": "user:ana"
        }
      ],
      "revision_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "round": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ReviewCycle.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ReviewCycle.Defined.v1"
}
```

## ReviewCycle.OutcomeRecorded

A reviewer answered.

- CloudEvents type: `tl.core.ReviewCycle.OutcomeRecorded.v1`
- Ledger payload class: `ReviewCycleOutcomeRecordedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `comment` | string or null | no | The reviewer's comment. |
| `outcome` | string | yes | approved, approved_with_comments or rejected. |
| `recorded_by` | string or null | no | The actor who recorded the answer when it was not the reviewer (admin); null otherwise. |
| `responded_on` | string | yes | ISO date of the answer. |
| `reviewer` | string | yes | The reviewer who answered. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "comment": "Check the weld map",
      "outcome": "approved_with_comments",
      "recorded_by": null,
      "responded_on": "2026-10-15",
      "reviewer": "user:ana"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ReviewCycle.OutcomeRecorded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ReviewCycle.OutcomeRecorded.v1"
}
```

## Revision.Defined

A revision of a document was created, as a draft.

- CloudEvents type: `tl.core.Revision.Defined.v1`
- Ledger payload class: `RevisionDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `change_note` | string or null | no | What changed since the previous revision. |
| `code` | string | yes | The revision code. |
| `document_id` | string | yes | Record id of the document. |
| `document_number` | string | yes | The document number. |
| `intended_status` | string or null | no | The issue status it is meant to be issued with. |
| `ordinal` | integer | yes | Position among the document's revisions, from 1. |
| `previous_revision_id` | string or null | no | Record id of the previous revision. |
| `purpose` | string or null | no | Purpose or issue reason. |
| `revision_date` | string or null | no | ISO date of the revision. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "change_note": null,
      "code": "A",
      "document_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "document_number": "ISO-1234",
      "intended_status": "IFR",
      "ordinal": 1,
      "previous_revision_id": null,
      "purpose": "First issue for review",
      "revision_date": "2026-10-13"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Revision.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Revision.Defined.v1"
}
```

## Revision.Issued

A revision was issued with an issue status; it is now current for its status class.

- CloudEvents type: `tl.core.Revision.Issued.v1`
- Ledger payload class: `RevisionIssuedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `date_reason` | string or null | no | Why the date is before the day it was recorded; null when it is that day. |
| `issue_status` | string | yes | The issue status (IFR, IFC, AFC, ASB). |
| `issued_on` | string | yes | ISO date of the issue. |
| `status_class` | string | yes | Its status class (review, construction, record). |
| `superseded_revision_ids` | any | no | Record ids of the revisions that stopped being current because of this issue. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "issue_status": "IFC",
      "issued_on": "2026-10-13",
      "status_class": "construction",
      "superseded_revision_ids": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Revision.Issued/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Revision.Issued.v1"
}
```

## Revision.Superseded

An issued revision stopped being current because a later one replaced it. It stays visible as superseded.

- CloudEvents type: `tl.core.Revision.Superseded.v1`
- Ledger payload class: `RevisionSupersededPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why. |
| `status_class` | string or null | no | The status class it was current in. |
| `superseded_by` | string | yes | Record id of the revision that replaces it. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Revision B issued",
      "status_class": "review",
      "superseded_by": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Revision.Superseded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Revision.Superseded.v1"
}
```

## Rule.Blocked

A matched event did not run the rule: the step was refused, the causation depth limit or a budget stopped it.

- CloudEvents type: `tl.core.Rule.Blocked.v1`
- Ledger payload class: `RuleBlockedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `depth` | integer | yes | Causation depth of the trigger. |
| `outcome` | string | yes | refused, depth_limit or budget. |
| `problems` | any | yes |  |
| `rule_id` | string | yes | Rule id. |
| `rule_version` | integer | yes | Rule version. |
| `trigger_event_id` | string | yes | The event that matched. |
| `trigger_seq` | integer | yes | Its seq. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "depth": 3,
      "outcome": "depth_limit",
      "problems": [
        {
          "code": "depth_limit",
          "message": "The causation depth limit of 3 was reached."
        }
      ],
      "rule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "rule_version": 2,
      "trigger_event_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8",
      "trigger_seq": 412
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Rule.Blocked/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Rule.Blocked.v1"
}
```

## Rule.Created

A rule was created. It starts disabled and in propose mode.

- CloudEvents type: `tl.core.Rule.Created.v1`
- Ledger payload class: `RuleCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `access` | string | yes | user or controller. |
| `condition` | string or null | no | Query-language condition on the subject record. |
| `enabled` | boolean or null | no | Whether it runs. |
| `integration_app` | string or null | no | Integration app name. |
| `key` | string | yes | Rule key (slug). |
| `mode` | string | yes | act or propose. |
| `owner` | string | yes | Owner actor. |
| `rule_id` | string | yes | Rule id. |
| `service_actor` | string | yes | svc:rule-<slug>. |
| `then` | any | yes |  |
| `title` | string | yes | Title. |
| `version` | integer | yes | Rule version. |
| `when` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "access": "user",
      "condition": null,
      "enabled": false,
      "integration_app": null,
      "key": "hse-notify",
      "mode": "propose",
      "owner": "user:jsmith",
      "rule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "service_actor": "svc:rule-hse-notify",
      "then": [
        {
          "args": {
            "body": "HSE notified of ${subject_key}"
          },
          "command": "PostToFeed"
        }
      ],
      "title": "Notify HSE on #safety",
      "version": 1,
      "when": {
        "event_types": [
          "Feed.PostCreated"
        ],
        "hashtags": [
          "safety"
        ]
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Rule.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Rule.Created.v1"
}
```

## Rule.Disabled

A rule was switched off.

- CloudEvents type: `tl.core.Rule.Disabled.v1`
- Ledger payload class: `RuleDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why. |
| `rule_id` | string | yes | Rule id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "noisy",
      "rule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Rule.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Rule.Disabled.v1"
}
```

## Rule.Enabled

A rule was switched on, from this event on.

- CloudEvents type: `tl.core.Rule.Enabled.v1`
- Ledger payload class: `RuleEnabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no | Why. |
| `rule_id` | string | yes | Rule id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "after dry run",
      "rule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Rule.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Rule.Enabled.v1"
}
```

## Rule.Revised

A rule was revised; the event carries the whole new rule. Switching to act mode is a revision with a reason.

- CloudEvents type: `tl.core.Rule.Revised.v1`
- Ledger payload class: `RuleRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |
| `rule` | any | yes |  |
| `rule_id` | string | yes | Rule id. |
| `version` | integer | yes | The new rule version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "ready to act",
      "rule": {
        "key": "hse-notify",
        "mode": "act",
        "version": 2
      },
      "rule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
      "version": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Rule.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Rule.Revised.v1"
}
```

## Schedule.Defined

A schedule was registered.

- CloudEvents type: `tl.core.Schedule.Defined.v1`
- Ledger payload class: `ScheduleDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | The schedule's code. |
| `owner` | string or null | no | Who owns it. |
| `p6_project` | string or null | no | The P6 project short name to read, or null. |
| `schedule_type` | string | yes | baseline, current, look_ahead or what_if. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "MAIN",
      "owner": "Planning",
      "p6_project": "DEMO-RACK",
      "schedule_type": "current"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Schedule.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Schedule.Defined.v1"
}
```

## Schedule.OrphansChecked

One run of the job that makes the links to a schedule's activities agree with its current snapshot (ADR-0015 section 5): activity references whose presence changed, links flagged stale (their activity is gone) and links restored (it came back). Written on the schedule's stream. A run does a bounded amount of work; complete is false when more is left and another run is queued.

- CloudEvents type: `tl.core.Schedule.OrphansChecked.v1`
- Ledger payload class: `ScheduleOrphansCheckedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `complete` | boolean | yes | True when nothing is left to do for this snapshot. |
| `links_flagged` | integer | yes | Links flagged stale in this run. |
| `links_restored` | integer | yes | Links restored in this run. |
| `refs_changed` | integer | yes | Activity references whose presence was changed in this run. |
| `snapshot_id` | string | yes | The current snapshot the run made the links agree with. |
| `snapshot_number` | integer | yes | Its number. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "complete": true,
      "links_flagged": 1,
      "links_restored": 0,
      "refs_changed": 1,
      "snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "snapshot_number": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Schedule.OrphansChecked/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Schedule.OrphansChecked.v1"
}
```

## Schedule.SnapshotPublished

A snapshot became the schedule's current one. Written on the schedule's stream.

- CloudEvents type: `tl.core.Schedule.SnapshotPublished.v1`
- Ledger payload class: `ScheduleSnapshotPublishedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `data_date` | string | yes | Its data date. |
| `orphan_check_queued` | boolean | yes | True: a job (schedule.flag_orphans) was queued to flag the links to activities that are not in the snapshot and to restore the ones that came back. Its events (Schedule.OrphansChecked) carry the totals. |
| `previous_snapshot_id` | string or null | no | The snapshot that was current before, or null. |
| `snapshot_id` | string | yes | The published snapshot. |
| `snapshot_number` | integer | yes | Its number. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "data_date": "2026-10-12T08:00",
      "orphan_check_queued": true,
      "previous_snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "snapshot_number": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Schedule.SnapshotPublished/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Schedule.SnapshotPublished.v1"
}
```

## ScheduleSnapshot.BuildFailed

A build attempt failed (a limit breach, a crash, a lease that ran out).

- CloudEvents type: `tl.core.ScheduleSnapshot.BuildFailed.v1`
- Ledger payload class: `ScheduleSnapshotBuildFailedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | Attempt number. |
| `error_code` | string | yes | A short fixed code. |
| `error_message` | string | yes | Words for a person; no paths, no trace. |
| `final` | boolean | yes | True when no attempt is left. |
| `retry_at` | string or null | no | ISO-8601 UTC of the next attempt, or null. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 1,
      "error_code": "xer_limit",
      "error_message": "reading the XER file broke the resource limits",
      "final": true,
      "retry_at": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ScheduleSnapshot.BuildFailed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ScheduleSnapshot.BuildFailed.v1"
}
```

## ScheduleSnapshot.BuildStarted

A worker claimed the build.

- CloudEvents type: `tl.core.ScheduleSnapshot.BuildStarted.v1`
- Ledger payload class: `ScheduleSnapshotBuildStartedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `attempt` | integer | yes | Attempt number. |
| `lease_until` | string | yes | ISO-8601 UTC; the claim expires here. |
| `worker` | string | yes | The worker's id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "attempt": 1,
      "lease_until": "2026-10-17T10:05:00Z",
      "worker": "host:1:abcdef"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ScheduleSnapshot.BuildStarted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ScheduleSnapshot.BuildStarted.v1"
}
```

## ScheduleSnapshot.Built

The file was read and passed the XER document schema; the typed rows were written. The snapshot is Valid.

- CloudEvents type: `tl.core.ScheduleSnapshot.Built.v1`
- Ledger payload class: `ScheduleSnapshotBuiltPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `counts` | any | yes |  |
| `data_date` | string | yes | The project's data date, ISO local date-time. |
| `p6_project` | string | yes | The P6 project short name that was read. |
| `p6_version` | string | yes | The P6 version of the file. |
| `raw_file_id` | string | yes | The raw tables file. |
| `raw_sha256` | string | yes | SHA-256 of the uncompressed raw tables. |
| `report_file_id` | string | yes | The check report file. |
| `typed_sha256` | string | yes | SHA-256 of the canonical typed rows. |
| `warning_count` | integer | yes | Warnings of the check. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "counts": {
        "activities": 21,
        "calendars": 1,
        "codes": 21,
        "relationships": 23,
        "udfs": 12,
        "wbs": 4
      },
      "data_date": "2026-10-05T08:00",
      "p6_project": "DEMO-RACK",
      "p6_version": "20.12",
      "raw_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "raw_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "report_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "typed_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "warning_count": 0
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ScheduleSnapshot.Built/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ScheduleSnapshot.Built.v1"
}
```

## ScheduleSnapshot.Defined

A snapshot was opened for a schedule; the XER file is attached next.

- CloudEvents type: `tl.core.ScheduleSnapshot.Defined.v1`
- Ledger payload class: `ScheduleSnapshotDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `number` | integer | yes | The snapshot's number in the schedule. |
| `p6_project_option` | string or null | no | The P6 project asked for, or null. |
| `schedule_code` | string | yes | Its code. |
| `schedule_id` | string | yes | The schedule. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "number": 1,
      "p6_project_option": null,
      "schedule_code": "MAIN",
      "schedule_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ScheduleSnapshot.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ScheduleSnapshot.Defined.v1"
}
```

## ScheduleSnapshot.MadeCurrent

A snapshot was made the schedule's current one. Written on the snapshot's stream next to the workflow move.

- CloudEvents type: `tl.core.ScheduleSnapshot.MadeCurrent.v1`
- Ledger payload class: `ScheduleSnapshotMadeCurrentPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `orphan_check_queued` | boolean | yes | True: the job that flags and restores the links to activities was queued. |
| `previous_snapshot_id` | string or null | no | The snapshot that was current before, or null. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "orphan_check_queued": true,
      "previous_snapshot_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ScheduleSnapshot.MadeCurrent/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ScheduleSnapshot.MadeCurrent.v1"
}
```

## ScheduleSnapshot.Queued

The build of a snapshot was queued: the XER file is fixed.

- CloudEvents type: `tl.core.ScheduleSnapshot.Queued.v1`
- Ledger payload class: `ScheduleSnapshotQueuedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `requested_by` | string | yes | The actor who asked. |
| `source_file_id` | string | yes | The XER file. |
| `source_name` | string | yes | Display name of the file. |
| `source_sha256` | string | yes | SHA-256 of the file. |
| `source_size` | integer | yes | Bytes. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "requested_by": "user:demo",
      "source_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "source_name": "rack-2026-10-05.xer",
      "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "source_size": 7496
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ScheduleSnapshot.Queued/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ScheduleSnapshot.Queued.v1"
}
```

## ScheduleSnapshot.Rejected

The file was read and is not a valid schedule snapshot (or could not be read): the snapshot is Invalid and no rows were written.

- CloudEvents type: `tl.core.ScheduleSnapshot.Rejected.v1`
- Ledger payload class: `ScheduleSnapshotRejectedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `error_count` | integer | yes | Errors. |
| `first_codes` | any | yes |  |
| `outcome` | string | yes | invalid (read, but it fails the document schema) or refused (could not be read). |
| `report_file_id` | string | yes | The report file. |
| `warning_count` | integer | yes | Warnings. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "error_count": 1,
      "first_codes": [
        "missing_table"
      ],
      "outcome": "invalid",
      "report_file_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "warning_count": 0
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/ScheduleSnapshot.Rejected/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.ScheduleSnapshot.Rejected.v1"
}
```

## Schema.EffectiveChanged

The effective schema of a scope changed.

- CloudEvents type: `tl.core.Schema.EffectiveChanged.v1`
- Ledger payload class: `SchemaEffectiveChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `effective_schema_hash` | string | yes | New hash. |
| `packages` | array or null | no | Adopted packages as name@version. |
| `previous_hash` | string or null | no | Previous hash; null the first time. |
| `scope` | string | yes | Scope id. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "effective_schema_hash": "9f2c",
      "packages": [
        "co.acme.engineering@3.2.0"
      ],
      "previous_hash": null,
      "scope": "project:P123"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Schema.EffectiveChanged/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Schema.EffectiveChanged.v1"
}
```

## SchemaPackage.Analysed

The classification and impact reports of the draft were made, for the content with the stated hash.

- CloudEvents type: `tl.core.SchemaPackage.Analysed.v1`
- Ledger payload class: `SchemaPackageAnalysedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `base_ref` | string or null | no | name@version the change was compared with, or null for a first version. |
| `classification` | any | yes |  |
| `classification_digest` | string | yes | The digest of the classification report. |
| `content_sha256` | string | yes | The content hash the reports were made for. |
| `impact` | any | yes |  |
| `impact_sha256` | string | yes | SHA-256 of the canonical JSON of the impact report. |
| `worst_class` | string | yes | The worst class of the change. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "base_ref": "co.acme.engineering@3.2.0",
      "classification": {
        "worst": "additive"
      },
      "classification_digest": "1111111111111111111111111111111111111111111111111111111111111111",
      "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "impact": {
        "sections": []
      },
      "impact_sha256": "2222222222222222222222222222222222222222222222222222222222222222",
      "worst_class": "additive"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Analysed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Analysed.v1"
}
```

## SchemaPackage.Approved

An administrator approved the package, having read the classification report with this digest.

- CloudEvents type: `tl.core.SchemaPackage.Approved.v1`
- Ledger payload class: `SchemaPackageApprovedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `approver` | string | yes | The approving administrator. |
| `classification_digest` | string | yes | The digest of the classification report approved. |
| `comment` | string or null | no | A remark, or null. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "approver": "user:admin",
      "classification_digest": "1111111111111111111111111111111111111111111111111111111111111111",
      "comment": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Approved/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Approved.v1"
}
```

## SchemaPackage.ChangesRequested

A reviewer sent the package back to Draft.

- CloudEvents type: `tl.core.SchemaPackage.ChangesRequested.v1`
- Ledger payload class: `SchemaPackageChangesRequestedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | What must change. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Say what seat_leak_class measures."
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.ChangesRequested/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.ChangesRequested.v1"
}
```

## SchemaPackage.Deprecated

A published version was deprecated: projects that pinned it keep it, nobody can adopt it.

- CloudEvents type: `tl.core.SchemaPackage.Deprecated.v1`
- Ledger payload class: `SchemaPackageDeprecatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |
| `replacement` | string or null | no | name@version that replaces it, or null. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Superseded by 3.3.0.",
      "replacement": "co.acme.engineering@3.3.0"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Deprecated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Deprecated.v1"
}
```

## SchemaPackage.Drafted

A package version was drafted. The content is the package YAML, at most 262144 bytes.

- CloudEvents type: `tl.core.SchemaPackage.Drafted.v1`
- Ledger payload class: `SchemaPackageDraftedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changelog` | string or null | no | What the author says changed, or null. |
| `content` | string | yes | The package YAML. |
| `content_sha256` | string | yes | SHA-256 of the content. |
| `drafted_by` | string | yes | The actor that drafted it. |
| `kind` | string | yes | company, extension or project. |
| `package` | string | yes | Package name. |
| `package_title` | string or null | no | The title the package gives itself, or null. |
| `project` | string or null | no | The project of an extension or project package, or null. |
| `version` | string | yes | Package version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "changelog": "Adds seat_leak_class.",
      "content": "package: co.acme.engineering\n",
      "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "drafted_by": "user:rgarcia",
      "kind": "company",
      "package": "co.acme.engineering",
      "package_title": null,
      "project": null,
      "version": "3.3.0"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Drafted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Drafted.v1"
}
```

## SchemaPackage.Published

A schema package version was published.

- CloudEvents type: `tl.core.SchemaPackage.Published.v1`
- Ledger payload class: `SchemaPackagePublishedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `auto_adopted` | array or null | no | Projects whose pin moved to this version by publication. |
| `content_sha256` | string or null | no | SHA-256 of the package content. |
| `kind` | string or null | no | company, extension or project. |
| `package` | string | yes | Package name. |
| `record_id` | string or null | no | The `schemareg.SchemaPackage` record, when the registry module published it. |
| `version` | string | yes | Package version. |
| `worst_class` | string or null | no | The worst class of the change the version makes (additive, constraining, ...). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "package": "co.acme.engineering",
      "version": "3.2.0"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Published/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Published.v1"
}
```

## SchemaPackage.Retired

A deprecated version was retired: it is out of every effective schema.

- CloudEvents type: `tl.core.SchemaPackage.Retired.v1`
- Ledger payload class: `SchemaPackageRetiredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "No project pins it."
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Retired/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Retired.v1"
}
```

## SchemaPackage.Revised

The author changed the content of a draft. Any earlier analysis no longer holds.

- CloudEvents type: `tl.core.SchemaPackage.Revised.v1`
- Ledger payload class: `SchemaPackageRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changelog` | string or null | no | What the author says changed, or null. |
| `content` | string | yes | The package YAML. |
| `content_sha256` | string | yes | SHA-256 of the content. |
| `package_title` | string or null | no | The title the package gives itself, or null. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "changelog": null,
      "content": "package: co.acme.engineering\n",
      "content_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "package_title": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Revised.v1"
}
```

## SchemaPackage.Submitted

The author sent the package to review.

- CloudEvents type: `tl.core.SchemaPackage.Submitted.v1`
- Ledger payload class: `SchemaPackageSubmittedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `classification_digest` | string | yes | The digest of the classification report the reviewer will read. |
| `submitted_by` | string | yes | The actor that submitted it. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "classification_digest": "1111111111111111111111111111111111111111111111111111111111111111",
      "submitted_by": "user:rgarcia"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/SchemaPackage.Submitted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.SchemaPackage.Submitted.v1"
}
```

## Setting.Changed

One key was set, or reset to what the layer above gives, at one layer. The stream is `setting:<layer>:<key>`. A change with `applies_at` in the future takes effect then (and not before): resolution is time-based, so no job applies it.

- CloudEvents type: `tl.core.Setting.Changed.v1`
- Ledger payload class: `SettingChangedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `accept_risk` | boolean or null | no | The person confirmed "I accept the risk" (a `dangerous` key). |
| `applies_at` | string or null | no | When the change takes effect, if later than the time it was recorded. |
| `key` | string | yes | The setting key. |
| `layer` | string | yes | `company`, `project:<id>` or `user:<id>`. |
| `new_value` | any | no | The new value; null with `reset` true. |
| `old_set` | boolean or null | no | Whether the layer held a value of its own before (false: it was inheriting). |
| `old_value` | any | no | The value the layer held when the change was recorded (null when it held none). |
| `reason` | string or null | no | Why. Required for `advanced` and `dangerous` keys. |
| `reset` | boolean or null | no | True when the layer goes back to inheriting. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "accept_risk": false,
      "applies_at": null,
      "key": "feed.reactions.enabled",
      "layer": "project:P123",
      "new_value": false,
      "old_set": false,
      "old_value": null,
      "reason": null,
      "reset": false
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Setting.Changed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Setting.Changed.v1"
}
```

## Setting.Locked

The company locked a key for its projects, unlocked it, or changed the bounds projects must keep to. The stream is `setting:company:<key>`.

- CloudEvents type: `tl.core.Setting.Locked.v1`
- Ledger payload class: `SettingLockedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `bounds` | any | no | Limits for project values: `minimum`, `maximum` and/or `choices`; null for none. |
| `key` | string | yes |  |
| `layer` | string | yes | Always `company`; only the company layer locks or bounds a key. |
| `locked` | boolean | yes | True when projects may not override the key. |
| `reason` | string | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "bounds": null,
      "key": "ai.agents.default_mode",
      "layer": "company",
      "locked": true,
      "reason": "Company policy: agents propose, people decide"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Setting.Locked/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Setting.Locked.v1"
}
```

## Standard.Closed

A registry entry was superseded by another or retired; it stays resolvable for history.

- CloudEvents type: `tl.core.Standard.Closed.v1`
- Ledger payload class: `StandardClosedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `effective_to` | string or null | no | ISO date the entry stops applying. |
| `lifecycle` | string | yes | superseded or retired. |
| `reason` | string | yes | Why. |
| `superseded_by` | string or null | no | Record id of the entry that replaced this one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "effective_to": "2027-01-01",
      "lifecycle": "superseded",
      "reason": "Edition 2 replaces the pattern",
      "superseded_by": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Standard.Closed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Standard.Closed.v1"
}
```

## Standard.Defined

A registry entry (a code list, a mnemonic or a numbering pattern) was defined.

- CloudEvents type: `tl.core.Standard.Defined.v1`
- Ledger payload class: `StandardDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `adoption` | string or null | no | mandatory, default or optional. |
| `code` | string | yes | The entry's code within its kind. |
| `data` | any | no | Kind-specific content. |
| `definition` | string or null | no | What the entry means or governs. |
| `edition` | string | yes | The standards edition that supplied it. |
| `effective_from` | string or null | no | ISO date from which the entry applies. |
| `effective_to` | string or null | no | ISO date after which it no longer applies. |
| `kind` | string | yes | code_list, mnemonic or numbering_pattern. |
| `label` | string | yes | Display name or meaning. |
| `owner` | string or null | no | Steward of the entry. |
| `value_list_policy` | string or null | no | Code lists only: closed, extensible or project_defined. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "adoption": "mandatory",
      "code": "FV",
      "data": {
        "class_hint": "ControlValve"
      },
      "definition": null,
      "edition": "co.acme.standards@1.0.0",
      "effective_from": null,
      "effective_to": null,
      "kind": "mnemonic",
      "label": "Flow control valve",
      "owner": "role:standards-steward",
      "value_list_policy": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Standard.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Standard.Defined.v1"
}
```

## Tag.Defined

A tag was created, with its number parsed into segments and its class.

- CloudEvents type: `tl.core.Tag.Defined.v1`
- Ledger payload class: `TagDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `area` | string or null | no | The area or unit segment. |
| `bound_psets` | any | no | Pset names the class binds to the tag. |
| `class_code` | string or null | no | Code of the tag's class; null until classified. |
| `conformance` | string or null | no | Conformance of the new tag: ok, warning, nonconformant or waived. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `mnemonic` | string or null | no | The mnemonic segment. |
| `number` | string | yes | The tag number. |
| `number_status` | string | yes | ok or violation. |
| `origin` | string | yes | created, import, rename, split or merge. |
| `pattern_code` | string or null | no | Code of the numbering pattern the number was checked against. |
| `segments` | any | no | Every parsed segment by name. |
| `sequence` | integer or null | no | The sequence segment. |
| `supersedes` | any | no | Record ids of the tags this one replaces. |
| `violations` | any | no | The problems found in the number. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "area": "47",
      "bound_psets": [
        "valve_data"
      ],
      "class_code": "ControlValve",
      "conformance": "nonconformant",
      "effective_schema_hash": "9f2c",
      "mnemonic": "FV",
      "number": "47-FV-1001",
      "number_status": "ok",
      "origin": "created",
      "pattern_code": "tag",
      "segments": {
        "area": "47",
        "mnemonic": "FV",
        "seq": "1001"
      },
      "sequence": 1001,
      "supersedes": [],
      "violations": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Tag.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Tag.Defined.v1"
}
```

## Tag.Reclassified

A tag moved to another class; the new class may bind other property sets.

- CloudEvents type: `tl.core.Tag.Reclassified.v1`
- Ledger payload class: `TagReclassifiedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `bound_psets` | any | no | Pset names the new class binds. |
| `conformance` | string or null | no | Conformance after the change. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `from_class` | string or null | no | The previous class code; null when the tag had none. |
| `reason` | string or null | no | Why. |
| `to_class` | string | yes | The new class code. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "class_code": [
        "ManualValve",
        "ControlValve"
      ]
    },
    "detail": {
      "bound_psets": [
        "valve_data"
      ],
      "conformance": "nonconformant",
      "effective_schema_hash": "9f2c",
      "from_class": "ManualValve",
      "reason": "Actuator added",
      "to_class": "ControlValve"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Tag.Reclassified/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Tag.Reclassified.v1"
}
```

## Tag.Superseded

A tag was replaced by one or more others (a rename, a split or a merge); it stays in the ledger as history.

- CloudEvents type: `tl.core.Tag.Superseded.v1`
- Ledger payload class: `TagSupersededPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `operation` | string | yes | rename, split or merge. |
| `reason` | string | yes | Why. |
| `superseded_by` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "operation": "rename",
      "reason": "P&ID revision 3 renumbers the loop",
      "superseded_by": [
        "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Tag.Superseded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Tag.Superseded.v1"
}
```

## TagClass.Closed

A tag class was retired; tags already of that class keep it.

- CloudEvents type: `tl.core.TagClass.Closed.v1`
- Ledger payload class: `TagClassClosedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `lifecycle` | string | yes | superseded or retired. |
| `reason` | string | yes | Why. |
| `superseded_by` | string or null | no | Record id of the class that replaced this one. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "lifecycle": "retired",
      "reason": "Merged into ControlValve",
      "superseded_by": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/TagClass.Closed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TagClass.Closed.v1"
}
```

## TagClass.Defined

A tag class was defined.

- CloudEvents type: `tl.core.TagClass.Defined.v1`
- Ledger payload class: `TagClassDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | string | yes | The class code. |
| `edition` | string | yes | The standards edition that supplied the class. |
| `family` | string | yes | instrument, valve, pump, line, equipment, cable or other. |
| `itr_templates` | any | no | ITR template references. |
| `label` | string | yes | Display name. |
| `mnemonics` | any | no | Mnemonic codes that normally identify this class. |
| `required_psets` | any | no | Pset names a tag of this class must carry. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "code": "ControlValve",
      "edition": "co.acme.standards@1.0.0",
      "family": "valve",
      "itr_templates": [
        "ITR-VALVE-01"
      ],
      "label": "Control valve",
      "mnemonics": [
        "FV"
      ],
      "required_psets": [
        "valve_data"
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/TagClass.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TagClass.Defined.v1"
}
```

## TagClass.Revised

A tag class changed. Adding a required pset is a constraining change: existing tags are flagged, not rewritten.

- CloudEvents type: `tl.core.TagClass.Revised.v1`
- Ledger payload class: `TagClassRevisedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string | yes | Why it changed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "required_psets": [
        [
          "valve_data"
        ],
        [
          "valve_data",
          "safety_data"
        ]
      ]
    },
    "detail": {
      "changes": {
        "required_psets": [
          [
            "valve_data"
          ],
          [
            "valve_data",
            "safety_data"
          ]
        ]
      },
      "reason": "SIS valves need safety data"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/TagClass.Revised/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TagClass.Revised.v1"
}
```

## Technical.Answered

The answer to a Technical item was recorded, with the answerer's statement on cost and schedule. A cost or schedule impact of `yes` is what the RFI to Commercial escalation rule listens for.

- CloudEvents type: `tl.core.Technical.Answered.v1`
- Ledger payload class: `TechnicalAnsweredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `answer` | string | yes | The answer, plain text. |
| `answer_item_id` | string or null | no | Record id of the item that carries the answer, when there is one. |
| `answered_on` | string | yes | ISO date of the answer. |
| `answering_revision_id` | string or null | no | Record id of the document revision that answers, when there is one. |
| `cost_impact` | string | yes | yes, no or unknown. |
| `date_reason` | string or null | no | Why the date is before the day it was recorded; null when it is that day. |
| `feed_policy` | string or null | no | full, minimal or none: what the feed shows (the domain's policy at the time). |
| `feed_text` | string or null | no | The line of the feed card when the policy is full or minimal. |
| `schedule_impact` | string | yes | yes, no or unknown. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "answer": "Re-route as proposed; revision C follows",
      "answer_item_id": null,
      "answered_on": "2026-10-20",
      "answering_revision_id": null,
      "cost_impact": "yes",
      "date_reason": null,
      "schedule_impact": "no"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Technical.Answered/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Technical.Answered.v1"
}
```

## Technical.Defined

A Technical item (RFI, technical query or deviation request) was raised. It follows the `Correspondence.Defined` event of the same item in the same append and holds the domain data.

- CloudEvents type: `tl.core.Technical.Defined.v1`
- Ledger payload class: `TechnicalDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `discipline` | string or null | no | Discipline code. |
| `potential_cost_impact` | string | yes | yes, no or unknown. |
| `potential_schedule_impact` | string | yes | yes, no or unknown. |
| `proposed_solution` | string or null | no | What the raiser proposes. |
| `question` | string | yes | The question, or the deviation to be accepted. |
| `required_by` | string or null | no | ISO date an answer is needed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "discipline": "M",
      "potential_cost_impact": "unknown",
      "potential_schedule_impact": "no",
      "proposed_solution": "Re-route the line above the beam",
      "question": "The isometric clashes with beam B12; confirm the routing",
      "required_by": "2026-10-30"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Technical.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Technical.Defined.v1"
}
```

## Technical.Reissued

A rejected Technical item went back to internal review to be issued again. The answer and the judgement of the round before are cleared from the current state; the events keep them.

- CloudEvents type: `tl.core.Technical.Reissued.v1`
- Ledger payload class: `TechnicalReissuedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why it is issued again. |
| `round` | integer | yes | The number of the round that starts, counting the first issue as 1. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "Names beam B12 and B13",
      "round": 2
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Technical.Reissued/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Technical.Reissued.v1"
}
```

## Technical.Reviewed

The raiser accepted or rejected the answer. A rejected answer is re-issued with `Technical.Reissued`.

- CloudEvents type: `tl.core.Technical.Reviewed.v1`
- Ledger payload class: `TechnicalReviewedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `decision` | string | yes | accepted or rejected. |
| `note` | string or null | no | Remark on accepting, or why the answer was rejected. |
| `reviewed_on` | string | yes | ISO date. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "decision": "rejected",
      "note": "The answer does not say which beam",
      "reviewed_on": "2026-10-21"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Technical.Reviewed/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Technical.Reviewed.v1"
}
```

## Technical.Updated

The domain fields of a Technical item that is a draft or in internal review changed.

- CloudEvents type: `tl.core.Technical.Updated.v1`
- Ledger payload class: `TechnicalUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |
| `reason` | string or null | no | Why it changed. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "required_by": [
        "2026-10-30",
        "2026-11-06"
      ]
    },
    "detail": {
      "changes": {
        "required_by": [
          "2026-10-30",
          "2026-11-06"
        ]
      },
      "reason": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Technical.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Technical.Updated.v1"
}
```

## Thread.Dispatched

A slash command in a thread was confirmed and its commands ran, in the same transaction as the message of kind `dispatch` that carries the command line. `results` lists the commands, `link_ids` the `dispatched_from` links from created records back to the thread's record. Each command's own events carry the source `thread:<record id>`, the correlation id `dispatch:<message id>` and this message's event as their cause.

- CloudEvents type: `tl.core.Thread.Dispatched.v1`
- Ledger payload class: `ThreadDispatchedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `link_ids` | array or null | no |  |
| `message_id` | string | yes |  |
| `record_id` | string | yes |  |
| `results` | array or null | no |  |
| `summary` | string or null | no | One line for the result card. |
| `verb` | string | yes | The slash command verb (`link`, `status`, `raise`, `dispatch`, `notify`, `remind`, `summarise`...). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "link_ids": [
        "01J9Z6Q4W3X2Y1V0T9S8R7Q6P8"
      ],
      "message_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "results": [
        {
          "command_type": "CreateRecord",
          "key": "P123-REC-0044",
          "stream_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7",
          "version": 1
        }
      ],
      "summary": "Created P123-REC-0044",
      "verb": "raise"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Thread.Dispatched/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Thread.Dispatched.v1"
}
```

## Thread.MessageEdited

The author replaced the body of a message. The payload is a full replacement of the body, the mentions and the record references; the earlier text stays in the ledger.

- CloudEvents type: `tl.core.Thread.MessageEdited.v1`
- Ledger payload class: `ThreadMessageEditedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `body` | string | yes |  |
| `mentions` | array or null | no |  |
| `message_id` | string | yes |  |
| `record_id` | string | yes |  |
| `record_refs` | array or null | no |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "body": "Flanges short for W019 and W020 @lchen",
      "mentions": [
        "lchen"
      ],
      "message_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "record_refs": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Thread.MessageEdited/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Thread.MessageEdited.v1"
}
```

## Thread.MessagePosted

A message was posted in a record thread. The first message of a record creates the thread stream and also carries `record_creator`, the actor that created the record, who joins the participants.

- CloudEvents type: `tl.core.Thread.MessagePosted.v1`
- Ledger payload class: `ThreadMessagePostedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `author` | string | yes |  |
| `body` | string | yes |  |
| `kind` | string | yes | What a message is. A person's message is `message`; the others are written by the server. |
| `mentions` | array or null | no |  |
| `message_id` | string | yes |  |
| `record_creator` | string or null | no | First message of the thread only; the actor that created the record. |
| `record_id` | string | yes |  |
| `record_refs` | array or null | no |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "author": "user:rgarcia",
      "body": "Flanges short for W019 @lchen",
      "kind": "message",
      "mentions": [
        "lchen"
      ],
      "message_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "record_creator": "user:mlee",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6",
      "record_refs": []
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Thread.MessagePosted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Thread.MessagePosted.v1"
}
```

## Thread.MessageRetracted

The author retracted a message. The projection keeps a tombstone row and drops the body.

- CloudEvents type: `tl.core.Thread.MessageRetracted.v1`
- Ledger payload class: `ThreadMessageRetractedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `message_id` | string | yes |  |
| `reason` | string | yes | Why the message was retracted. |
| `record_id` | string | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "message_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "reason": "Wrong record",
      "record_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Thread.MessageRetracted/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Thread.MessageRetracted.v1"
}
```

## Transmittal.Defined

A transmittal was drafted with the revisions it carries and its recipients.

- CloudEvents type: `tl.core.Transmittal.Defined.v1`
- Ledger payload class: `TransmittalDefinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `direction` | string | yes | outgoing or incoming. |
| `due_date` | string or null | no | ISO date an answer is due. |
| `items` | any | yes |  |
| `number` | string | yes | The transmittal number. |
| `purpose` | string | yes | Why it is sent. |
| `recipients` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "direction": "outgoing",
      "due_date": "2026-10-27",
      "items": [
        {
          "document_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
          "document_number": "ISO-1234",
          "issue_status": "IFC",
          "revision_code": "B",
          "revision_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
        }
      ],
      "number": "TRN-0001",
      "purpose": "for_construction",
      "recipients": [
        {
          "email": null,
          "name": "Site document control",
          "organisation": "Acme Construction"
        }
      ]
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Transmittal.Defined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Transmittal.Defined.v1"
}
```

## Transmittal.Issued

A transmittal was issued to its recipients.

- CloudEvents type: `tl.core.Transmittal.Issued.v1`
- Ledger payload class: `TransmittalIssuedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `date_reason` | string or null | no | Why the date is before the day it was recorded; null when it is that day. |
| `issued_on` | string | yes | ISO date of the issue. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "date_reason": null,
      "issued_on": "2026-10-13"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Transmittal.Issued/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Transmittal.Issued.v1"
}
```

## Transmittal.ResponseRecorded

The recipients answered a transmittal.

- CloudEvents type: `tl.core.Transmittal.ResponseRecorded.v1`
- Ledger payload class: `TransmittalResponseRecordedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `date_reason` | string or null | no | Why the date is before the day it was recorded; null when it is that day. |
| `responded_on` | string | yes | ISO date of the answer. |
| `response_code` | string | yes | approved, approved_with_comments, rejected or noted. |
| `response_note` | string or null | no | Free text that came with the answer. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "date_reason": null,
      "responded_on": "2026-10-20",
      "response_code": "approved",
      "response_note": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Transmittal.ResponseRecorded/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Transmittal.ResponseRecorded.v1"
}
```

## TypeRegistration.Deprecated

The owner retired a version. Existing instances stay readable and editable; no new instance can be created.

- CloudEvents type: `tl.core.TypeRegistration.Deprecated.v1`
- Ledger payload class: `TypeRegistrationDeprecatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |
| `type_ref` | string | yes | The deprecated version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "superseded by 2.0.0",
      "type_ref": "co.acme.LiftPlan@1.0.0"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/TypeRegistration.Deprecated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TypeRegistration.Deprecated.v1"
}
```

## TypeRegistration.Quarantined

A type package failed validation, or its files changed under a version that is already registered. The report lists every problem (`kind`, `path`, `detail`). A conflict never removes a registration that is already active.

- CloudEvents type: `tl.core.TypeRegistration.Quarantined.v1`
- Ledger payload class: `TypeRegistrationQuarantinedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_hash` | string | yes | sha256 over the canonical `type.lock` form of the files as found. |
| `location_uri` | string | yes | Where the package files are. |
| `report` | any | yes |  |
| `type_ref` | string | yes | `<namespace>.<name>@<version>`, or `invalid:<relative path>` when the path is not a package path. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_hash": "4d1c0a0f9f43b3a0a0f3a6a6b9d3f0a5c8e5d9b2f1a7c3e6d4b8a2f9c1e7d0b3",
      "location_uri": "file:///srv/types/co.acme/LiftPlan/1.0.1",
      "report": [
        {
          "detail": "examples/bad.json: 'risk_class' is not one of ['low', 'medium', 'high']",
          "kind": "example",
          "path": "examples/bad.json"
        }
      ],
      "type_ref": "co.acme.LiftPlan@1.0.1"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/TypeRegistration.Quarantined/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TypeRegistration.Quarantined.v1"
}
```

## TypeRegistration.Registered

A type package validated and was registered. The package files stay where they are; this event holds metadata only. `content_hash` is the sha256 of the canonical bytes of the package's `type.lock`.

- CloudEvents type: `tl.core.TypeRegistration.Registered.v1`
- Ledger payload class: `TypeRegistrationRegisteredPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `content_hash` | string | yes | sha256 over the canonical bytes of `type.lock`. |
| `index_fields` | array or null | no | Slots annotated `tl:index`: the query contract. |
| `location_uri` | string | yes | Where the package files are, for example `file:///srv/types/co.acme/LiftPlan/1.0.0`. |
| `name` | string | yes | Type name, UpperCamelCase, for example `LiftPlan`. |
| `namespace` | string | yes | Namespace, dotted lower-case segments, for example `co.acme`. |
| `owner` | string | yes | Actor that registered the package. |
| `schema_hash` | string | yes | Hash of the compiled class: the schema a stored body validated against. |
| `status` | string | yes | `active` for this event. |
| `storage_mode` | string | yes | `managed` or `object-backed` in v0. |
| `type_ref` | string | yes | `<namespace>.<name>@<version>`. |
| `version` | string | yes | Semantic version `MAJOR.MINOR.PATCH`. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "content_hash": "4d1c0a0f9f43b3a0a0f3a6a6b9d3f0a5c8e5d9b2f1a7c3e6d4b8a2f9c1e7d0b3",
      "index_fields": [
        "crane",
        "lift_date",
        "risk_class"
      ],
      "location_uri": "file:///srv/types/co.acme/LiftPlan/1.0.0",
      "name": "LiftPlan",
      "namespace": "co.acme",
      "owner": "user:alice",
      "schema_hash": "7a3b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a2b",
      "status": "active",
      "storage_mode": "object-backed",
      "type_ref": "co.acme.LiftPlan@1.0.0",
      "version": "1.0.0"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/TypeRegistration.Registered/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.TypeRegistration.Registered.v1"
}
```

## Waiver.Approved

An administrator approved the waiver; the effective schema of the project changes.

- CloudEvents type: `tl.core.Waiver.Approved.v1`
- Ledger payload class: `WaiverApprovedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `approver` | string | yes | The approving administrator. |
| `comment` | string or null | no | A remark, or null. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "approver": "user:admin",
      "comment": null
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Waiver.Approved/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Waiver.Approved.v1"
}
```

## Waiver.Requested

Someone asked to relax one property for a project until a date.

- CloudEvents type: `tl.core.Waiver.Requested.v1`
- Ledger payload class: `WaiverRequestedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `expires` | string | yes | Last day it holds, YYYY-MM-DD. |
| `number` | integer | yes | 1 for the first waiver of the path in the project. |
| `path` | string | yes | The property path. |
| `project` | string | yes | The project id. |
| `reason` | string | yes | Why. |
| `requested_by` | string | yes | The actor that asked. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "expires": "2027-03-31",
      "number": 1,
      "path": "psets.valve_data.size_in",
      "project": "P123",
      "reason": "Legacy valves have no size on record.",
      "requested_by": "user:rgarcia"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Waiver.Requested/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Waiver.Requested.v1"
}
```

## Waiver.Revoked

An administrator revoked the waiver (or refused a request).

- CloudEvents type: `tl.core.Waiver.Revoked.v1`
- Ledger payload class: `WaiverRevokedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes | Why. |
| `revoked_by` | string | yes | The administrator. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "reason": "The data was corrected.",
      "revoked_by": "user:admin"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Waiver.Revoked/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Waiver.Revoked.v1"
}
```

## WebhookSubscription.Created

A webhook subscription was created. The signing secret is held outside the ledger.

- CloudEvents type: `tl.core.WebhookSubscription.Created.v1`
- Ledger payload class: `WebhookSubscriptionCreatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `event_schema_version` | string or null | no | Schema pin. |
| `expires_at` | string or null | no | ISO-8601 time after which the subscription stops. |
| `filter` | any | yes |  |
| `integration_app` | string or null | no | Integration app. |
| `name` | string | yes | Label. |
| `owner` | string | yes | Owner actor. |
| `payload_mode` | string | yes | thin, delta or full. |
| `secret_id` | string | yes | Id of the first signing secret (not the secret). |
| `subscription_id` | string | yes | Subscription id. |
| `target_url` | string | yes | Receiver URL. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "event_schema_version": "v1",
      "expires_at": null,
      "filter": {
        "event_types": [
          "Workflow.Transitioned"
        ],
        "transitions": [
          "* -> Issued"
        ]
      },
      "integration_app": null,
      "name": "NDE requests",
      "owner": "user:jsmith",
      "payload_mode": "delta",
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
      "subscription_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA",
      "target_url": "https://nde.example.net/hooks/tl"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Created/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Created.v1"
}
```

## WebhookSubscription.Disabled

A subscription stopped receiving events.

- CloudEvents type: `tl.core.WebhookSubscription.Disabled.v1`
- Ledger payload class: `WebhookSubscriptionDisabledPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `detail` | string or null | no | Free-text detail, for example the failure counts. |
| `reason` | string | yes | owner or sustained_failure. |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "detail": "5 deliveries dead-lettered since the last success",
      "reason": "sustained_failure"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Disabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Disabled.v1"
}
```

## WebhookSubscription.Enabled

A disabled subscription started receiving events again, from this event on.

- CloudEvents type: `tl.core.WebhookSubscription.Enabled.v1`
- Ledger payload class: `WebhookSubscriptionEnabledPayload`
- Version: 1

### Payload fields

No fields.

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {},
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Enabled/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Enabled.v1"
}
```

## WebhookSubscription.SecretRotated

A new signing secret was issued; the previous one keeps signing until the overlap ends.

- CloudEvents type: `tl.core.WebhookSubscription.SecretRotated.v1`
- Ledger payload class: `WebhookSubscriptionSecretRotatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `previous_expires_at` | string or null | no | ISO-8601 time when the previous secret stops signing. |
| `previous_secret_id` | string or null | no | Id of the secret that is being replaced. |
| `secret_id` | string | yes | Id of the new secret (not the secret). |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "previous_expires_at": "2026-10-10T03:14:07.000000Z",
      "previous_secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC",
      "secret_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.SecretRotated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.SecretRotated.v1"
}
```

## WebhookSubscription.Updated

A subscription's name, target, filter or payload mode changed.

- CloudEvents type: `tl.core.WebhookSubscription.Updated.v1`
- Ledger payload class: `WebhookSubscriptionUpdatedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `changes` | any | yes |  |

### Sample delivered event

```json
{
  "data": {
    "changes": {},
    "detail": {
      "changes": {
        "payload_mode": [
          "thin",
          "delta"
        ]
      }
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/WebhookSubscription.Updated/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.WebhookSubscription.Updated.v1"
}
```

## Workflow.Transitioned

A record moved from one workflow state to another.

- CloudEvents type: `tl.core.Workflow.Transitioned.v1`
- Ledger payload class: `WorkflowTransitionedPayload`
- Version: 1

### Payload fields

| Field | Type | Required | Description |
|---|---|---|---|
| `conformance` | string or null | no | Conformance after the transition. |
| `effective_schema_hash` | string or null | no | Hash of the effective schema in force. |
| `from_state` | string | yes | State before. |
| `guards_evaluated` | any | no | List of {kind, passed, message} for each guard that ran. |
| `reason` | string or null | no | Free-text reason. |
| `signature` | any | no | Signature data when the transition was signed. |
| `to_state` | string | yes | State after. |
| `transition` | string | yes | Transition name. |
| `workflow` | string | yes | Workflow id. |
| `workflow_version` | integer or null | no | Workflow version. |

### Sample delivered event

```json
{
  "data": {
    "changes": {
      "status": [
        "InReview",
        "Issued"
      ]
    },
    "detail": {
      "conformance": "ok",
      "effective_schema_hash": "9f2c",
      "from_state": "InReview",
      "guards_evaluated": [
        {
          "kind": "required_pset",
          "message": "",
          "passed": true
        }
      ],
      "reason": null,
      "signature": null,
      "to_state": "Issued",
      "transition": "issue",
      "workflow": "document",
      "workflow_version": 1
    },
    "links": [],
    "origin": {
      "api": "https://tl.example.com/api/v1/p/P123/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "id": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
      "key": "47-1234-W012",
      "type": "core.Record",
      "uri": "https://tl.example.com/c/acme/p/P123/r/core.Record/47-1234-W012@v7",
      "version": 7
    }
  },
  "datacontenttype": "application/json",
  "dataschema": "https://tl.example.com/schema/events/Workflow.Transitioned/1",
  "id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
  "source": "https://tl.example.com/c/acme/p/P123",
  "specversion": "1.0",
  "subject": "urn:tl:01J9Z6Q4W3X2Y1V0T9S8R7Q6P5",
  "time": "2026-10-09T03:14:07.000000Z",
  "tlactor": "user:jsmith",
  "tlcorrelationid": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PX",
  "tlseq": 48211933,
  "tlstreamversion": 7,
  "type": "tl.core.Workflow.Transitioned.v1"
}
```
