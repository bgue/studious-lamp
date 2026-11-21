-- # Class: LinkDataset Description: One model, one schedule, and everything that links them. In JSON this is the links file; in SQL each slot holding a list becomes its own table keyed to the dataset.
--     * Slot: id Description: Unique key of the record (a UUID or any stable string).
--     * Slot: created_at
--     * Slot: tool Description: The program and version that wrote the dataset (xray-4d 1.0, viewer 25, an MCP server name).
--     * Slot: model_identity_key
--     * Slot: schedule_source_hash Description: The schedule the links belong to. Absent in a mapping-only dataset (element assignments made before any schedule is linked); required in practice as soon as the dataset holds activities or links.
-- # Class: ModelRef Description: The IFC model the elements belong to.
--     * Slot: identity_key Description: The viewer's model identity key (file names and sizes, or a content hash), the same in every tool.
--     * Slot: name
--     * Slot: file_name
--     * Slot: file_hash Description: SHA-256 of the file, hex.
--     * Slot: ifc_schema
-- # Class: ScheduleRef Description: The schedule the activities belong to (one P6 project of one XER file).
--     * Slot: source_hash Description: SHA-256 of the XER file, hex.
--     * Slot: project Description: The P6 project short name.
--     * Slot: data_date Description: The schedule's data date (P6 last_recalc_date), local time without a zone.
--     * Slot: file_name
-- # Class: Activity Description: A schedule activity as far as linking needs it. The full schedule stays in the XER; these rows exist so SQL can join and filter (by location, trade, dates) without parsing XER.
--     * Slot: task_code Description: The P6 Activity ID (task_code).
--     * Slot: name
--     * Slot: wbs_path Description: WBS short names from the top down, joined with "/".
--     * Slot: activity_type
--     * Slot: activity_status Description: The P6 status of the activity.
--     * Slot: start Description: The activity's start in the dates the dataset was made from (planned or actual), local time.
--     * Slot: finish
--     * Slot: location Description: Location value (schedule side after value mapping, or model side), e.g. "Level 3".
--     * Slot: trade Description: Trade value, e.g. "CONC".
--     * Slot: zone Description: Zone or area value, e.g. "A".
--     * Slot: critical
--     * Slot: LinkDataset_id Description: Autocreated FK slot
-- # Class: Element Description: An IFC element as far as linking needs it, with the attributes read from the model.
--     * Slot: global_id Description: The IFC GlobalId (22 characters, IFC base-64).
--     * Slot: ifc_class Description: The IFC entity, e.g. IfcSlab.
--     * Slot: name
--     * Slot: storey Description: The name of the IfcBuildingStorey that contains the element.
--     * Slot: location Description: Location value (schedule side after value mapping, or model side), e.g. "Level 3".
--     * Slot: trade Description: Trade value, e.g. "CONC".
--     * Slot: zone Description: Zone or area value, e.g. "A".
--     * Slot: existing Description: The element exists before the job starts (never animated in).
--     * Slot: LinkDataset_id Description: Autocreated FK slot
-- # Class: Assignment Description: One attribute value given to one element (its location, trade or zone), with who or what gave it. The viewer's 4D mapping tool, rules, the classifier and SQL / MCP agents all write these; accepted ones are saved into the IFC (property set Xray_4D) and drive the links.
--     * Slot: id Description: Unique key of the record (a UUID or any stable string).
--     * Slot: element Description: An element, by GlobalId.
--     * Slot: attribute
--     * Slot: value Description: The assigned value.
--     * Slot: source
--     * Slot: confidence
--     * Slot: status Description: The review state of an assignment or a link.
--     * Slot: reviewed_by Description: Who accepted or rejected the record. Personal data: kept in the dataset only, never written into share links or packed pages, and into the IFC only by explicit opt-in (like reviewer names in Xray_Review).
--     * Slot: reviewed_at
--     * Slot: created_at
--     * Slot: LinkDataset_id Description: Autocreated FK slot
-- # Class: ActivityLink Description: Elements built (or removed) by an activity. An element has at most one accepted build link; a removal link may follow it.
--     * Slot: id Description: Unique key of the record (a UUID or any stable string).
--     * Slot: activity
--     * Slot: role
--     * Slot: source
--     * Slot: confidence
--     * Slot: split
--     * Slot: rule Description: The mapping rule or query that made the link (for attribute and suggested links).
--     * Slot: status Description: The review state of an assignment or a link.
--     * Slot: reviewed_by Description: Who accepted or rejected the record. Personal data: kept in the dataset only, never written into share links or packed pages, and into the IFC only by explicit opt-in (like reviewer names in Xray_Review).
--     * Slot: reviewed_at
--     * Slot: created_at
--     * Slot: LinkDataset_id Description: Autocreated FK slot
-- # Class: Tie Description: An element that two or more activities would build with equal specificity; left for a person to decide.
--     * Slot: id
--     * Slot: element Description: An element, by GlobalId.
--     * Slot: LinkDataset_id Description: Autocreated FK slot
-- # Class: LinkDataset_unlinked_activities
--     * Slot: LinkDataset_id Description: Autocreated FK slot
--     * Slot: unlinked_activities_task_code Description: Activities that should build something but have no accepted link.
-- # Class: LinkDataset_unlinked_elements
--     * Slot: LinkDataset_id Description: Autocreated FK slot
--     * Slot: unlinked_elements_global_id Description: Elements that are not existing and have no accepted build link.
-- # Class: Assignment_reasons
--     * Slot: Assignment_id Description: Autocreated FK slot
--     * Slot: reasons Description: Human-readable evidence, one per line ("Level 3 from code Level=L03").
-- # Class: ActivityLink_elements
--     * Slot: ActivityLink_id Description: Autocreated FK slot
--     * Slot: elements_global_id Description: The elements that the activity builds or removes (references by GlobalId).
-- # Class: ActivityLink_reasons
--     * Slot: ActivityLink_id Description: Autocreated FK slot
--     * Slot: reasons Description: Human-readable evidence, one per line ("Level 3 from code Level=L03").
-- # Class: Tie_candidates
--     * Slot: Tie_id Description: Autocreated FK slot
--     * Slot: candidates_task_code

