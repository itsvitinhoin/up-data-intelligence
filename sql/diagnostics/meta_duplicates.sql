-- PROPOSTA, NÃO EXECUTADA. Requer tabelas Meta provisionadas em etapa futura.
-- Somente contagens/categorias; não retorna IDs de anúncio, URLs, cookies ou PII.
-- Parâmetros: @store (STRING), @account (STRING), @date_from/@date_to (DATE).
-- Aplicar maximum_bytes_billed no cliente.
WITH duplicate_keys AS (
  SELECT 'duplicate_meta_accounts' AS rule_id, COUNT(*) AS copies
  FROM `${project_id}.up_core.meta_accounts`
  WHERE store_id = @store AND account_id = @account GROUP BY row_key HAVING COUNT(*) > 1
  UNION ALL
  SELECT 'duplicate_campaigns', COUNT(*) FROM `${project_id}.up_core.meta_campaigns`
  WHERE store_id = @store AND account_id = @account GROUP BY row_key HAVING COUNT(*) > 1
  UNION ALL
  SELECT 'duplicate_adsets', COUNT(*) FROM `${project_id}.up_core.meta_adsets`
  WHERE store_id = @store AND account_id = @account GROUP BY row_key HAVING COUNT(*) > 1
  UNION ALL
  SELECT 'duplicate_ads', COUNT(*) FROM `${project_id}.up_core.meta_ads`
  WHERE store_id = @store AND account_id = @account GROUP BY row_key HAVING COUNT(*) > 1
  UNION ALL
  SELECT 'duplicate_meta_insights', COUNT(*) FROM `${project_id}.up_core.meta_insights_daily`
  WHERE store_id = @store AND account_id = @account
    AND date_start BETWEEN @date_from AND @date_to
  GROUP BY row_key HAVING COUNT(*) > 1
)
SELECT rule_id, COUNT(*) AS duplicated_keys, SUM(copies - 1) AS extra_rows
FROM duplicate_keys GROUP BY rule_id;
