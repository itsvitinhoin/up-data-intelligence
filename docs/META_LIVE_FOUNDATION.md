# CHANGE #13 — Meta Ads Live Foundation (preparação offline)

Apesar do nome, esta entrega **não habilita conexão live**. A estrutura Meta anterior já existia. Este change amplia o contrato de leitura e adiciona projeção/testes separados; não altera CORE existente, RAW, UP Zero, Analytics V1, Paid Influence ou Customer Intelligence. Nenhuma configuração real de conta/token foi criada.

## Arquitetura e arquivos

```text
Meta API futura → RAW Meta sanitizado → entidades Meta normalizadas
                                      → Insights por dia/nível/configuração
                                      → relacionamento exato de IDs com Paid Influence
                                      → Customer Intelligence
```

- `src/connectors/meta/foundation.py`: MetaFoundationConnector, campos adicionais e escolha de nível. Reutiliza cursor/retry/sanitização de MetaConnector, que aceita somente httpx.MockTransport.
- `src/connectors/meta/client.py`: pontos de extensão de fields e insights_level; defaults anteriores preservados.
- `src/normalization/meta.py`: normalize_foundation, projeção pura separada do transform existente.
- `src/quality/meta.py`: validate_foundation, validação da proposta e duplicatas.
- `src/ingestion/meta.py`: extract_foundation_offline, extração simulada limitada em memória, sem Repository ou persistência.
- `src/connectors/meta/foundation_schema.py`: gerador da proposta.
- `infra/terraform/meta_live_proposed/`: cinco schemas e manifesto **não referenciados pelo Terraform ativo**. Não substituem `infra/terraform/schemas/meta_*.json` nem o catálogo CORE existente.
- `tests/meta/`: fixtures exclusivamente sintéticas.

A nova extração não deve ser passada ao MetaEngine durável como se fosse schema atual: os contratos são diferentes. A migração/mapeamento de compatibilidade deverá ser desenhada e autorizada separadamente antes de produção. Não promover os cinco nomes existentes como novas tabelas cegamente.

## Entidades e mapeamento

Todos os IDs são STRING decimal, com zeros à esquerda preservados; inteiros, vazios, negativos e strings não numéricas são bloqueados. Binding explícito de loja/conta vem da configuração aprovada, nunca de campanha/UTM. A convenção de endpoint `act_` não é armazenada como parte do ID numérico.

| Proposta | Grão e campos |
| --- | --- |
| meta_accounts | loja + conta; meta_account_id, account_name, currency, timezone, status, created_time, updated_time |
| meta_campaigns | loja + conta + campanha; campaign_id/name, objective, status/effective_status, created_time/updated_time |
| meta_adsets | loja + conta + conjunto; adset_id/name, campaign_id, optimization_goal, billing_event, targeting_summary, status/effective_status |
| meta_ads | loja + conta + anúncio; ad_id/name, adset_id, campaign_id, creative_id, status/effective_status |
| meta_insights_daily | loja + conta + nível + ID da entidade + dia + configuração + breakdowns |

Todos incluem row_key, store_id, account_id, api_version, contract_version, observed_at e source_updated_at. Proposta de Insights particionada por date_start e cluster por loja/conta; entidades cluster por loja/conta; deletion protection proposta. Não criar recursos.

Account status é a representação textual do account_status numérico observado; não inferir enum. created_time/updated_time de conta ficam NULL quando ausentes na resposta. source_updated_at de entidades deriva de updated_time; Insights não oferece um timestamp de atualização nesta extração, portanto NULL. observed_at é horário da coleta informado pelo chamador, não watermark da Meta.

Adset lê optimization_goal/billing_event/targeting; targeting_summary expõe somente os nomes das dimensões presentes, sem valores de localização/audiências. Anúncio lê creative{id}; ausente permanece NULL. Não coletar conteúdo de criativo nem supor métricas de desempenho a partir dele. Campos verificados no SDK oficial: [AdSet](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adset.py) e [Ad](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/ad.py). Disponibilidade e combinações ainda exigem validação contra uma versão de API aprovada antes de uso real.

