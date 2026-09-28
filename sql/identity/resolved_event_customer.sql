-- READ-ONLY PROPOSAL; not executed or installed as a view.
-- Same semantics as resolve_customer(). Returns current-order customer, NOT login identity.
-- For touchpoints, replace only the events CTE source with up_core.touchpoints.
-- Explicit projection: no customer PII is copied. Views/IAM require separate approval.
WITH events AS (
  SELECT store_id, source_system, fact_id, order_id, version_id
  FROM `up-data-intelligence-dev.up_core.analytics_events`
), orders AS (
  SELECT *, COUNT(*) OVER (PARTITION BY store_id, source_system, order_id) AS matches
  FROM `up-data-intelligence-dev.up_core.orders`
), customers AS (
  SELECT *, COUNT(*) OVER (PARTITION BY store_id, source_system, customer_id) AS matches
  FROM `up-data-intelligence-dev.up_core.customers`
)
SELECT e.store_id, e.source_system, e.fact_id, e.version_id AS event_version_id, e.order_id,
  c.customer_id AS customer_id_resolved,
  o.version_id AS order_version_id, c.version_id AS customer_version_id,
  CASE WHEN e.store_id IS NULL OR e.store_id = '' OR e.source_system IS DISTINCT FROM 'upzero'
         THEN 'unsupported_source_or_store'
       WHEN e.order_id IS NULL OR e.order_id = '' THEN 'missing_order_id'
       WHEN o.order_id IS NULL THEN 'order_missing_or_ambiguous'
       WHEN c.customer_id IS NULL THEN 'customer_missing_or_ambiguous'
       ELSE 'resolved_via_order' END AS resolution_status,
  IF(c.customer_id IS NOT NULL, 'observed_event_order_customer', NULL) AS evidence_type
FROM events AS e
LEFT JOIN orders AS o ON e.store_id = o.store_id AND e.source_system = o.source_system
  AND e.source_system = 'upzero' AND e.store_id != ''
  AND e.order_id = o.order_id AND e.order_id != '' AND o.matches = 1
LEFT JOIN customers AS c ON o.store_id = c.store_id AND o.source_system = c.source_system
  AND o.customer_id = c.customer_id AND c.customer_id != '' AND c.matches = 1;
