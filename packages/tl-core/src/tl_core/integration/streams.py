"""Stream types and event types of the integration layer (P1-I7, ADR-0017).

Only names: no imports beyond the standard library, so the ledger, the projectors and the webhook
dispatcher can all use them without a cycle. The payloads are described in
``schema/core/events.yaml`` and the generated event catalog.
"""

from __future__ import annotations

# --- stream types (one stream per record, like ``core.WebhookSubscription``) ---------------------

APP_STREAM_TYPE = "core.IntegrationApp"
ACTION_DEFINITION_STREAM_TYPE = "core.ActionDefinition"
ACTION_INVOCATION_STREAM_TYPE = "core.ActionInvocation"
RULE_STREAM_TYPE = "core.Rule"
ENDPOINT_STREAM_TYPE = "core.InboundEndpoint"
DELIVERY_STREAM_TYPE = "core.InboundDelivery"
ENRICHER_STREAM_TYPE = "core.Enricher"
ENRICHMENT_STREAM_TYPE = "core.EnrichmentValue"

# --- event types ----------------------------------------------------------------------------------

APP_REGISTERED = "IntegrationApp.Registered"
APP_REVISED = "IntegrationApp.Revised"
APP_ENABLED = "IntegrationApp.Enabled"
APP_DISABLED = "IntegrationApp.Disabled"
APP_EVENT_TYPES = frozenset({APP_REGISTERED, APP_REVISED, APP_ENABLED, APP_DISABLED})

ACTION_DEFINED = "ActionDefinition.Defined"
ACTION_REVISED = "ActionDefinition.Revised"
ACTION_RETIRED = "ActionDefinition.Retired"
ACTION_SECRET_ROTATED = "ActionDefinition.SecretRotated"
ACTION_DEFINITION_EVENT_TYPES = frozenset(
    {ACTION_DEFINED, ACTION_REVISED, ACTION_RETIRED, ACTION_SECRET_ROTATED}
)

ACTION_REQUESTED = "Action.Requested"
ACTION_RUNNING = "Action.Running"
ACTION_COMPLETED = "Action.Completed"
ACTION_FAILED = "Action.Failed"
ACTION_INVOCATION_EVENT_TYPES = frozenset(
    {ACTION_REQUESTED, ACTION_RUNNING, ACTION_COMPLETED, ACTION_FAILED}
)

RULE_CREATED = "Rule.Created"
RULE_REVISED = "Rule.Revised"
RULE_ENABLED = "Rule.Enabled"
RULE_DISABLED = "Rule.Disabled"
RULE_BLOCKED = "Rule.Blocked"
RULE_EVENT_TYPES = frozenset(
    {RULE_CREATED, RULE_REVISED, RULE_ENABLED, RULE_DISABLED, RULE_BLOCKED}
)

ENDPOINT_CREATED = "InboundEndpoint.Created"
ENDPOINT_REVISED = "InboundEndpoint.Revised"
ENDPOINT_ENABLED = "InboundEndpoint.Enabled"
ENDPOINT_DISABLED = "InboundEndpoint.Disabled"
ENDPOINT_SECRET_ROTATED = "InboundEndpoint.SecretRotated"
ENDPOINT_EVENT_TYPES = frozenset(
    {
        ENDPOINT_CREATED,
        ENDPOINT_REVISED,
        ENDPOINT_ENABLED,
        ENDPOINT_DISABLED,
        ENDPOINT_SECRET_ROTATED,
    }
)

INBOUND_RECEIVED = "Inbound.Received"
INBOUND_APPLIED = "Inbound.Applied"
INBOUND_FAILED = "Inbound.Failed"
INBOUND_RETRIED = "Inbound.Retried"
DELIVERY_EVENT_TYPES = frozenset(
    {INBOUND_RECEIVED, INBOUND_APPLIED, INBOUND_FAILED, INBOUND_RETRIED}
)

ENRICHER_REGISTERED = "Enricher.Registered"
ENRICHER_REVISED = "Enricher.Revised"
ENRICHER_ENABLED = "Enricher.Enabled"
ENRICHER_DISABLED = "Enricher.Disabled"
ENRICHER_EVENT_TYPES = frozenset(
    {ENRICHER_REGISTERED, ENRICHER_REVISED, ENRICHER_ENABLED, ENRICHER_DISABLED}
)

ENRICHMENT_PROPOSED = "Enrichment.Proposed"
ENRICHMENT_ACCEPTED = "Enrichment.Accepted"
ENRICHMENT_REJECTED = "Enrichment.Rejected"
ENRICHMENT_EVENT_TYPES = frozenset({ENRICHMENT_PROPOSED, ENRICHMENT_ACCEPTED, ENRICHMENT_REJECTED})

#: Every event type of the integration layer.
INTEGRATION_EVENT_TYPES = (
    APP_EVENT_TYPES
    | ACTION_DEFINITION_EVENT_TYPES
    | ACTION_INVOCATION_EVENT_TYPES
    | RULE_EVENT_TYPES
    | ENDPOINT_EVENT_TYPES
    | DELIVERY_EVENT_TYPES
    | ENRICHER_EVENT_TYPES
    | ENRICHMENT_EVENT_TYPES
)

#: What webhooks deliver (FANOUT objective): what automation did to the ledger and what an enricher
#: proposed or got accepted. Configuration events (apps, definitions, rules, endpoints, enrichers)
#: and the inbound delivery bookkeeping are in the catalog and the ledger but are never delivered.
INTEGRATION_WEBHOOK_EVENT_TYPES = frozenset(
    {ACTION_REQUESTED, ACTION_COMPLETED, ACTION_FAILED, ENRICHMENT_PROPOSED, ENRICHMENT_ACCEPTED}
)
INTEGRATION_INTERNAL_EVENT_TYPES = INTEGRATION_EVENT_TYPES - INTEGRATION_WEBHOOK_EVENT_TYPES

#: The source prefix of a rule; the depth of a chain is read from it (FANOUT D7).
RULE_SOURCE_PREFIX = "rule:"
