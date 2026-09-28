# UP Data Intelligence — arquitetura aprovada e Fase 1

Status: Fase 1 implementada localmente; sem deploy, credencial real ou execução em produção. Fonte: [upzero-openapi.json](upzero-openapi.json), preservado byte a byte. As demais fontes e camadas analíticas permanecem futuras.

## Escopo efetivo
UP Zero (customers, orders, analytics/facts) → Python/Cloud Run Jobs → sanitização → BigQuery up_raw → transformação/versionamento → up_core → qualidade/up_ops. up_analytics é apenas dataset vazio. Cloud Scheduler tem schedules pausados; Secret Manager é resolvido por referência de conexão. Terraform descreve recursos, sem apply. TypeScript/Node não é usado nesta fase.

## Decisão aprovada de RAW
A instrução da Fase 1 substitui RAW byte a byte: credenciais e autenticação são redigidas antes de persistir. Dados comerciais e de tracking permanecem, inclusive CPF/CNPJ quando presentes, click IDs, UTMs, landing_url e referrer. Exceções explícitas: parâmetros secretos em URLs e recovery_url. Payload e hash são sanitizados; headers nunca são armazenados. Ver [SECURITY](SECURITY.md).

## Decisões implementadas
- Chaves sempre por loja e ID; apenas uma conexão UP Zero ativa por loja no piloto.
- RAW+checkpoint pending gravados antes de CORE. Promoção de página em transação com histórico/OPS.
- Estado corrente e versões; replay antigo não desfaz observação posterior. Mudança de Fact cria versão, sem duplicata corrente.
- SQL parametrizado de staging em memória (até 8 MB) evita load por página e interpolação de payload.
- SQLite é adaptador offline para testes; BigQuery é o destino cloud.
- Bucket técnico GCS acrescentado apenas para mutex distribuído, sem dados da fonte. Criação condicional, sem expiração automática; recuperação pós-crash exige operador. Não usar BigQuery como lock.
- Scheduler, runtime e acessos de dados separados; ingestão/transformação usam mesma identidade no piloto. Sem papéis de BI.
- Somente coocorrências de identidade; nenhuma equivalência user_id/customer_id ou atribuição implementada.

## Expansão futura e riscos
Meta Marketing API, demais Ads, campanhas/gastos, LTV/CAC/ROI/coortes/customer_360, Dashboard/MCP/IA continuam fora de escopo. Milhões de eventos requerem medir custo de SQL, tamanho de página, quotas e tempo do backfill; não há benchmark de produção. Jobs têm limite de uma hora; distribuir reconciliação histórica conforme volume.

Pontos humanos para teste piloto: projeto/região/localização, conta/loja corretas, secret existente, IAM/retenção, intervalo pequeno, SLA e vigência de purchase.order_id. Ver [README](../README.md). Nenhum campo de pagamento liquidado, customer_id derivado de user_id ou conta Meta foi inventado.

## Fonte e rastreabilidade
OpenAPI 3.1.0/API 1.0.0: 41 caminhos, 66 operações, 97 schemas. SHA-256 `47e863d1942ba4074faaace1398e97fb25f3a1c25e3ab65bed01cafe33b21043`. Inventário abaixo é capacidade da API, não escopo implementado; só três GETs estão habilitados no conector.

## 8. Inventário completo de operações
Leitura analítica usa GET. Operações de escrita constam abaixo para mapear capacidades; não serão chamadas. Limites de batch: produtos 50 itens, ajustes de estoque 100. Quotas por segundo/dia, SLA e retenção não estão especificados.