## Insights diário

Níveis campaign/adset/ad são separados. IDs abaixo do nível solicitado devem ser NULL; os IDs obrigatórios desse nível não podem faltar. Não somar linhas dos três níveis. date_start=date_stop representa **um dia local da conta**, com time_increment=1; since/until são inclusivos. Não tratar DATE como checkpoint UTC.

Chave lógica inclui api_version, timezone, moeda, nível, action_report_time, attribution windows, tipo de ação e dimensões de breakdown. A janela de extração não faz parte da identidade: coletar o mesmo dia em janelas sobrepostas não deve criar outra linha lógica. Mudança de configuração gera outra série, nunca sobreposição silenciosa.

| Métrica | Fonte/regra |
| --- | --- |
| spend | Fonte, NUMERIC/string decimal, obrigatório e não negativo |
| impressions / reach / clicks | Inteiros não negativos quando disponíveis; ausente NULL |
| link_clicks | Mapeamento explícito de inline_link_clicks; não confundir com todos os clicks |
| landing_page_views | actions[action_type=landing_page_view].value; decimal para preservar representação da fonte; não soma categorias sobrepostas |
| currency / timezone | Configuração explícita reconciliada com account_currency/conta |
| cpm | spend × 1000 / impressions |
| cpc | spend / clicks (todos os cliques, não apenas link_clicks) |
| ctr | clicks × 100 / impressions, unidade percentual |

CPM/CPC/CTR nesta proposta são calculados com Decimal, 9 casas, HALF_EVEN. Valores reportados originais continuam no envelope RAW sanitizado. Denominador zero/ausente → NULL, não zero inventado. Spend zero é válido. Não inferir zero de resposta vazia/ausência de permissão. O vocabulário de métricas está no [AdsInsights oficial](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adsinsights.py); este código não comprova disponibilidade de cada breakdown para uma versão/conta live.

Breakdowns preparados: age, gender, country, publisher_platform, platform_position, conforme allowlist existente. Cada combinação é uma série distinta; dimensão solicitada ausente ou dimensão conhecida inesperada bloqueia. Não misturar base sem breakdown com segmentações, nem somar sobre dimensões sobrepostas. Reach não é aditivo entre dias/anúncios; taxas devem ser recalculadas de bases compatíveis, nunca média simples. Não implementar rollup de reach para campanha a partir de anúncios.

## Paginação, retry e limites offline

Somente GET simulado, API version explicitamente configurada, limite de página configurável, max_pages e tentativas limitadas. Cursor after vem da resposta; não seguir paging.next como URL. Retry herdado cobre transporte/429/5xx e Retry-After limitado; não habilitar OAuth ou transporte HTTP real. Permissões Graph, erros Graph com HTTP200, limites de conta e relatórios assíncronos precisam de qualificação antes de live.

extract_foundation_offline captura páginas sanitizadas em memória antes de normalizar. Valida todas as linhas, inclusive duplicatas entre páginas, antes de retornar. Retorna raw_pages e rows; não escreve checkpoint/tabelas/arquivos. Falha não publica resultado parcial, porém **não deixa RAW durável**: é referência de teste. Limite padrão 100.000 registros; não é pipeline de produção nem prova de escala.

MetaEngine anterior continua separado como referência durável: RAW/pending_raw_id antes de CORE, checkpoint somente após promoção completa, replay e current/version. O novo contrato exige adaptação explícita antes de usar esse caminho. Não reescrever dados atuais para testar a proposta.

## Qualidade e integração

Bloqueios: spend negativo/ausente, IDs inválidos, conta/loja divergente, moeda inconsistente, timezone divergente, data inválida ou fora da janela, nível incompatível, breakdown ausente/inesperado, schema incompatível, métricas negativas e chave duplicada (mesmo payload idêntico nesta proposta). Replay independente das mesmas entradas reproduz a mesma row_key; um lote com duas cópias não é tratado como dois resultados.

