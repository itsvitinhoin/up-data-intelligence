# Resource-scoped quality gate e status do backfill

Implementação local, sem migration, deploy, backfill ou alteração GCP. Não modifica dados, checkpoints, parâmetros da MX Fashion, schemas, IAM nem purchase_order_id_effective_at. Execuções de testes usam fixtures sintéticas e rede bloqueada.

## Investigação histórica encerrada quanto ao caminho de saída

Evidências posteriores fornecidas pelo responsável confirmaram a imagem DEV.3 e exit code 1, 28 child runs correlacionados com logs, quatro completed_with_errors com uma falha cada no snapshot at-exit. Os quatro erros foram reproduzidos a partir do RAW: state/city opcionais vazios tratados como identificadores inválidos. Ver [causa raiz e recuperação](CUSTOMER_OPTIONAL_EMPTY_FIX.md).

ROOT CAUSE: optional empty state/city normalization.
NOT ROOT CAUSE: Orders sync_delayed, global quality warnings, invalid_meta_parser.

O CLI anterior já retornava 1 se qualquer child não fosse completed. O quality gate por recurso é uma melhoria independente de política e observabilidade, não a correção da causa histórica de ppq2j.

Antes, `--mode quality` retornava 0 se a consulta persistia resultados, mesmo com alerts. Agora ele usa o mesmo gate, respeitando `--resource` (default all), com ingestion_status=not_requested.

## Política de blocking

Severity é mantida. Uma regra só bloqueia se failed_count > 0 e severity=alert e seu escopo é aplicável. Regras globais conhecidas antes gravadas com resource=all agora recebem seu recurso real; registros históricos não são reescritos. O gate reconhece também nomes antigos/all e analytics_events como alias de analytics_facts.

| Regra | Recurso bloqueado |
|---|---|
| duplicate_customers | customers |
| duplicate_orders | orders |
| duplicate_facts | analytics_facts |
| purchase_without_order_id_after_effective / purchase_item_without_order_id_after_effective | analytics_facts |
| sync_delayed | somente o recurso identificado na ocorrência |
| duplicate_order_items | orders, quando encontrado nos resultados dos child runs selecionados |
| conflicting_duplicate_in_page, conflicting_source_version, invalid_transformation_or_monetary_value, fact_without_technical_store | recurso do child run selecionado |

`resource=all` considera os três recursos; qualquer blocking aplicável bloqueia. Alerts futuros de escopo all não mapeado bloqueiam conservadoramente qualquer execução até definir o escopo, pois não é seguro classificá-los automaticamente como irrelevantes.

Warnings permanecem não bloqueantes: purchase/purchase_item sem order_id antes da correção ou effective_at=null; invalid_meta_parser; order_id_without_order; duplicate_event_ids; order_without_customer; observações stale e outros warnings existentes. Nenhum dado histórico é apagado ou artificialmente corrigido.

Dependências: Orders não exige freshness de Customers; preserva customer_id para resolução posterior. Facts não exige freshness de Orders; referências ainda sem pedido ficam pending/warning. Customers não depende de Orders/Facts. Esses comportamentos evitam dependência circular no bootstrap. Não são exceções que descartam dados ou convertem warnings em pass silencioso.

Alert de infraestrutura de tentativa anterior persistido no mesmo run_id não bloqueia sozinho uma retomada concluída: status de ingestão atual e checks de integridade determinam o gate. O alerta continua no histórico. Resultados inline bloqueantes conhecidos são lidos apenas para os child runs selecionados, não para todo o histórico da loja.

## Estados e observabilidade

- ingestion_status: completed, failed ou not_requested (quality-only).
- resource_quality_status: pass/fail; unknown quando a avaliação não pode ser concluída.
- global_quality_status: pass/warning/alert; unknown se consulta/persistência falhar. Inclui checks globais e histórico de qualidade dos child runs selecionados; não apaga alertas de tentativas anteriores.
- blocking_for_requested_resource: decisão explícita no resumo terminal normal.
- exit_code: 0 somente se ingestão solicitada completou e gate passou; 1 para ingestão incompleta, regra blocking aplicável ou exceção que impede afirmar sucesso.