| Método | Caminho | Finalidade |
|---|---|---|
| GET | `/external/v1/products` | Listar produtos da integração externa |
| POST | `/external/v1/products` | Criar produto (integração externa) |
| POST | `/external/v1/products/batch` | Criar ou atualizar produtos em lote |
| GET | `/external/v1/products/{product_id}` | Obter produto da integração externa por ID interno |
| PATCH | `/external/v1/products/{product_id}` | Atualizar produto da integração externa (parcial) |
| DELETE | `/external/v1/products/{product_id}` | Arquivar produto da integração externa |
| GET | `/external/v1/products/by-code/{code}` | Obter produto da integração externa por código interno |
| GET | `/external/v1/products/{product_id}/images` | Listar imagens do produto na integração externa |
| POST | `/external/v1/products/{product_id}/images` | Adicionar imagem ao produto na integração externa |
| PATCH | `/external/v1/products/{product_id}/images/{image_id}` | Atualizar imagem do produto na integração externa |
| DELETE | `/external/v1/products/{product_id}/images/{image_id}` | Remover imagem do produto na integração externa |
| GET | `/external/v1/products/{product_id}/videos` | Listar vídeos do produto na integração externa |
| POST | `/external/v1/products/{product_id}/videos` | Adicionar vídeo ao produto na integração externa |
| PATCH | `/external/v1/products/{product_id}/videos/{video_id}` | Atualizar vídeo do produto na integração externa |
| DELETE | `/external/v1/products/{product_id}/videos/{video_id}` | Remover vídeo do produto na integração externa |
| GET | `/external/v1/attributes` | Listar atributos da integração externa |
| POST | `/external/v1/attributes` | Criar atributo da integração externa |
| DELETE | `/external/v1/attributes/{attribute_id}` | Remover atributo da integração externa |
| GET | `/external/v1/attributes/{attribute_id}/terms` | Listar termos de um atributo da integração externa |
| POST | `/external/v1/attributes/{attribute_id}/terms` | Criar termo em um atributo da integração externa |
| DELETE | `/external/v1/attributes/{attribute_id}/terms/{term_id}` | Remover termo de atributo da integração externa |
| GET | `/external/v1/attributes/by-code/{attribute_code}/terms` | Listar termos de um atributo por código na integração externa |
| POST | `/external/v1/attributes/by-code/{attribute_code}/terms` | Criar termo em um atributo por código na integração externa |
| GET | `/external/v1/categories` | Listar categorias da integração externa |
| POST | `/external/v1/categories` | Criar categoria da integração externa |
| GET | `/external/v1/categories/{id}` | Obter categoria da integração externa por ID |
| PUT | `/external/v1/categories/{id}` | Atualizar categoria da integração externa |
| DELETE | `/external/v1/categories/{id}` | Remover categoria da integração externa |
| GET | `/external/v1/categories/{id}/children` | Listar categorias filhas da categoria pai |
| GET | `/external/v1/internal-categories` | Listar categorias internas do ecommerce |
| POST | `/external/v1/internal-categories` | Criar categoria interna do ecommerce |
| GET | `/external/v1/internal-categories/{id}` | Obter categoria interna por ID |
| PUT | `/external/v1/internal-categories/{id}` | Atualizar categoria interna |
| DELETE | `/external/v1/internal-categories/{id}` | Remover categoria interna |
| GET | `/external/v1/internal-categories/{id}/children` | Listar categorias internas filhas da categoria pai |
| GET | `/external/v1/variants` | Listar variantes da integração externa |
| POST | `/external/v1/variants` | Criar variante da integração externa |
| GET | `/external/v1/variants/{variant_id}` | Obter variante da integração externa |
| PATCH | `/external/v1/variants/{variant_id}` | Atualizar variante da integração externa |
| DELETE | `/external/v1/variants/{variant_id}` | Inativar variante da integração externa |
| GET | `/external/v1/inventory/availability` | Consultar disponibilidade de estoque da variante na integração externa |
| POST | `/external/v1/inventory/adjust` | Ajustar estoque da variante na integração externa |
| POST | `/external/v1/inventory/adjust/batch` | Ajustar estoque em lote na integração externa |
| GET | `/external/v1/orders` | Listar pedidos da integração externa |
| POST | `/external/v1/orders` | Criar pedido da integração externa |
| GET | `/external/v1/coupons` | Listar cupons da integração externa |
| POST | `/external/v1/coupons` | Criar ou atualizar cupom da integração externa |
| GET | `/external/v1/coupons/{coupon_id}` | Obter cupom da integração externa |
| GET | `/external/v1/customers` | Listar clientes da integração externa |
| POST | `/external/v1/customers` | Criar cliente da integração externa |
| GET | `/external/v1/customers/{customer_id}` | Obter cliente da integração externa |
| PATCH | `/external/v1/customers/{customer_id}` | Editar cliente da integração externa |
| GET | `/external/v1/orders/{order_id}` | Obter pedido da integração externa |
| PATCH | `/external/v1/orders/{order_id}` | Atualizar pagamento e endereço do pedido |
| PATCH | `/external/v1/orders/{order_id}/status` | Atualizar status do pedido |
| POST | `/external/v1/orders/{order_id}/cancel` | Cancelar pedido da integração externa |
| POST | `/external/v1/invoices` | Receber dados de NF-e de integração fiscal externa |
| GET | `/external/v1/invoices/{order_id}` | Buscar invoice (NF-e) de um pedido |
| POST | `/external/v1/labels` | Registrar ou atualizar etiqueta de envio de um pedido |
| GET | `/external/v1/labels/{order_id}` | Buscar etiqueta de envio de um pedido |
| GET | `/external/v1/webhooks` | Listar webhooks da integração externa |
| POST | `/external/v1/webhooks` | Criar webhook da integração externa |
| DELETE | `/external/v1/webhooks/{webhook_id}` | Remover webhook da integração externa |
| GET | `/external/v1/webhooks/logs` | Listar logs de entrega de webhook |
| GET | `/external/v1/analytics/metrics` | Listar métricas de analytics por período |
| GET | `/external/v1/analytics/facts` | Listar eventos detalhados de analytics (facts) |

