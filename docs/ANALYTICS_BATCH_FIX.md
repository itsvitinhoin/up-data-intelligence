# Analytics Facts: limite de batch e retomada

## Diagnóstico e limites da evidência

Execução reportada: up-foundation-dev-sync-p8chg, backfill analytics_facts de 2026-09-25T12:00:00Z até 13:00:00Z. A mensagem antiga provém exclusivamente de `BigQueryRepository.write`, no teste `len(canonical(records).encode()) > 8_000_000`, antes de enviar aquela query. `records` é a lista de strings JSON contendo target_table e record, portanto há serialização/escape adicional; não equivale ao tamanho HTTP da página.

Isso é um limite preventivo LOCAL de 8.000.000 bytes, não uma resposta de quota excedida do BigQuery. O limite publicado da requisição BigQuery é 10 MB incluindo parâmetros/configuração. CORE multiplica cada fact em estado atual, versão, touchpoint, vínculo de pedido e até três vínculos de identidade; pode ultrapassar 8 MB mesmo que RAW caiba. O teste antigo tampouco media todo o envelope real da requisição e subestimava escapes Unicode.

A investigação do código ocorreu antes da alteração. Tentativa de leitura apenas dos metadados dos logs DEV foi bloqueada: gcloud sem conta ativa. Posteriormente foi tentado SELECT de metadados usando ADC, também bloqueado (Forbidden), conforme SYNC_RUN_METRICS.md. Não houve acesso aos dados reais. Portanto **não foi possível determinar se a operação daquela execução foi RAW+checkpoint ou CORE+run+checkpoint, nem o número exato de bytes além de >8.000.000**. O warning em repository.py:232 prova que algum write menor chegou a submeter query; não identifica o write que excedeu o limite.

O diagnóstico read-only `sql/diagnostics/failed_analytics_backfill.sql` retorna candidatos, contagens e tamanhos, nunca payloads ou credenciais. Correlacionar started_at/run_id com logs; o nome da execução Cloud Run não está no schema antigo. O tamanho JSON retornado pelo SQL não é a medida exata da lista serializada pelo Python. Não apagar RAW, CORE ou checkpoint. Nenhuma query diagnóstica foi executada.

## Paginação e configuração

O OpenAPI documenta limit mínimo 1, máximo 1000 e default da API 200. O conector existente solicita explicitamente 1000 por padrão para analytics_facts e 200 para commerce. Esse comportamento foi preservado para não mudar silenciosamente os planos/checkpoints existentes. Cursor/next_cursor opacos e janela fixa [from,to) continuam iguais; não passamos ao cursor seguinte antes da promoção completa da página.

`Settings.page_limit` já existia; agora é possível sobrescrevê-lo com `--page-limit 1..1000`, inclusive via argumentos de Job em etapa futura autorizada. Commerce continua limitado a 200. Sem override, o limite atual é preservado. A janela temporal não é reduzida. **Ao retomar o incidente, não mudar page_limit, filtros, mode, loja/conexão ou usar --refresh**: limit explícito faz parte da chave de plano. Retomar com os mesmos argumentos depois de reconstrução/teste/deployment autorizado.

## Escrita nova

1. Validar colunas e deduplicar por tabela/store_id/row_key.
2. Medir configuração de query serializada com parâmetros, escapes JSON/Unicode e margem de 64 KiB para o envelope jobs.insert. Orçamento de 8.000.000 bytes por requisição, abaixo dos 10 MB do serviço.
3. Se couber, manter o caminho rápido: um script BEGIN/MERGE/COMMIT, como antes.
4. Se exceder, criar sessão BigQuery na mesma região e tabela **TEMP** privada write_fragments. Dividir inclusive uma linha RAW grande em fragmentos de texto JSON; agrupar os fragmentos pelo orçamento real do transporte. O MERGE temporário usa índices de linha/fragmento, idempotentes. Dados já foram sanitizados antes dessa etapa.
5. Reconstituir exatamente as strings (incluindo Unicode) em TEMP write_records, na ordem dos fragmentos. Nenhum fragmento é descartado/truncado.
6. Somente quando todo o lote está disponível executar a transação final com todos os MERGEs duráveis, incluindo checkpoint. Mesmos schemas/chaves existentes. RAW+checkpoint pending continua uma transação distinta e anterior a CORE+run+checkpoint. Não há commit durável por fragmento.
7. Encerrar a sessão após resultado conhecido. Falha de limpeza é registrada sem payload e não converte commit confirmado em falha; temporários de sessão têm expiração gerenciada pelo BigQuery.

O protocolo de batches não exige novas tabelas permanentes, buckets ou dependências Python. O complemento posterior de [métricas por etapa](SYNC_RUN_METRICS.md) exige colunas aditivas em sync_runs antes de executar a imagem nova; essa migração está preparada, não executada. A identidade atual tem bigquery.jobs.create via jobUser, necessário para suas próprias sessões. Políticas organizacionais e execução SQL/session reais precisam de validação DEV posterior: testes offline não validam o parser SQL nem o IAM real. Tabelas temporárias têm custo de armazenamento/query.

