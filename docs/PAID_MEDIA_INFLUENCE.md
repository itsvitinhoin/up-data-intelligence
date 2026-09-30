# Changes #08 + #09 — influência paga e materialização offline

A pergunta é: **“há contato pago observado antes desta compra, com vínculo
comprovado ao cliente?”**. Não existe atribuição exclusiva, divisão percentual,
last click/first click, causalidade, CAC ou ROAS nesta camada. Campanhas participam
da jornada; não recebem100% da venda. First/last são extremos temporais.

## O que mudou em relação ao CHANGE #07

O critério de entrada agora é o aprovado no Epic: pelo menos um campo observado
`meta_campaign_id`, `meta_adset_id`, `meta_ad_id`, `fbclid`, `fbc` ou `gclid`.
O #07 exigia resolução Meta offline; **essa exigência não se aplica mais**.
`paid_evidence` continua aceito como input legado opcional, mas não decide elegibilidade.
Nenhum client/API Meta é usado. UTM sozinha, `fbp`, nomes ou URLs não tornam evento pago.

Marcadores devem ser strings não vazias: rejeitam whitespace/placeholders e literais
null/none/undefined; IDs Meta devem ser decimais. Não alteramos o parser CORE.
Cliques não são decodificados para inventar campaign/adset/ad. `paid_signal_types`
registra quais campos sustentam o sinal, sem copiar o token de clique para a saída.
`touch_type=PAID_TRACKING`. Isso é classificação por tracking observado conforme
regra aprovada, não comprovação de cobrança/impressão pela plataforma. Tokens podem
ser persistidos/reutilizados pela fonte; não alegamos um novo clique por cada evento.

## Identidade e evidência

O resolver é compartilhado com a [timeline](CUSTOMER_TIMELINE.md) e usa, em ordem:
1. Fact.order_id→orders.customer_id, mesma loja, IDs explícitos.
2. register_approved com prova explícita de Fact→customer, e session/visitor temporal.
3. Jornada anterior à compra, ancorada em purchase/purchase_item→order→customer.

Nunca inferir user_id=customer_id, nome, email/telefone fuzzy ou CNPJ. Link user
exige coocorrências session→user nos dois Facts, com versão/tempo correspondentes.
Conflitos de identidade não são arbitrados por “melhor nome”; deixam evento sem
resolução. IDs de outra loja não participam. Veja contrato de cadastro no documento
da timeline: a Foundation atual não produz essa prova automaticamente.

Níveis de influência:
- **DIRECT:** touch e conversão do pedido com mesmo session_id.
- **CUSTOMER_JOURNEY:** visitor/session/cadastro comprovado liga touch→customer→order,
  inclusive compra posterior em LIFETIME.
- **SUPPORTED:** vínculo explícito por order_id ou user com provas temporais, sem
  a ligação direta de sessão para o pedido considerado.

Em timeline, DIRECT também descreve Fact→Order→Customer explícito; o contexto é
resolução de identidade. Nenhum nível é percentual/confiança estatística.
Touchpoints sem resolução continuam na tabela paga com identity_path vazio e
sem evidence_type de identidade. Não são descartados nem atribuídos por adivinhação.

Para qualquer pedido influenciado, `touch.occurred_at < order.created_at` (estrito).
Um anchor de outro pedido/cadastro não pode ocorrer depois da criação do pedido-alvo.
Evento de conversão do próprio pedido pode chegar depois da criação, antes de as_of;
é evidência retrospectiva desse order_id, não licença para projetar identidade em
pedidos anteriores. Orders atuais não têm session_id: DIRECT usa o evento de conversão.

## Escopos e recompra

`--influence-scope` / `InfluenceScope`:

| Escopo | Pedidos elegíveis | Intervalo dos touches |
|---|---|---|
| LIFETIME (default) | Todas compras qualificantes na janela de relatório | Todo histórico fornecido antes da criação do pedido |
| ACQUISITION | purchase_number=1 observado | Antes da primeira compra observada |
| REPEAT_PURCHASE | purchase_number>1 | `[previous_order.created_at, current_order.created_at)` |

Assim um touch da aquisição pode participar de LIFETIME da recompra, mas não
prova REPEAT_PURCHASE se não houver contato no intervalo novo. Compras qualificantes
são as da Policy existente; CANCELED não incrementa sequência. Ordenação created_at,
order_id é determinística. Com history_complete=false, primeira compra e intervalo
anterior são **observados**, não lifetime comercial certificado. Nenhuma janela
máxima7/30/90dias foi inventada. as_of é limite exclusivo, dias locais vêm da policy.

Cada artifact materializa **um** escopo. `influence_scope` acompanha tabelas customer
e order. Seus grãos continuam1cliente/loja e1pedido/campanha; não juntar snapshots de
escopos distintos na mesma tabela como linhas adicionais. Alternativas simultâneas
exigiriam revisão explícita de grão, sem modificar o atual silenciosamente.

## Quatro modelos e schemas propostos

- **analytics_paid_touchpoints:**1store/fact_id; tracking, UTMs, tempo, touch_type,
  paid_signal_types, evidence_type e identity_path. event_id não é chave de dedupe.
- **analytics_customer_paid_influence:**1store/customer; clientes sem evidência
  aparecem FALSE (“não comprovado no snapshot”), não “nunca viu publicidade”.
  Contatos distintos, campanhas distintas e pedidos distintos na janela/escopo.
