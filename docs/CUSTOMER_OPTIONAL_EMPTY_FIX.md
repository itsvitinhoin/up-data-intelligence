# Customers — campos opcionais vazios

## Causa confirmada

ROOT CAUSE: optional empty state/city normalization.

NOT ROOT CAUSE: Orders sync_delayed; global quality warnings; invalid_meta_parser.

O responsável forneceu resultados da Execution/Task ppq2j: imagem DEV.3 digest `sha256:75178081762e20da7f4dfc0c7c4417c69027ee4ba074494197ea7dc86c96209f`, exit code 1/NonZeroExitCode. Dos 28 child runs correlacionados por logs, 24 completed e 4 completed_with_errors. Snapshot histórico: 576 processados, 555 inserts, 17 updates, 4 failed. Reprodução em memória encontrou os quatro registros no RAW, todos com state/city strings vazias rejeitadas por typed(STRING) → identifier → ValueError. O CLI retorna 1 quando algum child não é completed; o retorno era correto para essas falhas.

Os seis warnings de parser foram categorizados pelo responsável como adset_name:placeholder, sem divergências entre resultado histórico e atual. Não são a causa do incidente. Parser permanece sem alterações, com investigação de nomes legítimos versus macros adiada. Nenhum dado cadastral real foi incluído em fixtures ou documentação.

## Escopo e auditoria dos campos

| Categoria | Campos | Política |
|---|---|---|
| Identificador obrigatório | Customer source.id → customer_id; IDs obrigatórios de outras entidades | Validação estrita mantida: null/empty/whitespace inválidos. Não converter para null para aceitar a entidade |
| Projeção opcional de geografia | state, city | null, empty ou whitespace → null; texto preenchido segue regra anterior sem trim adicional/inferência/fallback |
| Referência opcional de vendedor | seller_id | ID vazio/whitespace → null antes de identifier; ID preenchido validado como antes, inclusive tipo inválido continua falhando |
| Contatos e documentos opcionais | email, phone, cpf, cnpj | Projeção escalar vazia → null; não vazia preservada. Originais continuam no RAW e, quando aplicável, profile |
| Derivados de matching | email_normalized, phone_normalized, phone_e164, cnpj_digits, cpf_digits | Ausência → null; demais regras de normalização mantidas, sem inferência de país. Documentos/phones em branco não geram issue de formato apenas por ausência |
| Outros textos opcionais de Customer | name, customer_type, status, company_name, trade_name | Lista explícita: empty/whitespace → null. Sem mudanças em Orders ou Facts |
| Referência externa opcional | external_ref | Container null/empty/whitespace → null. Objeto fornecido preservado como JSON; não inventa ID ou integração. Chaves internas vazias permanecem na representação auditável |
| JSON original/auditável | retail_profile, wholesale_profile, seller; objeto external_ref | Preservados após sanitização de secrets; não normalizar recursivamente chaves *_id desses documentos originais. Isso evita rejeitar o cadastro por um ID opcional vazio em metadados livres e preserva tipos originais |
| Fonte e snapshots | RAW, customer_snapshot, shipping_address | RAW sem alteração; profiles originais preservados. Código/schema dos snapshots de Orders não muda |

A correção é limitada ao ramo Customers e às projeções listadas. Não relaxa typed() ou identifier() globalmente, nem transforma tipos inválidos em null. Strings preenchidas não são alteradas indiscriminadamente. State/city continuam vindo exclusivamente do profile correspondente ao customer_type, sem fallback de localização.

Transform_version passa de 1.1.0 para 1.1.1; identity_normalization_version de 1.0.0 para 1.0.1. Os JSONs auditáveis de Customers agora preservam tipos de IDs internos como recebidos (por exemplo seller.id inteiro), enquanto seller_id projetado continua STRING. Consumidores de JSON devem usar a projeção tipada; revisões anteriores permanecem em customers_versions. Não há mudança de schema.

## Recuperação após deploy — não executada