O limite de transporte não é mais limite de lote. Entretanto, BigQuery ainda tem limites físicos: a implementação rejeita uma **linha lógica** >64.000.000 bytes UTF-8, com erro específico, antes de escrever qualquer parte durável (margem abaixo do limite aproximado de linha de 100 MB). Uma página RAW é uma linha lógica no schema atual. Eventos/campos arbitrariamente ilimitados não cabem nesse schema; se esse limite for atingido, será necessária evolução de armazenamento RAW, sem descarte. As páginas normais com 1000 facts e RAW >8 MB estão cobertas. O processamento permanece limitado à página, não à janela inteira; não promete memória infinita. A reconciliação de qualidade global ainda materializa dados da loja e deve ser dimensionada separadamente antes de milhões de eventos.

## job_id, job_retry e falhas ambíguas

Escolhido job_id explícito por operação + job_retry=None em Client.query **e** QueryJob.result. Não usamos job_id_prefix: retries automáticos de jobs criariam novos IDs, o que dificultaria resolver o resultado de uma gravação de fragmento ou commit cujo ACK foi perdido.

Retries de transporte da biblioteca continuam habilitados. Em Conflict/erros transitórios, reconsultar o MESMO ID e localização com get_job; verificar DONE/error_result; nunca emitir novo ID para substituir um resultado desconhecido. Até três tentativas externas com backoff, além dos retries de transporte da biblioteca. Um job definitivamente falho exige retomada do lote numa nova tentativa, com IDs novos e MERGEs idempotentes. Um DONE bem-sucedido é aceito mesmo após ACK perdido.

Se o resultado permanece desconhecido: erro bigquery_write_outcome_unknown, log seguro com job_id, **sem sobrescrever run/checkpoint**, sem abortar a sessão potencialmente em commit e **sem liberar o lease da loja**. Operador deve consultar o job, aguardar término e confirmar resultado antes de remover o lease por geração e retomar. Um processo morto abruptamente também deixa o lease; nunca takeover automático. Isso evita concorrência entre retry e commit antigo ainda em andamento.

## Estado parcialmente persistido e retry

Na versão antiga, o lote rejeitado pelo teste de tamanho não enviou query. Escritas anteriores podem ter ocorrido:

- Falha ao capturar RAW: registry e run inicial e páginas anteriores podem estar persistidos; RAW da página rejeitada não foi escrito, cursor não avançou. Retry busca novamente a página atual.
- Falha ao promover CORE: RAW completo e pending_raw_id podem estar persistidos. CORE da página rejeitada não foi escrito; páginas anteriores podem estar completas. Retry consome o RAW salvo, sem buscar novamente essa página, e só depois segue next_cursor.
- Código antigo usa transação para cada write; o erro de tamanho não faz commit parcial dentro daquele write. Não concluir que toda a janela ficou vazia.

Na versão corrigida, falha no meio de staging deixa apenas temporários, sem alterações duráveis daquele write. Falha na transação final reverte o conjunto. Uma sessão perdida é reconstituída no retry; RAW pendente é a fonte durável para retomar promoção. Facts usam store/fact e source_system=upzero; somente uma conexão ativa UP Zero por loja é permitida pelo registry. Não mudamos chaves históricas nem misturamos fontes. Replay preserva as proteções contra observações antigas sobrescreverem versões mais recentes.

## Observabilidade e verificação

Resultado local da correção combinada: 120 testes passaram com FutureWarning tratado como erro; Ruff lint/formatação passaram; mypy strict passou em 36 arquivos (source e script diagnóstico). Nenhum teste acessou rede.

Arquivos alterados: src/bigquery/repository.py, novo src/bigquery/writer.py, src/ingestion/engine.py, src/jobs/cli.py, src/observability/logging.py, src/security/lease.py, tests/integration/test_batched_writer.py, tests/unit/test_cli.py, tests/unit/test_cloud_adapters.py, README.md, este documento e sql/diagnostics/failed_analytics_backfill.sql. Na etapa posterior de métricas, o schema Terraform de sync_runs foi atualizado; consultar SYNC_RUN_METRICS.md.

Novos logs allowlist: sync_started(run_id), page_persistence(phase raw_capture/core_promotion, resource, raw_record_id, records, payload_bytes), bigquery_write_job(phase, job_id, request_bytes), bigquery_write_staged e bigquery_chunk_staged. Nenhum SQL parametrizado, cursor, URL, payload ou secret é logado. Isso permite localizar exatamente a fase/tamanho em incidentes futuros.

Testes novos usam o writer/engine reais com modelo offline de sessões e commit atômico; cobrem páginas pequenas, grandes, 1000 facts, cursor, CLI page-limit, RAW individual >8 MB, Unicode/escapes, orçamento por request, falha no meio de RAW/CORE, rollback do commit, checkpoint, ACK perdido no envio/resultado, resultado desconhecido, lease retido, replay e ausência de perda/duplicação nas tabelas derivadas. O modelo NÃO executa SQL no serviço BigQuery.

É necessário reconstruir a imagem Docker para incorporar a correção. Nenhum build, push, deployment, execução Cloud Run, alteração GCP, API Key ou Secret Version foi realizado nesta etapa. Antes de produção, validar o caminho de sessão em DEV com autorização separada e medir latência/custo. Para a correção combinada, revisar a migração aditiva de métricas antes do deployment; não executar apply nesta etapa.

Fontes: [quotas BigQuery](https://docs.cloud.google.com/bigquery/quotas), [sessões e permissões](https://docs.cloud.google.com/bigquery/docs/sessions-intro), [transações](https://docs.cloud.google.com/bigquery/docs/transactions), [Client.query](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.client.Client). SDK instalado 3.45.2 inspecionado localmente.
