-- READ-ONLY PROPOSAL; not executed. Requires additive migration 003 first.
-- Use versions for historical evidence, current entities for current relationships.
-- Legacy edges remain interpretable. Do not union cooccurrence as person equivalence.
SELECT
  il.*,
  COALESCE(il.identifier_type_from, il.left_namespace) AS resolved_type_from,
  COALESCE(il.identifier_value_from, il.left_id) AS resolved_value_from,
  COALESCE(il.identifier_type_to, il.right_namespace) AS resolved_type_to,
  COALESCE(il.identifier_value_to, il.right_id) AS resolved_value_to
FROM `up-data-intelligence-dev.up_core.identity_links` AS il
WHERE il.source_system = 'upzero'
AND (
  (COALESCE(il.source_entity_type, 'analytics_fact') = 'analytics_fact' AND EXISTS (
    SELECT 1 FROM `up-data-intelligence-dev.up_core.analytics_events` AS e
    WHERE e.store_id = il.store_id AND e.source_system = il.source_system
      AND e.fact_id = il.source_fact_id AND e.version_id = il.source_version_id
  ))
  OR (il.source_entity_type = 'order' AND EXISTS (
    SELECT 1 FROM `up-data-intelligence-dev.up_core.orders` AS o
    WHERE o.store_id = il.store_id AND o.source_system = il.source_system
      AND o.order_id = il.source_entity_id AND o.version_id = il.source_version_id
  ))
);