CREATE TABLE "ModelRef" (
	identity_key TEXT NOT NULL,
	name TEXT,
	file_name TEXT,
	file_hash TEXT,
	ifc_schema VARCHAR(6),
	PRIMARY KEY (identity_key)
);
CREATE INDEX "ix_ModelRef_identity_key" ON "ModelRef" (identity_key);

CREATE TABLE "ScheduleRef" (
	source_hash TEXT NOT NULL,
	project TEXT NOT NULL,
	data_date TEXT,
	file_name TEXT,
	PRIMARY KEY (source_hash)
);
CREATE INDEX "ix_ScheduleRef_source_hash" ON "ScheduleRef" (source_hash);

CREATE TABLE "LinkDataset" (
	id TEXT NOT NULL,
	created_at DATETIME,
	tool TEXT,
	model_identity_key TEXT NOT NULL,
	schedule_source_hash TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(model_identity_key) REFERENCES "ModelRef" (identity_key),
	FOREIGN KEY(schedule_source_hash) REFERENCES "ScheduleRef" (source_hash)
);
CREATE INDEX "ix_LinkDataset_id" ON "LinkDataset" (id);

CREATE TABLE "Activity" (
	task_code TEXT NOT NULL,
	name TEXT,
	wbs_path TEXT,
	activity_type VARCHAR(15),
	activity_status VARCHAR(10),
	start TEXT,
	finish TEXT,
	location TEXT,
	trade TEXT,
	zone TEXT,
	critical BOOLEAN,
	"LinkDataset_id" TEXT,
	PRIMARY KEY (task_code),
	FOREIGN KEY("LinkDataset_id") REFERENCES "LinkDataset" (id)
);
CREATE INDEX "ix_Activity_task_code" ON "Activity" (task_code);

CREATE TABLE "Element" (
	global_id TEXT NOT NULL,
	ifc_class TEXT,
	name TEXT,
	storey TEXT,
	location TEXT,
	trade TEXT,
	zone TEXT,
	existing BOOLEAN,
	"LinkDataset_id" TEXT,
	PRIMARY KEY (global_id),
	FOREIGN KEY("LinkDataset_id") REFERENCES "LinkDataset" (id)
);
CREATE INDEX "ix_Element_global_id" ON "Element" (global_id);

CREATE TABLE "Assignment" (
	id TEXT NOT NULL,
	element TEXT NOT NULL,
	attribute VARCHAR(8) NOT NULL,
	value TEXT NOT NULL,
	source VARCHAR(10),
	confidence FLOAT,
	status VARCHAR(10),
	reviewed_by TEXT,
	reviewed_at DATETIME,
	created_at DATETIME,
	"LinkDataset_id" TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(element) REFERENCES "Element" (global_id),
	FOREIGN KEY("LinkDataset_id") REFERENCES "LinkDataset" (id)
);
CREATE INDEX "ix_Assignment_id" ON "Assignment" (id);