1. Após autorização separada, construir/publicar nova imagem com ambos os patches, atualizar o digest e fazer deploy DEV com schedulers pausados. Não há migration necessária para esta correção (pressupõe as colunas aditivas já presentes na DEV.3).
2. Conferir metadados do Job e digest, existência de RAW dos quatro runs e condições atuais de qualidade Customers. Não executar backfill amplo nem apagar/resetar checkpoints.
3. Executar **sequencialmente**, sob o lock de loja existente, quatro operações de replay Customers. Para cada run abaixo, usar argumentos do CLI:

```text
--live --confirm-store mx-fashion --mode replay --resource customers --replay-run <original_run_id>
```

| original_run_id | Registros do run original | Falhas históricas |
|---|---:|---:|
| a5c0378e-5344-4a17-b3bb-0504a77e03a2 | 32 | 1 |
| 103978b6-7c0d-4dcb-9150-bde6a7f9b696 | 20 | 1 |
| f88b9269-e806-477a-8933-74feeece9dd4 | 12 | 1 |
| 477002cc-b62a-4b74-baab-16d6e7a2d3bf | 25 | 1 |

Replay processa todo o RAW do run, não somente o registro rejeitado. Não chama a API UP Zero nem precisa resolver sua API Key. Mantém isolamento por loja e upsert por chave, com evidência versionada.

4. Validar novos sync_runs de mode=replay: status completed, core_records_failed=0, source_records_read=0, raw_pages_written=0. Com RAW integral, replay_records_read/core_records_processed somam 89. Sem observações posteriores ou recuperação concorrente, esperar 4 inserts e até 85 updates das linhas já existentes devido ao novo transform_version. Não prometer exatamente esses inserts/updates se os dados já tiverem sido atualizados; regras stale e idempotência permanecem ativas.
5. Verificar zero duplicatas por store/customer_id, geography null nos casos recuperados, profiles/RAW inalterados e Order→Customer preservado. A contagem atual só deve passar de 572 para 576 se nenhuma outra ingestão/recuperação tiver ocorrido. Segundo replay dos mesmos RAW sob a mesma versão não deve inserir/atualizar novamente as mesmas versões.
6. Os sync_runs originais continuam completed_with_errors e os checkpoints originais continuam needs_review. Replay cria outro run, com plan_key=original_run_id; não reescreve o histórico nem libera automaticamente aqueles planos. Não repetir o backfill esperando que esses checkpoints desapareçam. Se for necessário liberar/reconciliar os planos antigos, tratar em operação separadamente autorizada; não há reset ou atualização manual nesta correção.

### Atenção ao gate após replay

O quality gate novo permanece válido e inalterado: Orders delayed e warnings globais não bloqueiam Customers. Porém sync_delayed de Customers ainda pode bloquear se sua última ingestão não-replay estiver antiga, porque replay não conta como atualização da fonte. Assim, **replay completed e processo exit 1 por freshness própria podem coexistir**. Conferir ingestion_status, resource_quality_status, sync_runs e regras antes de qualquer retry; não reinterpretar isso como falha de recuperação nem repetir automaticamente. Falha da consulta/persistência de qualidade também pode produzir exit 1 após replay concluído.

## Validação local

Fixtures sintéticas incluem quatro janelas com um registro rejeitado e um válido em cada uma. Simulam a falha histórica e verificam recuperação exclusivamente do RAW, contatos/geografia opcionais, chaves obrigatórias estritas, preservação de profiles/RAW/checkpoints, referência Order→Customer e repetição idempotente sem duplicatas. Nenhuma operação de replay live foi executada; testes usam SQLite e transporte HTTP sintético com rede bloqueada.

A política resource-scoped e seus testes são preservados. A reprodução sintética da versão antiga simula explicitamente a rejeição de strings vazias; não usa dados reais ou a imagem live. A evidência da reprodução real foi fornecida pelo responsável no Cloud Shell.

