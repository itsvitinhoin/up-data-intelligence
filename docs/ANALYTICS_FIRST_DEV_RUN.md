# Primeira materialização Analytics DEV — preparada, não executada

Estado informado pelo responsável: oito tabelas provisionadas (8 added/0 changed/
0 destroyed), sete dry-runs e sete comparações Python/BigQuery aprovados.
Esta etapa prepara código live e recursos de runtime; não executa nenhuma operação
cloud, HEAD initialization, materialização, build, deploy, migration ou plan/apply.

## Escopo e guards

`src.analytics.job --live` aceita somente up-data-intelligence-dev, região
southamerica-east1, mx-fashion, confirmações project/store, full-refresh e policy
oficial. Hash:
`3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c`.

A janela, history_from, as_of e flags de cobertura devem ser exatamente os aprovados;
não é permitido trocar flags sem alterar hash e passar despercebido (hash não inclui
cobertura). Erros bloqueiam antes de descobrir credenciais. Nova loja/projeto/janela
precisa de configuração/revisão explícita, não apenas argumentos diferentes.
`--dry-run` continua somente geração local de SQL, mutuamente exclusivo de --live.

Novo guard `--confirm-backfill-complete` exige declaração do operador de que o
backfill foi concluído. O programa não infere isso de observed_at nem consulta
Jobs de ingestão. Na configuração futura do Cloud Run esse argumento está presente;
a execução manual do Job deve ocorrer somente após essa confirmação operacional.

Após os guards, cria apenas BigQuery Client com project/location explícitos.
Lê quatro COREs atuais; não usa versões, RAW, Secret Manager ou Meta.
A policy oficial é copiada explicitamente ao container pelo Dockerfile; .dockerignore
permite apenas esse JSON em config. Não foi construída imagem nesta etapa.

## Snapshot e publicação inicial

Ao início, depois da confirmação de backfill, captura snapshot_at UTC uma única vez.
O manifesto técnico tem somente store, policy_hash, snapshot_at canônico e
mode=full_refresh_initial. generation é digest determinístico desse manifesto;
completeness_confirmed=false e full_refresh_authorized=true. Todas as leituras CORE
usam o mesmo FOR SYSTEM_TIME AS OF. Snapshot_at é tempo de leitura atual; as_of é
limite de negócio aprovado em 28/09 00h local. Não confundir os dois.

Snapshot/generation ficam em logs estruturados sem PII. Source watermark no receipt
é esse hash, não um checkpoint CDC. Não há promessa de incrementalidade exactly-once.

Pré-flight somente leitura:

1. Exatamente um HEAD obrigatório. Ausência/duplicação bloqueia antes de ler CORE.
2. Generation=0 exige HEAD limpo, nenhum receipt e nenhuma linha da loja/policy nas
   sete tabelas. Não substitui uma materialização anterior silenciosamente.
3. Generation=1 permite apenas reconciliar exatamente um receipt completed da mesma
   janela/policy/versão, vinculado ao HEAD por publication_id/source_watermark.
   Retorna sem ler CORE nem escrever novamente.
4. Generation>1, receipt conflitante ou HEAD inconsistente bloqueia. Nenhum reset.

Retry antes de commit pode capturar novo snapshot, ainda com generation HEAD=0.
Retry após commit encontra o receipt anterior, mesmo que relógio/snapshot atual
sejam diferentes. Concorrência continua protegida pelo CAS transacional do writer;
segunda tentativa baseada em HEAD antigo falha ou reconcilia. Não há auto-retry de
Cloud Run (max_retries=0), loop automático nem Scheduler. Se houver timeout incerto,
verificar receipt antes de assumir falha/limpar estado; nunca apagar dados para retry.

## HEAD — comando futuro, NÃO executar nesta preparação

Arquivo `sql/analytics/cloud_proposed/initialize_head.sql` agora é idempotente para
chamadas sequenciais: insere generation=0 só se ausente; deixa HEAD existente intacto,
inclusive generation>0; falha para mais de um HEAD; não insere/remove receipts.

