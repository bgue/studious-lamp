CREATE TABLE IF NOT EXISTS cur_action_invocation_target (
  target_id TEXT COLLATE "C" PRIMARY KEY,
  invocation_id TEXT COLLATE "C" NOT NULL,
  record_id TEXT COLLATE "C" NOT NULL,
  record_key TEXT COLLATE "C",
  record_type TEXT COLLATE "C",
  record_version BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cur_action_invocation_target_action_target_pair ON cur_action_invocation_target (invocation_id, record_id);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_target_invocation_id ON cur_action_invocation_target (invocation_id);

CREATE INDEX IF NOT EXISTS ix_cur_action_invocation_target_record ON cur_action_invocation_target (record_id, invocation_id);