Resultado final: 186 testes aprovados (166 anteriores + 20 novos casos), Ruff lint e formatting aprovados (55 arquivos), mypy aprovado (40 arquivos), git diff --check aprovado. Nenhum GCP, replay live, Cloud Run, migration, build ou deploy executado nesta correção.

## CHANGE #17D.1.3 — recovery administrativa de checkpoints

O responsável confirmou que os quatro replays históricos já foram concluídos:
89 Customers processados, quatro inserts, 85 updates e zero falhas CORE, com
source_records_read=0 e raw_pages_written=0. Os runs originais continuam
`completed_with_errors`; os replay runs continuam `completed`. Os checkpoints
originais permaneceram `needs_review`, porque replay **não atualiza automaticamente
checkpoint**. Nenhum desses replays foi executado novamente nesta entrega.

Agora existe o estado terminal auditável `recovered`: o erro original permanece
registrado, mas o RAW correspondente foi reprocessado com sucesso por um replay
único e explicitamente comprovado. Não significa nova leitura da API, novo scan,
pagamento confirmado ou eliminação do histórico. Não há migration, schema ou
coluna nova; a relação auditável continua checkpoint.run_id → original sync_run e
replay.plan_key → original run_id.

### Prova e operação separada do registry

`src.ingestion.checkpoints` define os estados canônicos e o conjunto terminal
`{complete, recovered}`. `CheckpointRecovery`/`RecoveryProof` são contratos
separados de StoreAdmin. A operação exige ADMIN_UP com subject não vazio **antes**
de qualquer leitura, escrita ou aquisição de lease; o CLI interno usa
`Admin("adc-internal-operator", "ADMIN_UP")`, com credenciais ADC/IAM do operador
confiável. Essa identidade não é uma autorização enviada por um navegador.

A prova usa somente metadados de `up_ops.sync_checkpoints`/`up_ops.sync_runs`:

- exatamente um checkpoint da store/run, recurso UP Zero suportado, status
  needs_review e pending_raw_id NULL;
- exatamente um original da mesma store/run/resource/mode, source upzero,
  completed_with_errors e core_records_failed positivo;
- exatamente um replay válido, da mesma store/resource, mode replay,
  plan_key=original_run_id, completed, sem falhas CORE, sem captura API/RAW,
  replay_records_read positivo e igual a core_records_processed;
- com metrics_version=2 no original, os contadores precisam ser válidos
  (processed >= failed) e o replay deve ter exatamente original.processed registros.
  Versões históricas NULL/1 não recebem contadores v2 inventados; os contadores
  explícitos do replay continuam obrigatórios. Versão desconhecida falha fechada;
- o replay único deve ser o UUID explicitamente fornecido. Nenhum replay é
  escolhido como “mais recente”; zero ou múltiplos replays válidos bloqueiam.

A consulta de prova é centralizada em `recovery_queries.py` e reutilizada pelo
reader, worker, preflight e transação. Não lê payload RAW, Customers CORE, nome,
email, telefone, CPF/CNPJ ou endereço; nem carrega filters para a recovery.
Logs contêm somente event/store/resource/status e códigos sanitizados, sem
ampliar SAFE_FIELDS ou imprimir SQL/valores de exceções.

### CAS, campos preservados e lease

A operação roda sob `cloud_lease(lease_bucket, store_id)`. Uma única transação
recalcula a prova em uma tabela TEMP privada, faz ASSERTs de cardinalidade,
estado, pending, original, replay explícito, contadores, chave e recurso esperado,
e executa UPDATE parametrizado. `ASSERT @@row_count=1` ocorre imediatamente
após o UPDATE, antes de COMMIT. A tabela TEMP não é uma tabela permanente nem
um novo recurso/schema da plataforma.

Somente `status= recovered` e `updated_at=CURRENT_TIMESTAMP()` são escritos.
Preservam-se exatamente row_key, store_id, resource, connection_id, plan_key,
run_id, mode, filters, position, completed_to, high_id e pending_raw_id. Original,
replay, quality_results, RAW e CORE não recebem UPDATE. TOCTOU, zero/múltiplas
linhas ou prova inválida causam rollback. Repetição com a mesma prova retorna
`checkpoint_already_recovered`, sem segunda mutação ou atualização do timestamp.