**Inicialização precisa ser serializada pelo operador, sem inicializadores ou Jobs
concorrentes.** BigQuery não impõe unicidade; dois INSERTs concorrentes partindo de
zero HEAD não constituem um mutex seguro. O Job não chama esse SQL. Só iniciar Job
depois de confirmar exatamente um HEAD. Não repetir inicialização em paralelo.

Definir ANALYTICS_MAXIMUM_BYTES_BILLED com o valor aprovado antes dos comandos futuros:

```bash
bq --project_id=up-data-intelligence-dev --location=southamerica-east1 query \
  --use_legacy_sql=false \
  --maximum_bytes_billed="$ANALYTICS_MAXIMUM_BYTES_BILLED" \
  --parameter='store:STRING:mx-fashion' \
  --parameter='policy:STRING:3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c' \
  < sql/analytics/cloud_proposed/initialize_head.sql
```

Este comando contém DML e depende de autorização posterior. O runtime não precisa
permissões para criar tabelas nem para inicializar sua própria infraestrutura.

## Terraform ativo — somente novos recursos de runtime

Arquivo novo: `infra/terraform/analytics_runtime.tf`.

| Recurso | Quantidade |
|---|---:|
| Service account up-analytics-dev | 1 |
| roles/bigquery.jobUser no projeto | 1 |
| Table IAM dataViewer: customers, orders, order_items, analytics_events | 4 |
| Table IAM dataEditor: oito tabelas up_analytics aprovadas | 8 |
| Cloud Run Job up-analytics-dev | 1 |
| **Total esperado novo** | **15** |

Expectativa futura: **15 add / 0 change / 0 destroy**, se não houver drift nem
runtime preexistente. Não é resultado de plan. Parar se qualquer recurso existente
aparecer alterado/recriado/destruído. Nenhum schema, tables.json, dataset, IAM anterior,
UP Zero Job, Secret ou scheduler_paused foi alterado nesta etapa.

Leitura CORE é por tabela, não dataset. Como já documentado, table IAM permite
tecnicamente todas as colunas dessa tabela; projeções do reader são mínimas.
Escrita limitada às oito tabelas Analytics. Sem write CORE/RAW, secrets, Owner,
Editor de projeto, Artifact Registry writer, versões CORE ou recursos Meta.
Nenhum Scheduler é criado; o Scheduler antigo da Foundation continua pausado.
A raiz analytics_proposed não deve ser aplicada em paralelo à raiz ativa.

Entradas Terraform novas e obrigatórias, sem default:

- analytics_image: digest imutável da **nova** imagem foundation com policy/CLI.
  O var.image/DEV.4 de UP Zero permanece intacto.
- analytics_maximum_bytes_billed: inteiro positivo aprovado, teto **por query**.
  Não limita o total do Job; preflight, CORE, staging, commit e reconciliação somam.
- analytics_maximum_total_bytes_billed: soma máxima aprovada dos tetos reservados
  por query, incluindo tentativas falhas; guard operacional agregado obrigatório.

Sem imagem/digest e orçamento aprovados, não gerar/applicar plan. Não foi colocado
um digest fictício ou reutilizada DEV.4 no Job novo.

Dimensionamento proposto: 1 task, parallelism=1, 2 vCPU, 4 GiB, timeout 3600s,
query timeout 300s, max_retries=0. Facts agora são transportados por dia/prefixo e
reduzidos em spool temporário, sem juntar toda a janela numa lista. O limite de
100 mil permanece por transporte; os três inputs comerciais mantêm seus limites
por leitura e agregado. Benchmark, custos, capacidade e limitações estão em
[ANALYTICS_FACT_CHUNKING.md](ANALYTICS_FACT_CHUNKING.md). Nenhum teste local garante
capacidade cloud; revisar memória e ambos os orçamentos antes da execução.

## Contrato futuro de execução — NÃO executado