- **analytics_order_paid_influence:**1store/order/campaign; vários participantes
  podem conter o mesmo requested/fulfilled do pedido. **Não somar receita entre
  campanhas como receita total da loja.** Customer total deduplica order_id.
- **analytics_customer_timeline:** jornada resolvida, descrita no documento próprio.

Cada coluna pedida pelo Epic está nos schemas. Controles adicionais: policy_hash,
currency, history_complete, facts_complete, as_of/calculated_at, row_key/store também
no grão order. adset_id/ad_id agregados são NULL se diferentes; `participating_ads`
JSON preserva as combinações, sem escolher um anúncio arbitrário. Campaign ausente
continua NULL, bucket desconhecido do pedido, não ID inferido. Counts ignoram NULL.
First/last respeitam occurred_at,fact_id mesmo quando ID da primeira campanha é NULL.

Schemas JSON e manifest em `infra/terraform/paid_influence_proposed/`, regenerados
por `python -m src.influence.schema`. Não existem .tf aplicáveis nesta pasta;
nenhum item adicionado ao manifesto ativo. Partição de touches/timeline occurred_at;
clusters store/campaign/fact e store/customer/order. Customer/order snapshots sem
partição; deletion_protection proposta. Não foi criada tabela física ou migration.

## Solicitado x atendido

CORE.requested_total/fulfilled_total e requested_items_qty/fulfilled_items_qty são
preservados separadamente. Sem fallback de total/payment. Decimal/NUMERIC sem float;
qualquer componente ausente faz a soma correspondente ficar NULL; sem pedidos dá0.
**Fulfilled é atendido, nunca paid/recebido.** Não inferimos atendimento pelo status.

Cancelados não entram nas métricas de compra influenciada nem purchase_number;
continuam visíveis na timeline e nos KPIs financeiros/cancelamento V1 intactos.
Atendimento parcial preserva solicitado e atendido. Touchpoints históricos permanecem
mesmo se o pedido do snapshot foi cancelado posteriormente.

## Materialização local, consistência e replay

`src/influence/materialization.py` calcula, valida schemas/tipos/chaves e serializa
os quatro modelos, mais receipt local com publication_id, versão da camada,
source_snapshot_hash, policy, janela, scope, content hash, contagens e unresolved_facts.
Esse hash representa inputs locais, **não** um watermark CORE/CDC ou prova de extração
completa. Inputs devem ser snapshots coerentes fornecidos pelo operador.

Publicação é um único JSON: `tables` e `receipt`. Primeiro prepara todo conteúdo,
grava temporário0600 no mesmo filesystem e publica por hard link exclusivo; falha
antes do link não torna parte dos modelos visível. Retry idêntico retorna sem
reescrever; conteúdo diferente no destino falha sem substituir. Temp é limpo em
falhas tratadas; crash abrupto pode deixar temporário órfão. Atomicidade de visibilidade
local, não transação BigQuery nem garantia de fsync de diretório após power loss.
Não inicializa HEAD, não escreve receipts remotos, não acopla aos7 modelos V1.

O engine é referência limitada a100.000 entradas agregadas, incluindo lista legado
paid_evidence se fornecida; não é um materializador production-scale. Limite excedido,
duplicatas, tipos inválidos ou status comercial desconhecido abortam. Observed_at
posterior a calculated_at é rejeitado; observed_at posterior ao as_of comercial pode
ser válido em snapshot retrospectivo. Fonte/cobertura incompletas permanecem flags,
nunca completude inventada. Eventos sem resolução têm contagem explícita no receipt.

```bash
python -m src.influence.offline \
  --policy config/analytics/mx-fashion.dev.json \
  --input /caminho/snapshot-local.json \
  --output /caminho/influence-lifetime.json \
  --calculated-at 2026-09-29T00:00:00Z \
  --influence-scope LIFETIME
```

Input JSON: arrays customers, orders, events, identity_links; paid_evidence opcional
legado ignorado para elegibilidade. Para recompra, usar outro output e
`--influence-scope REPEAT_PURCHASE`. Não há extração live, credentials ou client Google.
Nenhum arquivo com dados reais foi criado nesta entrega; tests usam fixtures sintéticas.

## Proteção e limites

IDs e identity_path são dados pseudônimos restritos; UTMs podem conter PII da fonte.
Não logar payloads ou expor JSON completo em dashboard público. Nome/CNPJ não são
copiados; UI autorizada poderá usar join exato store/customer e masking apropriado.
Não usar CNPJ como chave. Snapshot/output local real não deve ir para Git.

Antes de produção: snapshot/extraction, volume, provas de cadastro, permissões,
publicação transacional remota dos4 modelos e diagnóstico de cobertura precisam
etapa explícita. Esta entrega não fez deploy/build/terraform/migration/GCP/backfill,
não alterou DEV.4, CORE, UP Zero, Foundation runtime ou Meta Foundation.

## Validação desta entrega offline

438 testes passaram na suíte completa;38 casos na camada de influência/timeline.
Cobrem os6 sinais aprovados, ausência de mídia, cadastro com/sem prova, pedido,
atendimento parcial, cancelamento, recompra nos3 escopos, múltiplos touches/campanhas,
identidade ambígua/ausente, corte temporal, isolamento, schemas reproduzíveis,
publicação local atômica, falha antes da publicação, retry idempotente e conflito.
Ruff lint/format, mypy (76 arquivos) e git diff --check passaram. Clientes reais não
foram usados; a fixture global de testes bloqueia rede. Sem commit/push nesta etapa.