Cada chamada CLI gera parent_execution_id UUID, propagado por ContextVar aos logs internos. Cada sync_finished é emitido imediatamente ao retornar um child, inclusive quando reutiliza um run concluído; sync_started também herda a correlação. O resumo execution_finished separa ingestão de qualidade e do exit code. Em exceção, job_failed registra código seguro e execution_finished retorna exit_code=1/qualidade unknown, sem reclassificar runs completed já persistidos como failed.

Regras globais continuam executadas, gravadas em quality_results e emitidas como data_quality, independentemente do gate específico. Em falha de ingestão/infraestrutura, a avaliação global pode não ser alcançada: status unknown é explícito, não se inventa health pass. O SQL global já existente reconcilia event_order_links; este patch não remove essa função.

Não há coluna parent_execution_id no BigQuery. A correlação é em logs, evitando migration nesta etapa. Não é um parent durável com exactly-once delivery; retenção/perda dos logs limita reconstrução. Se for necessário histórico permanente, propor separadamente tabela de execuções e relações parent→child; não adicionar parent_id singular a sync_runs, pois o mesmo child pode ser reutilizado por várias execuções/retries.

## Windowing e retomada

`windows(..., days=1)` mantém janelas de um dia, truncando a última no limite final. De 2026-09-01T00:00:00Z a 2026-09-29T00:00:00Z são **28 janelas Customers**: start_date=end_date para cada data UTC de 01 a 28. Datas inclusivas da API são calculadas com end menos um microssegundo; limite final da solicitação é exclusivo. Facts usa instantes from/to; Orders converte datas para timezone da loja, podendo sobrepor datas locais entre janelas. Esse planejamento não foi alterado.

Cada plano é hash de store_id, connection_id, recurso, filtros e modo. Filtros incluem limit; mudar page-limit/intervalo/modo pode gerar outro plano. Cada plano tem checkpoint e run_id próprios. Para a mesma solicitação sem --refresh, janelas concluídas retornam o run existente; janela pendente retoma posição/pending_raw_id. RAW persistido antes de CORE pode ser promovido na retomada sem refetch. Checkpoint só avança com a persistência CORE transacional. RAW/CORE/counters não são resetados.

Falha de infraestrutura interrompe o loop, preservando janelas anteriores; nova execução com mesmos argumentos as reutiliza e retoma a incompleta. Transformação com records_failed deixa completed_with_errors/needs_review e requer replay/refresh autorizado; não é retomada automática bem-sucedida. A existência de alguns child runs completed não prova sucesso do parent inteiro. Idempotência e bloqueio por loja existentes foram preservados.

Para execução nova, filtrar logs por parent_execution_id e extrair run_id distintos de sync_started/sync_finished. No Cloud Run também existe o label da execução, útil para o incidente anterior (sem parent_id): filtrar a execução informada, recuperar **todos** os run_ids/statuses e cruzar com up_ops.sync_runs. Janelas cached não emitiam sync_started no código antigo; não prometer reconstrução completa só com esse evento. sync_checkpoints contém filtros e plan_key; correlação por horário isolado é heurística.

O resumo terminal normal soma contadores por run_id único: source_records_read, raw_pages_written, core_records_processed/inserted/updated/failed. `metrics_scope=cumulative_unique_child_runs`: são totais duráveis dos runs, incluindo trabalho concluído/reutilizado antes desta tentativa; não representam consumo de API ou inserts exclusivos desta invocação. Não somar parent totals de retries entre si. Em exceção não se publica um total parcial como se fosse total completo; usar child runs persistidos para analisar a janela falha. Contadores de versões antigas nulos não devem ser interpretados como prova de volume zero.

## Investigação de invalid_meta_parser

