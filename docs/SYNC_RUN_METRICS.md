# Auditoria pós-falha e métricas por etapa

## Evidência recebida e verificação pendente

Auditoria fornecida pelo usuário para MX Fashion: 1 envelope RAW, 0 analytics_events no CORE, run affd46d5-3371-448c-aa2b-0afb7e7625db failed, records_read/written/failed=0, início 2026-09-28 20:41:54 e término 20:42:10 (timezone não informado). Esses resultados são evidência fornecida pelo usuário, não contagens novamente consultadas pelo assistente.

Foi tentada uma consulta SELECT estritamente DEV, filtrada por store/run, com saída apenas de metadados, hashes de cursores, contagens e bytes. ADC está disponível, mas o BigQuery retornou Forbidden. Nenhum payload real foi retornado, salvo ou mostrado. Não houve alteração de IAM. Para concluir, uma identidade aprovada precisa de bigquery.jobs.create no projeto e leitura das tabelas RAW/OPS necessárias. Alternativamente executar a query abaixo no Cloud Shell/console com a identidade já autorizada.

**Ainda não confirmados diretamente:** vínculo daquele RAW com o run, raw_record_id, número de facts, tamanho do payload, cursor/next_cursor e estado efetivo do checkpoint. Não assumir que 1 envelope significa 1 fact nem que contém exatamente 1000 facts.

O diagnóstico explica por que zero não implica ausência de leitura: na versão antiga, RAW e checkpoint pending eram persistidos numa transação. records_read/pages/bytes só eram atualizados na transação posterior que promove CORE. Quando essa transação falhava antes do envio por lote >8.000.000 bytes, o tratamento de exceção recarregava o sync_run persistido antes da promoção, voltando aos contadores zero. records_written significava entidades CORE novas, nunca envelopes RAW. records_failed contava falhas de transformação por registro; não contava falhas de infraestrutura. Portanto records_failed=0 com status=failed é possível e correto para essa métrica específica.

Os dados fornecidos são compatíveis com **RAW capturado e falha na primeira promoção CORE**. Confirmação exata requer verificar pending_raw_id e RAW.run_id. O código do erro determina o limite excedido (>8.000.000 bytes da lista JSON de records), mas não seu tamanho exato histórico. O lote CORE expande cada fact para múltiplas tabelas e serializa duas vezes seus JSONs. A nova instrumentação registra a fase e o tamanho de transporte para futuras execuções.

## Consulta segura (não executada com sucesso)

Arquivo: `sql/diagnostics/mx_fashion_raw_metadata.sql`. Retorna:

- run_id, raw_record_id, request_id e ingested_at;
- quantidade de facts no array payload.data;
- bytes_read (resposta HTTP original) e BYTE_LENGTH(TO_JSON_STRING(payload)) (JSON armazenado sanitizado; medidas diferentes);
- from/to/limit explícito dos filtros;
- presença, comprimento e SHA256 de cursor/next_cursor, sem exibir tokens opacos;
- status/pending_raw_id/completed_to do checkpoint e se aponta para esse RAW.

```bash
bq --project_id=up-data-intelligence-dev --location=southamerica-east1 query \
  --use_legacy_sql=false --maximum_bytes_billed=1000000000 --format=prettyjson \
  < sql/diagnostics/mx_fashion_raw_metadata.sql
```

Se limit estiver ausente nos filtros salvos, o conector antigo solicitava explicitamente 1000; isso não prova que a resposta trouxe 1000. Compare hashes para verificar continuidade sem revelar o conteúdo do cursor.

Para reconstruir o lote da promoção **somente em memória**, com a hipótese auditada de CORE vazio:

```bash
uv run python -m scripts.audit_failed_facts
```

O script executa apenas SELECT no DEV, carrega RAW/OPS em memória e chama somente transform, nunca run/replay/write. Não grava os dados lidos em disco. A saída contém apenas metadados, quantidades por tabela e o tamanho do guard antigo reconstruído. Exceções não exibem mensagens/payload. Timestamps transitórios da transformação original não estão registrados, portanto o tamanho reconstruído não é o tamanho exato histórico da requisição. Não tomar a hipótese de CORE vazio como leitura atual do CORE. Não usar nem publicar dumps do envelope real para testes.

## Semântica v2

Todas as métricas são por run. São contadores de progresso **duravelmente confirmado**, não de tentativas HTTP. Entradas repetidas na fonte contam como entradas lidas; não significam facts únicos no CORE.