Com a nova imagem publicada, runtime provisionado, HEAD válido, backfill confirmado
e orçamento aprovado, o comando Python equivalente é:

```bash
python -m src.analytics.job \
  --live \
  --confirm-project up-data-intelligence-dev \
  --confirm-store mx-fashion \
  --store mx-fashion \
  --policy config/analytics/mx-fashion.dev.json \
  --from 2026-09-01 --to 2026-09-28 \
  --as-of 2026-09-28T03:00:00Z \
  --project up-data-intelligence-dev --location southamerica-east1 \
  --maximum-bytes-billed "$ANALYTICS_MAXIMUM_BYTES_BILLED" \
  --maximum-total-bytes-billed "$ANALYTICS_MAXIMUM_TOTAL_BYTES_BILLED" \
  --timeout-seconds 300 --full-refresh --confirm-backfill-complete
```

A configuração do Job contém esses mesmos argumentos; invocação manual futura:

```bash
gcloud run jobs execute up-analytics-dev \
  --project=up-data-intelligence-dev --region=southamerica-east1 --wait
```

Essa invocação depende de autorização posterior e permissão de execução do operador;
não foi concedida permissão de invocação automática. Não executar agora.

## Validação pós-materialização — SELECT preparado

`sql/analytics/validation/first_mx_fashion.sql` retorna somente contagens, nomes de
checks e passed, sem IDs de clientes/pedidos ou PII. Verifica:

- store_daily e funnel_daily: exatamente 27 linhas/dias locais, 01/09–27/09,
  sem duplicatas e com flags de cobertura aprovadas;
- chave e grain únicos nas sete tabelas; customer_id/order_id únicos nos grains;
- purchase_number inicia em 1, sem lacunas/duplicatas por customer;
- store/policy/currency esperados; métricas pagas NULL;
- um HEAD generation=1, um receipt completed da janela e vínculo entre ambos;
- ausência de linhas fora da loja/policy inicial (diagnóstico, nunca delete).

Comando futuro somente leitura, após autorização da materialização:

```bash
bq --project_id=up-data-intelligence-dev --location=southamerica-east1 \
  --format=prettyjson query --use_legacy_sql=false \
  --maximum_bytes_billed="$ANALYTICS_MAXIMUM_BYTES_BILLED" \
  --parameter='store:STRING:mx-fashion' \
  --parameter='policy:STRING:3098157d095a3bcb0c024dbc6263fa7e5eebdc099a2f72903ca82f7634b9c54c' \
  < sql/analytics/validation/first_mx_fashion.sql
```

Todos os checks devem passar. Contagem/facts_complete não comprova completude da
fonte por si só: depende da cobertura já atestada. Não promover consumo ou Scheduler
se algum check falhar. Preservar resultados para diagnóstico, sem apagar HEAD/receipt.

## Validação desta entrega

Clientes/transport mockados: guards, projeto/loja/policy, full-refresh obrigatório,
HEAD ausente/duplicado, proteção de generation, reconciliação/idempotência, política
paga NULL e isolamento. Suites anteriores cobrem rollback e lost acknowledgement.
Um teste legado de diagnóstico foi estabilizado para comparar o valor JSON do ID
sintético, evitando colisão acidental do texto curto `a-1` com UUID aleatório;
nenhuma lógica de ingestão foi modificada.

Terraform fmt-check/validate foram executados localmente com binário/provider já
instalados. O sandbox inicialmente bloqueou o handshake local do plugin; validate
passou fora dessa restrição, sem init/plan/cloud. DML HEAD/publicação e novas queries
de diagnóstico ainda precisam de validação no ambiente autorizado; paridade 7/7
não comprova transações ou DML do writer.

Parado antes de plan/apply/GCP/build/deploy/HEAD/materialização. Próximas decisões:
orçamentos por query/agregado, capacidade dos inputs comerciais e spool, nova imagem e
autorização separada para provisionamento/run manual.