O campo implementado é parse_status, não parser_valid. O quality check alerta warning para quatro statuses:

| Status | Condições no parser 1.0.0 |
|---|---|
| invalid_url | valor não textual, >32768 caracteres, escape % inválido, scheme fora de http/https, hostname ausente, userinfo, espaço/controle no netloc, falha de parsing/Unicode, >256 query fields |
| invalid_id | campaign_id/adset_id/ad_id não vazio e não composto apenas por dígitos ASCII |
| placeholder | chaves/colchetes/ângulos ou padrões placeholder/campaign.id/adset.id/ad.id, inclusive em adset_name |
| conflict | repetição de um parâmetro com valores distintos |

URL/param ausente ou vazio é absent, não warning. Repetição com mesmo valor é duplicate, também não warning. IDs STRING preservam zeros. Status usa prioridade conflict > placeholder > invalid_id > duplicate > ok > absent; um único status pode esconder múltiplas categorias no mesmo Fact.

Possível falso positivo reproduzido sinteticamente: `adset_name=Group[Remarketing]` é placeholder pela regra atual, mesmo que seja nome legítimo. Isso não comprova que algum dos seis registros reais pertence a esse caso. Nenhuma mudança no parser, tracking ou dados nesta tarefa.

A tentativa local de leitura retornou Forbidden. Posteriormente, o responsável executou o diagnóstico no Cloud Shell: 6/6 placeholder, todos adset_name:placeholder, sem truncamento nem status_mismatches, iguais no snapshot histórico e atual. Não há confirmação de que sejam nomes legítimos ou macros não resolvidas. Um operador com acesso autorizado pode executar, na raiz do projeto:

```sh
python -m scripts.audit_meta_parser --live \
  --project up-data-intelligence-dev --location southamerica-east1 \
  --store mx-fashion --confirm-store mx-fashion
```

O script faz somente SELECT dos Facts marcados inválidos no CORE, com teto de 1 GB faturável; processa URLs em memória e retorna contagens por status/campo/categoria e divergências de recomputação, sem URLs, IDs ou valores de query. Categorias são não exclusivas; sua soma pode exceder seis. Usa parser atual para comparação, sem UPDATE. `status_mismatches` exige investigação de versão/sanitização; não corrige automaticamente. O script não foi executado com sucesso contra dados reais nesta entrega.

## Validação e liberação

Testes cobrem os três recursos independentes em bootstrap, all bloqueante, qualidade persistida e logada, infraestrutura da avaliação indisponível, child anterior com erro e último completed, aliases/escopos BigQuery, falha no meio das janelas, retomada, contadores, zero duplicatas e correlação do CLI. Categorias de parser usam apenas exemplos sintéticos.

Não há schema migration nem modificação Terraform. Nova imagem será necessária para levar o código ao DEV; nenhum build/deploy executado. Antes de liberar, revisar política (incluindo quality/all e freshness do próprio recurso), manter investigação semântica de adset_name separada e validar a correção de Customers. Replay de backfill antigo totalmente cached pode bloquear por sync_delayed do próprio recurso se a última ingestão estiver antiga; preservar essa semântica explícita até decisão diferente. Consultas globais continuam tendo custo/latência e podem falhar por permissões; nesse caso o processo retorna 1 sem desfazer ingestão concluída.

Para conferir todos os child runs conhecidos do incidente, `sql/diagnostics/backfill_child_status.sql` fornece consultas SELECT parametrizadas. A lista de run_ids deve vir da correlação completa dos logs; o SQL não consegue descobrir um parent inexistente no schema.

Resultado local final: **166 testes passaram** (30 casos novos), Ruff lint e formatting aprovados (52 arquivos), mypy aprovado (39 arquivos), git diff --check aprovado. Nenhum teste live bem-sucedido, migration, build, deploy ou push nesta entrega. A única tentativa de diagnóstico DEV foi SELECT agregado e retornou Forbidden.