## 9. Parâmetros de leitura — inventário integral

Nomes, obrigatoriedade, limites, enums e semântica copiados do contrato. Ausência de required equivale a opcional.

### GET /external/v1/products

Por padrão, retorna apenas produtos ativos (`status: active`).
Use `include_inactive=true` para incluir produtos inativos na listagem.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 200, "default": 10} | Quantidade máxima de registros retornados por página. |
| cursor / query | não | {"type": "string"} | Cursor de paginação retornado na resposta anterior. |
| integration / query | não | {"type": "string"} | Identificador da integração (ex: bling, tiny, manse, custom_erp). |
| include_inactive / query | não | {"type": "boolean", "default": false} | Quando `false` ou omitido (padrão), retorna apenas produtos ativos.<br>Quando `true`, inclui também produtos inativos (excluídos soft delete continuam fora).<br> |
| external_id / query | não | {"type": "string"} | Filtra por external_id no contexto da integração. |
| code / query | não | {"type": "string"} | Filtra por código interno do produto. |

### GET /external/v1/products/{product_id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| product_id / path | sim | {"type": "string"} | ID interno do produto. |

### GET /external/v1/products/by-code/{code}

Por padrão, retorna apenas produtos ativos (`status: active`).
Use `include_inactive=true` para buscar produtos inativos pelo código.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| code / path | sim | {"type": "string"} | Código interno do produto. |
| include_inactive / query | não | {"type": "boolean", "default": false} | Quando `false` ou omitido (padrão), retorna apenas produtos ativos.<br>Quando `true`, inclui também produtos inativos (excluídos soft delete continuam fora).<br> |

### GET /external/v1/products/{product_id}/images

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| product_id / path | sim | {"type": "string"} | ID interno do produto. |

### GET /external/v1/products/{product_id}/videos

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| product_id / path | sim | {"type": "string"} | ID interno do produto. |

### GET /external/v1/attributes

Nenhum parâmetro documentado.

### GET /external/v1/attributes/{attribute_id}/terms

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| attribute_id / path | sim | {"type": "string"} | ID interno do atributo. |

### GET /external/v1/attributes/by-code/{attribute_code}/terms

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| attribute_code / path | sim | {"type": "string"} | Código do atributo no escopo da loja (ex: color, size). |

### GET /external/v1/categories

Loja resolvida automaticamente por Authorization Bearer (JWT com store_id) ou X-API-Key.
Retorna categorias pai com o array `children`.
Quando `parent_id` é informado, retorna apenas a categoria pai correspondente com seus filhos.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| status / query | não | {"type": "boolean"} | Filtra por status da categoria externa (ativa/inativa). |
| parent_id / query | não | {"type": "integer", "format": "int64"} | Filtra por categoria pai específica (retorna pai e filhos). |

### GET /external/v1/categories/{id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| id / path | sim | {"type": "integer", "format": "int64"} | ID interno da categoria. |

### GET /external/v1/categories/{id}/children

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| id / path | sim | {"type": "integer", "format": "int64"} | ID interno da categoria. |