BadRequest/Forbidden/Unauthorized são sanitizados como
`checkpoint_recovery_failed`. Timeout, perda de resposta ou outro resultado
ambíguo retornam `checkpoint_recovery_outcome_unknown`: **o lease fica retido**.
Não há retry automático da mutação. O operador precisa reconciliar o resultado
antes de liberar o lease ou tentar novamente; o commit pode ter ocorrido mesmo
sem resposta. Falhas de leitura são sanitizadas e não são mutação ambígua.

### Worker, cobertura e freshness

Engine.run conserva complete/needs_review; o mesmo plano recovered sem refresh
falha com `run_recovered_use_refresh`, nunca retorna o run histórico com erro como
sucesso. Actions.upzero verifica a prova antes de ignorar recovered sem pending,
e prossegue para uma coleta incremental real. Needs_review/running/extracted
continuam pendentes; recovered com pending (inclusive string vazia não NULL)
continua bloqueante. Nenhum replay/refresh é disparado automaticamente pela
operação administrativa.

`incremental()` continua selecionando somente mode incremental/status complete;
recovered não fornece novo cursor/high_id/lookback. Preflight revalida a prova
no mesmo source_snapshot_at usado nas outras dependências. Customers recovered
válidos deixam de ser pendência histórica, mas **não entram nos scans que provam
freshness**. Continua necessário um run real upzero, não replay, completed e sem
falhas, com finished_at >= window.as_of e filtros de scan limit-only. Nem
recovery.updated_at nem replay.finished_at podem satisfazer essa condição.

Nesta etapa, o preflight **continua fail-closed para Orders/Analytics Facts
recovered** (`upzero_recovered_resource_not_supported`). A recovery administrativa
suporta os três recursos, mas promover a cobertura histórica genérica desses
intervalos fica para análise posterior; isso não bloqueia o caso Customers atual.

### CLI preparado — não executar ainda

Não há recuperação real nesta entrega. Antes de recuperar os quatro checkpoints,
os workers precisam executar uma nova imagem com essa semântica; a imagem antiga
não reconhece recovered. Build/publicação/atualização do runtime, validação live
da prova/SQL e cada recovery real exigem etapa posterior autorizada. Schedulers
permanecem pausados. Não repetir replay: os quatro já foram comprovados.

Comando ilustrativo para essa etapa futura, com UUIDs explicitamente revisados:

```bash
.venv/bin/python -m src.control_plane.recovery_cli \
  --live \
  --project up-data-intelligence-dev \
  --confirm-project up-data-intelligence-dev \
  --location southamerica-east1 \
  --lease-bucket LEASE_BUCKET_DEV \
  --store-id mx-fashion \
  --confirm-store mx-fashion \
  --original-run-id UUID_ORIGINAL \
  --replay-run-id UUID_REPLAY \
  --maximum-bytes-billed 1073741824 \
  --maximum-total-bytes-billed 137438953472
```

Sem live/confirmações ou UUIDs válidos, o CLI falha antes de criar clients/ADC.
Ele respeita os guards de custo existentes. Permissões futuras necessárias são
jobUser para queries, leitura de ambas tabelas OPS, updateData em sync_checkpoints
e acesso restrito ao bucket de leases; nenhum IAM foi alterado nesta entrega.
Depois de recovery comprovada e commit conhecido, a próxima coleta UP Zero real
restabelece freshness. Não ativar scheduler como parte da recovery.

Validação #17D.1.3: 1.871 testes offline aprovados (140 novos casos), Ruff,
formatting, mypy, Terraform fmt/validate e git diff check aprovados. A prova/CAS
foi exercitada com SQLite/mocks e metadados sintéticos; o SQL não foi executado
no BigQuery real. Nenhum dos quatro checkpoints reais foi modificado.