| Coluna | Significado / momento de persistência |
|---|---|
| metrics_version | 2; NULL em runs antigos mantém semântica antiga |
| source_records_read | Soma das entradas payload.data dos envelopes novos capturados; commit junto com RAW |
| source_bytes_read | Soma bytes_read das respostas desses envelopes; não inclui bytes de tentativas falhas |
| raw_pages_written | Número de envelopes novos escritos, inclusive página vazia terminal |
| raw_payload_bytes | Soma bytes UTF-8 de canonical(payload sanitizado), diferente da resposta HTTP |
| core_records_processed | Entradas processadas em promoções confirmadas, incluindo inalteradas/inválidas |
| core_records_inserted | Entidades principais novas (facts/customers/orders), não todas as linhas derivadas |
| core_records_updated | Entidades principais atualizadas por mudança de conteúdo/versão |
| core_records_failed | Entradas cuja transformação falhou; problemas de infraestrutura são status/error_summary |
| core_pages_processed | Número de envelopes cuja promoção foi concluída; não implica dados novos |
| replay_records_read | Entradas lidas de RAW por replay confirmado; replay não incrementa captura da API/RAW |

Aliases legados **somente em metrics_version=2**: records_read=source_records_read, records_written=core_records_inserted, records_updated=core_records_updated, records_failed=core_records_failed, pages=raw_pages_written, bytes=source_bytes_read. Não reinterpretar runs históricos com versão NULL como v2. No replay v2, source_records_read/raw_pages_written/records_read/pages são zero; usar replay_records_read/core_pages_processed para seu progresso.

records_written=0 pode significar que tudo já existia (replay idempotente), ou que não houve promoção; usar core_records_processed/status para distinguir. Um CORE que escreve estado atual, histórico, touchpoint e links para 1 fact conta 1 inserção de entidade, não o total de linhas físicas. Correções repetidas da mesma entidade ao longo de várias páginas contam atualizações por observação, não necessariamente IDs únicos.

## Atomicidade e retomada

RAW, checkpoint pending e contadores de captura agora pertencem à mesma transação. CORE, run e checkpoint avançado continuam em outra transação. Falha RAW deixa contadores de captura anteriores; falha CORE preserva contadores RAW e mantém contadores CORE anteriores. ACK perdido é reconciliado pelo mesmo job_id. Resultado desconhecido não gera sobrescrita de contadores e conserva o lease.

Uma retomada v2 com pending_raw_id NÃO incrementa captura novamente. Em run legado incompleto, antes de retomar, o código reconstrói uma única vez a captura a partir dos envelopes existentes desse mesmo store/run, preserva os contadores antigos de CORE e grava metrics_version=2 na transação de início da retomada. Isso não foi executado no run real. Runs antigos completos não são automaticamente reescritos; permanecerão históricos legados.

Replay cria relatório próprio, não muda os contadores do run original e não avança o checkpoint original. Se falhar, o relatório do replay conserva somente progresso confirmado e recebe failed; falha de infraestrutura não vira contagem de facts inválidos. Retomar o run original, com os mesmos filtros/page_limit/conexão e sem --refresh, é o caminho para resolver seu checkpoint pendente.

## Migração necessária — preparada, NÃO executada

A separação explícita exige **11 colunas INT64 nullable adicionais** em up_ops.sync_runs (metrics_version e dez contadores). Fonte de schema, JSON Terraform e SQL de criação foram atualizados. Nenhum dado/coluna existente foi removido ou renomeado.

`sql/migrations/002_sync_run_stage_metrics.sql` contém somente ADD COLUMN IF NOT EXISTS. Revisar/aprovar e aplicar antes de executar a nova imagem. Alternativamente fazer a atualização aditiva do schema pelo Terraform após plano aprovado; não executar ambos os caminhos sem coordenar a gestão do schema. Nenhum plano/apply ou DDL foi executado nesta etapa. Após DDL externa, reconciliar o state/configuração Terraform em uma etapa autorizada. Executar a imagem nova contra schema antigo falhará no MERGE.

O histórico fica NULL nas colunas novas até uma retomada autorizada do run ou uma futura migração de métricas explicitamente aprovada. Não preencher zero indiscriminadamente, pois isso inventaria ausência de captura. Preservar especialmente o RAW do incidente para replay/checagem de idempotência.

## Verificação local

120 testes passaram, incluindo RAW confirmado + CORE falho, falha RAW, retry sem recontagem, ACK perdido, migração lógica de run legado pendente, replay sem leitura da API, replay falho, duplicatas na fonte, rejeição de transformação e saída diagnóstica sem PII/cursor. Ruff lint/formatação passaram; mypy passou em 36 arquivos (src + script diagnóstico). Rede é bloqueada na suíte.

Arquivo de schema alterado: infra/terraform/schemas/sync_runs.json. SQL de criação: sql/ops/sync_runs.sql. Módulo novo: src/ingestion/metrics.py. Engine, logs e testes foram atualizados sobre a correção de batches ainda local. A imagem precisa ser reconstruída, mas não foi feito build/deploy/push nem executado Job. Nenhuma API Key, Secret Version, conexão UP Zero/Meta ou remoção de dados ocorreu.