### GET /external/v1/internal-categories

Loja resolvida automaticamente por Authorization Bearer (JWT com store_id) ou X-API-Key.
Retorna categorias pai com o array `children`.
Quando `parent_id` é informado, retorna apenas a categoria pai correspondente com seus filhos.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| status / query | não | {"type": "boolean"} | Filtra por status da categoria interna (ativa/inativa). |
| parent_id / query | não | {"type": "integer", "format": "int64"} | Filtra por categoria pai específica (retorna pai e filhos). |

### GET /external/v1/internal-categories/{id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| id / path | sim | {"type": "integer", "format": "int64"} | ID interno da categoria. |

### GET /external/v1/internal-categories/{id}/children

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| id / path | sim | {"type": "integer", "format": "int64"} | ID interno da categoria. |

### GET /external/v1/variants

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 200, "default": 10} | Quantidade máxima de registros retornados por página. |
| cursor / query | não | {"type": "string"} | Cursor de paginação retornado na resposta anterior. |
| product_id / query | não | {"type": "string"} | Filtra variantes por ID interno do produto. |
| sku / query | não | {"type": "string"} | Filtra variantes por SKU. |
| integration / query | não | {"type": "string"} | Identificador da integração (ex: bling, tiny, manse, custom_erp). |
| external_id / query | não | {"type": "string"} | Filtra por external_id da variante na integração. |

### GET /external/v1/variants/{variant_id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| variant_id / path | sim | {"type": "string"} | ID interno da variante. |

### GET /external/v1/inventory/availability

Consulte por `variant_id` **ou** `sku`.
Se ambos forem enviados, `variant_id` tem prioridade.
Se `sku` for ambíguo na loja, retorna erro 400.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| variant_id / query | não | {"type": "string"} | ID interno da variante para consulta de disponibilidade (opcional se `sku` for informado). |
| sku / query | não | {"type": "string"} | SKU da variante para consulta de disponibilidade (opcional se `variant_id` for informado). |

### GET /external/v1/orders

Retorna pedidos ordenados por `id` em ordem decrescente (mais recentes primeiro).
A paginação é baseada em páginas: use `page` para navegar e `total_pages` na resposta para saber o total de páginas.
Cada pedido inclui `payment_method` (`pix`, `boleto`, `credit_card`, `faturado`) e, quando for cartão, `installments`.

Totais de solicitado vs atendido:
- `requested_total` / `requested_items_qty`: valor e quantidade **solicitados** (`original_qty` de todos os itens, inclusive `removed`).
- `fulfilled_total` / `fulfilled_items_qty`: valor e quantidade **atendidos** (`qty` dos itens `active` e `attended`).
- Itens com `status: removed` (soft delete) entram no solicitado, não entram no atendido e continuam em `items`.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 200, "default": 10} | Quantidade máxima de registros retornados por página. |
| page / query | não | {"type": "integer", "minimum": 1, "default": 1} | Número da página (começa em 1). |
| status / query | não | {"type": "string", "enum": ["RESERVED", "CONFIRMED", "PROCESSING", "INVOICED", "SHIPPED", "CANCELED"]} | Filtra pedidos por status. Valores possíveis: `RESERVED` (aberto/aguardando pagamento), `CONFIRMED` (aprovado/pago), `PROCESSING` (em processamento/separação), `INVOICED` (nota fiscal emitida), `SHIPPED` (despachado/entregue), `CANCELED` (cancelado).<br> |
| integration / query | não | {"type": "string"} | Identificador da integração (ex: bling, tiny, manse, custom_erp). |
| external_id / query | não | {"type": "string"} | Filtra pedidos por external_id no contexto da integração. |
| start_date / query | não | {"type": "string", "format": "date", "example": "2026-03-01"} | Data inicial (inclusiva) para filtrar por created_at do pedido na timezone configurada por EXTERNAL_ORDERS_DATE_TZ (padrão America/Sao_Paulo). |
| end_date / query | não | {"type": "string", "format": "date", "example": "2026-03-31"} | Data final (inclusiva) para filtrar por created_at do pedido na timezone configurada por EXTERNAL_ORDERS_DATE_TZ (padrão America/Sao_Paulo). |