```text
Meta Campaign → paid touchpoint → customer influence → order influence → Customer Intelligence
```

Relacionar analytics_events.meta_campaign_id/meta_adset_id/meta_ad_id com IDs exatos, no mesmo store_id e conta explicitamente configurada. Hierarquia anúncio→conjunto→campanha deve ser validada; conflito não ganha fallback por nome. IDs em URL não provam autorização da conta nem causalidade de venda. Ausência de entidade Meta não autoriza apagar o Fact. Catálogo Meta enriquecido adiciona nomes/metadados; não muda os caminhos determinísticos de identidade do cliente.

LIFETIME, ACQUISITION e REPEAT_PURCHASE continuam separados. Nenhum módulo Paid Influence/Customer Intelligence é modificado. Teste sintético comprova preservação dos três IDs no touchpoint, incluindo zeros à esquerda; isso não certifica resolução cross-account nem atribuição causal.

## Métricas e API futuras

Preparar combinação por loja/conta/campanha/janela/moeda/configuração compatíveis: spend, clientes/pedidos influenciados distintos, requested_revenue_influenced e fulfilled_revenue_influenced. cost_per_influenced_customer/order poderá ser spend dividido pela contagem correspondente, com denominador zero→NULL e cobertura demonstrada; não calculado aqui. Campanhas participantes podem compartilhar pedidos: não somar receitas por campanha como se fossem disjuntas.

Não calcular ROAS, CAC ou LTV pago: faltam Payment Ledger e receita paga, além de regras de atribuição e cobertura aprovadas. Meta reporta mídia e conversões da plataforma; UP fornece clientes/pedidos/solicitado/atendido. Conversão reportada pela Meta não substitui receita paga.

| GET futuro | Contrato |
| --- | --- |
| /campaigns | Lista paginada por loja/conta com identidade/status |
| /campaigns/{id} | Campanha + resumo de spend e participação comercial em janela explícita |
| /campaigns/{id}/insights | Série por dia/nível/configuração/breakdown; moeda/timezone e cobertura |
| /campaigns/{id}/customers | Clientes influenciados distintos, escopo/evidência; não PII |
| /campaigns/{id}/orders | Pedidos distintos + solicitado/atendido separados e campanhas participantes |

Todas exigirão principal autenticado, store_id/account_id autorizados, cursor vinculado à geração/filtros, page_size limitado, filtros date_from/date_to e metadata de moeda/timezone/reporting_configuration. Nunca cruzar lojas ou fazer query RAW no frontend. Resposta lógica Campaign + Spend + Customers influenced + Orders influenced + Requested revenue + Fulfilled revenue; sem receita genérica ou crédito exclusivo. Nenhum endpoint foi implementado/publicado neste change.

## Segurança e caminho para live

Nenhum token real, credencial, OAuth, leitura Secret Manager ou API Meta foi executado. Testes usam marcador sintético, transporte MockTransport e bloqueio global de rede. Authorization só existe no request simulado; sanitização anterior à captura remove valores sensíveis e URLs com tokens, sem seguir next. Nunca registrar access_token, refresh_token, app_secret em contratos, outputs ou logs. RAW Meta é sanitizado por segurança, não promessa de cópia byte a byte de credenciais.

Integração futura deverá buscar credencial em Secret Manager apenas em memória, identidade mínima, rotação e redaction; não é implementada aqui. Antes de live: conta/loja e moeda aprovadas, versão/API/campos/breakdowns qualificados, permissão de leitura revisada, estratégia async/limites/retry, armazenamento/checkpoint e schemas compatíveis aprovados, custos/retenção/observabilidade e testes DEV autorizados. Nenhum desses passos é disparado automaticamente.