CREATE TABLE "ActivityLink" (
	id TEXT NOT NULL,
	activity TEXT NOT NULL,
	role VARCHAR(6) NOT NULL,
	source VARCHAR(10),
	confidence FLOAT,
	split VARCHAR(13),
	rule TEXT,
	status VARCHAR(10),
	reviewed_by TEXT,
	reviewed_at DATETIME,
	created_at DATETIME,
	"LinkDataset_id" TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(activity) REFERENCES "Activity" (task_code),
	FOREIGN KEY("LinkDataset_id") REFERENCES "LinkDataset" (id)
);
CREATE INDEX "ix_ActivityLink_id" ON "ActivityLink" (id);

CREATE TABLE "Tie" (
	id INTEGER NOT NULL,
	element TEXT NOT NULL,
	"LinkDataset_id" TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(element) REFERENCES "Element" (global_id),
	FOREIGN KEY("LinkDataset_id") REFERENCES "LinkDataset" (id)
);
CREATE INDEX "ix_Tie_id" ON "Tie" (id);

CREATE TABLE "LinkDataset_unlinked_activities" (
	"LinkDataset_id" TEXT,
	unlinked_activities_task_code TEXT,
	PRIMARY KEY ("LinkDataset_id", unlinked_activities_task_code),
	FOREIGN KEY("LinkDataset_id") REFERENCES "LinkDataset" (id),
	FOREIGN KEY(unlinked_activities_task_code) REFERENCES "Activity" (task_code)
);
CREATE INDEX "ix_LinkDataset_unlinked_activities_unlinked_activities_task_code" ON "LinkDataset_unlinked_activities" (unlinked_activities_task_code);
CREATE INDEX "ix_LinkDataset_unlinked_activities_LinkDataset_id" ON "LinkDataset_unlinked_activities" ("LinkDataset_id");

CREATE TABLE "LinkDataset_unlinked_elements" (
	"LinkDataset_id" TEXT,
	unlinked_elements_global_id TEXT,
	PRIMARY KEY ("LinkDataset_id", unlinked_elements_global_id),
	FOREIGN KEY("LinkDataset_id") REFERENCES "LinkDataset" (id),
	FOREIGN KEY(unlinked_elements_global_id) REFERENCES "Element" (global_id)
);
CREATE INDEX "ix_LinkDataset_unlinked_elements_unlinked_elements_global_id" ON "LinkDataset_unlinked_elements" (unlinked_elements_global_id);
CREATE INDEX "ix_LinkDataset_unlinked_elements_LinkDataset_id" ON "LinkDataset_unlinked_elements" ("LinkDataset_id");

CREATE TABLE "Assignment_reasons" (
	"Assignment_id" TEXT,
	reasons TEXT,
	PRIMARY KEY ("Assignment_id", reasons),
	FOREIGN KEY("Assignment_id") REFERENCES "Assignment" (id)
);
CREATE INDEX "ix_Assignment_reasons_reasons" ON "Assignment_reasons" (reasons);
CREATE INDEX "ix_Assignment_reasons_Assignment_id" ON "Assignment_reasons" ("Assignment_id");

CREATE TABLE "ActivityLink_elements" (
	"ActivityLink_id" TEXT,
	elements_global_id TEXT NOT NULL,
	PRIMARY KEY ("ActivityLink_id", elements_global_id),
	FOREIGN KEY("ActivityLink_id") REFERENCES "ActivityLink" (id),
	FOREIGN KEY(elements_global_id) REFERENCES "Element" (global_id)
);
CREATE INDEX "ix_ActivityLink_elements_ActivityLink_id" ON "ActivityLink_elements" ("ActivityLink_id");
CREATE INDEX "ix_ActivityLink_elements_elements_global_id" ON "ActivityLink_elements" (elements_global_id);

CREATE TABLE "ActivityLink_reasons" (
	"ActivityLink_id" TEXT,
	reasons TEXT,
	PRIMARY KEY ("ActivityLink_id", reasons),
	FOREIGN KEY("ActivityLink_id") REFERENCES "ActivityLink" (id)
);
CREATE INDEX "ix_ActivityLink_reasons_ActivityLink_id" ON "ActivityLink_reasons" ("ActivityLink_id");
CREATE INDEX "ix_ActivityLink_reasons_reasons" ON "ActivityLink_reasons" (reasons);

CREATE TABLE "Tie_candidates" (
	"Tie_id" INTEGER,
	candidates_task_code TEXT,
	PRIMARY KEY ("Tie_id", candidates_task_code),
	FOREIGN KEY("Tie_id") REFERENCES "Tie" (id),
	FOREIGN KEY(candidates_task_code) REFERENCES "Activity" (task_code)
);
CREATE INDEX "ix_Tie_candidates_candidates_task_code" ON "Tie_candidates" (candidates_task_code);
CREATE INDEX "ix_Tie_candidates_Tie_id" ON "Tie_candidates" ("Tie_id");