### GET /external/v1/coupons

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 200, "default": 50} | — |
| search / query | não | {"type": "string"} | Busca por name ou code. |
| code / query | não | {"type": "string"} | Filtra por código exato (case insensitive). |
| status / query | não | {"type": "boolean"} | — |
| integration / query | não | {"type": "string", "example": "firebase"} | — |
| external_id / query | não | {"type": "string"} | — |

### GET /external/v1/coupons/{coupon_id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| coupon_id / path | sim | {"type": "string"} | — |

### GET /external/v1/customers

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 200, "default": 50} | Limite de clientes retornados. |
| search / query | não | {"type": "string"} | Busca por nome, email, CPF/CNPJ. |
| start_date / query | não | {"type": "string", "format": "date", "example": "2025-01-01"} | Filtro por data de criação (início, formato: YYYY-MM-DD, UTC). |
| end_date / query | não | {"type": "string", "format": "date", "example": "2025-12-31"} | Filtro por data de criação (fim, formato: YYYY-MM-DD, UTC). |
| integration / query | não | {"type": "string", "example": "firebase"} | Filtra por `external_ref.integration`. |
| external_id / query | não | {"type": "string"} | Filtra por `external_ref.external_id` (ex. Firebase user id). |
| after_id / query | não | {"type": "integer", "format": "int64"} | Cursor de paginação. Retorna clientes com `id` menor que este valor (`ORDER BY id DESC`). |

### GET /external/v1/customers/{customer_id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| customer_id / path | sim | {"type": "string"} | ID interno do cliente. |

### GET /external/v1/orders/{order_id}

Retorna o pedido com os mesmos totais da listagem:
`requested_total` / `requested_items_qty` (solicitado) e
`fulfilled_total` / `fulfilled_items_qty` (atendido, itens `active` e `attended`).
Itens `removed` (soft delete) entram no solicitado e permanecem em `items`.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| order_id / path | sim | {"type": "string"} | ID interno do pedido. |

### GET /external/v1/invoices/{order_id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| order_id / path | sim | {"type": "string"} | ID interno do pedido. |

### GET /external/v1/labels/{order_id}

| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| order_id / path | sim | {"type": "string"} | ID interno do pedido. |

### GET /external/v1/webhooks

Retorna os webhooks cadastrados para a loja autenticada.

Eventos suportados atualmente:
  - cart_created
  - cart_abandoned
  - cart_converted
  - customer.created
  - customer.updated
  - order.created
  - order.updated
  - order.confirmed
  - order.payment_confirmed
  - order.shipped
  - order.delivered
  - order.cancelled
  - payment_link.created
  - payment_link.updated
  - payment_link.cancelled
  - payment_link.expired
  - payment_link.completed
  - payment_link.payment_failed

Observação para eventos de carrinho (`cart_created`, `cart_abandoned`, `cart_converted`):
  - O payload em `data` inclui `phone`, `customer_phone`, `customer_name`, `contact_name` e `customer.phone` quando disponíveis.
  - O telefone é resolvido a partir de `customers.phone` ou do `meta` do carrinho (`checkout.customer.phone`, etc.).

Observação para `cart_abandoned`:
  - O payload enviado em `data` inclui `recovery_token` e `recovery_url`,
    que podem ser usados para recuperar o carrinho no storefront.


Nenhum parâmetro documentado.

### GET /external/v1/webhooks/logs

Retorna os logs de entrega dos webhooks da loja autenticada.
O tenant é resolvido por X-API-Key ou Authorization Bearer.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| webhook_id / query | não | {"type": "integer", "format": "int64"} | Filtra logs por ID do webhook. |
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 500, "default": 100} | Quantidade máxima de logs retornados. |

### GET /external/v1/analytics/metrics

Retorna métricas pré-agregadas de analytics_event_metrics filtradas por período.
Os dados são gerados pelo tracking-worker Cloudflare e acumulados via cron.
Suporta ordenação e paginação por cursor para leitura incremental.

