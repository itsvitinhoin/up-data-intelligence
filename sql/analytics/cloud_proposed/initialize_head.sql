-- PROPOSTA SOMENTE. Executar uma única vez sob exclusão externa/manual por store/policy.
-- BigQuery não impõe unicidade; duas inicializações concorrentes NÃO são seguras.
ASSERT NOT EXISTS(
 SELECT generation FROM `up-data-intelligence-dev.up_analytics.analytics_publications`
 WHERE store_id=@store AND policy_hash=@policy AND record_kind='HEAD'
) AS 'head_already_exists';
INSERT INTO `up-data-intelligence-dev.up_analytics.analytics_publications`
(record_kind,store_id,policy_hash,generation,status)
VALUES ('HEAD',@store,@policy,0,'initialized');
