-- PREPARADO, NÃO EXECUTADO. Run once under external/manual exclusive access.
-- Never run simultaneous initializers: BigQuery does not enforce uniqueness.
ASSERT @store='mx-fashion'
  AND @policy='3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c'
  AS 'unapproved_initial_head';
BEGIN TRANSACTION;
ASSERT (
 SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications`
 WHERE store_id=@store AND policy_hash=@policy AND record_kind='HEAD'
)<=1 AS 'duplicate_head';
INSERT INTO `up-data-intelligence-dev.up_analytics.analytics_publications`
(record_kind,store_id,policy_hash,generation,status)
SELECT 'HEAD',@store,@policy,0,'initialized'
WHERE NOT EXISTS (
 SELECT generation FROM `up-data-intelligence-dev.up_analytics.analytics_publications`
 WHERE store_id=@store AND policy_hash=@policy AND record_kind='HEAD'
);
ASSERT (
 SELECT COUNT(*) FROM `up-data-intelligence-dev.up_analytics.analytics_publications`
 WHERE store_id=@store AND policy_hash=@policy AND record_kind='HEAD'
)=1 AS 'head_required';
COMMIT TRANSACTION;
-- No UPDATE, DELETE or RECEIPT insertion: existing generations are preserved.