Quando o evento ocorreu no contexto de link de vendedora (`/v/{seller_slug}`),
a linha inclui `seller` com `id`, `name` e `seller_slug`. Use o filtro
`seller_id` para isolar o tráfego de uma vendedora.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| from / query | sim | {"type": "string", "format": "date-time", "example": "2026-05-01T00:00:00Z"} | Início do período (inclusivo). ISO 8601. |
| to / query | não | {"type": "string", "format": "date-time", "example": "2026-05-31T23:59:59Z"} | Fim do período (exclusivo). Padrão é o momento atual. ISO 8601. |
| event_name / query | não | {"type": "string", "enum": ["page_view", "category_view", "product_view", "whatsapp_button_click", "register_start", "register_submitted", "login", "add_to_cart", "cart_view", "remove_from_cart", "checkout_started", "checkout_delivery", "checkout_payment", "checkout_review", "purchase", "search", "product_item_impression", "product_item_click", "order_created", "order_paid", "order_approved"]} | Filtra por nome do evento. |
| period_type / query | não | {"type": "string", "enum": ["hour", "day", "week", "month"], "default": "hour"} | Granularidade do período. |
| device_type / query | não | {"type": "string", "enum": ["desktop", "mobile", "tablet"]} | Filtra por tipo de dispositivo. |
| product_id / query | não | {"type": "integer"} | Filtra por ID do produto. |
| product_variant_id / query | não | {"type": "integer"} | Filtra por ID da variante. |
| category_id / query | não | {"type": "integer"} | Filtra por ID da categoria. |
| order_id / query | não | {"type": "integer"} | Filtra por ID do pedido. |
| seller_id / query | não | {"type": "integer", "format": "int64"} | Filtra por ID da vendedora (`admins.id`) atribuída via link `/v/{seller_slug}`.<br>Use para isolar tráfego/conversão de uma vendedora específica.<br> |
| source / query | não | {"type": "string"} | Filtra por origem lógica do evento (ex. site, app, admin). |
| channel / query | não | {"type": "string"} | Filtra por canal de negócios (ex. b2b, b2c). |
| utm_source / query | não | {"type": "string"} | Filtra por utm_source. |
| utm_medium / query | não | {"type": "string"} | Filtra por utm_medium. |
| utm_campaign / query | não | {"type": "string"} | Filtra por utm_campaign. |
| sort_by / query | não | {"type": "string", "enum": ["period_start", "total_events", "total_value"], "default": "period_start"} | Campo de ordenação. |
| sort_dir / query | não | {"type": "string", "enum": ["asc", "desc"], "default": "desc"} | Direção da ordenação. |
| cursor / query | não | {"type": "string"} | Cursor retornado na resposta anterior (atualmente compatível com sort_by=period_start e sort_dir=desc). |
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 1000, "default": 500} | Máximo de registros retornados. |

### GET /external/v1/analytics/facts

Retorna eventos granulares da tabela analytics_event_facts.
Ideal para drilldown, investigação, funis e auditoria de tracking.


| Nome / local | Obrigatório | Tipo e restrições | Descrição |
|---|---|---|---|
| from / query | sim | {"type": "string", "format": "date-time", "example": "2026-05-01T00:00:00Z"} | Início do período (inclusivo). ISO 8601. |
| to / query | não | {"type": "string", "format": "date-time", "example": "2026-05-31T23:59:59Z"} | Fim do período (exclusivo). Padrão é o momento atual. ISO 8601. |
| event_name / query | não | {"type": "string"} | — |
| user_id / query | não | {"type": "integer"} | — |
| session_id / query | não | {"type": "string"} | — |
| visitor_id / query | não | {"type": "string"} | — |
| anonymous_id / query | não | {"type": "string"} | — |
| product_id / query | não | {"type": "integer"} | — |
| product_variant_id / query | não | {"type": "integer"} | — |
| category_id / query | não | {"type": "integer"} | — |
| order_id / query | não | {"type": "integer"} | — |
| device_type / query | não | {"type": "string"} | — |
| source / query | não | {"type": "string"} | — |
| channel / query | não | {"type": "string"} | — |
| utm_source / query | não | {"type": "string"} | — |
| utm_medium / query | não | {"type": "string"} | — |
| utm_campaign / query | não | {"type": "string"} | — |
| landing_host / query | não | {"type": "string"} | — |
| referrer_host / query | não | {"type": "string"} | — |
| cursor / query | não | {"type": "string"} | Cursor retornado na resposta anterior. |
| limit / query | não | {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200} | Máximo de registros retornados. |
