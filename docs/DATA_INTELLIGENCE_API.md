# Data Intelligence API — CHANGE #11 (offline)

Implementação em `src/intelligence/api.py`: adaptador Python em processo, sem listener HTTP, servidor público, SQL, SDK cloud ou descoberta de credenciais. Consome somente os quatro modelos Customer 360 e `analytics_customer_timeline` materializada. A API não recebe nem consulta analytics_events/RAW/CORE.

Contrato gerado: `docs/openapi/data-intelligence.openapi.json` (OpenAPI 3.1). Gerar com `python -m src.intelligence.contract`. Bearer authentication é contrato futuro, não autenticação implementada.

## Uso e autorização

```python
from src.intelligence.api import MaterializedAPI, Principal

# artifact é resultado materializado local. signing_key é fornecida pelo chamador,
# tem >=32 bytes e não deve ser colocada no Git nem gerada a cada requisição.
service = MaterializedAPI([artifact], cursor_key=signing_key)
principal = Principal("operador-sintetico", "viewer", frozenset({"loja-sintetica"}))
status, response = service.handle(
    "GET", "/v1/customers", {"store_id": "loja-sintetica", "page_size": "20"}, principal
)
```

Principal é contexto confiável do adaptador local. Não aceitar subject/role/stores do corpo, query ou token não validado. O futuro servidor deve verificar identidade e obter permissões no backend antes de construir Principal. `store_id` obrigatório seleciona o tenant, não concede acesso.

| Role | Escopo desta entrega |
| --- | --- |
| viewer | Leitura das projeções permitidas das lojas autorizadas |
| manager | Mesma leitura; nenhuma escrita ou permissão adicional implícita |
| admin | Mesma leitura; sem bypass de loja ou liberação automática de PII |

Sem principal/role válida: 401. Loja fora do conjunto autorizado: 403. Loja/cliente não materializado: 404. Apenas GET: demais métodos 405. Filtros inválidos/desconhecidos ou cursor inválido: 400. Resposta de erro: `{"error":{"code":"..."}}`, sem stacktrace/valores sensíveis.

## Rotas

| GET | Resposta e filtros adicionais |
| --- | --- |
| `/v1/customers` | Lista; customer_type, state, city, paid_media_influenced, has_repurchase, first_purchase_date, last_purchase_date, min_requested_revenue, max_requested_revenue |
| `/v1/customers/{customer_id}` | profile, commercial, journey, marketing, orders, products e metadata |
| `/v1/customers/{customer_id}/timeline` | Facts/ORDER derivados resolvidos em ordem cronológica; event_name, occurred_at, canal, IDs de campanha/produto/pedido e valores permitidos |
| `/v1/orders/influenced` | Pedido/cliente/campanhas/solicitado/atendido; campaign_id, customer_id, date_from, date_to, min_requested_revenue, max_requested_revenue, influence_scope |
| `/v1/campaigns/{campaign_id}/customers` | Contrato futuro, retorna 501 nesta implementação |

Todos exigem store_id e autorização. Filtros são combinados por AND. Texto é igualdade exata; booleans `true`/`false`. Datas de primeira/última compra são igualdade no timezone da policy. date_from inclusivo/date_to exclusivo filtram data local do pedido. Receita mínima/máxima é inclusiva, decimal não negativo; valores desconhecidos não passam filtro numérico. Não há filtro fuzzy nem inferência de localização.

Pedidos influenciados aceitam LIFETIME (padrão), ACQUISITION ou REPEAT_PURCHASE. campaign_count, primeira/última campanha e evidência são do escopo escolhido. Um pedido com duas campanhas continua uma linha; filtrar campanha seleciona participação, não distribui crédito financeiro.

Futuro contrato de campanha: customer_id, pedidos qualificantes influenciados deduplicados, requested_revenue, fulfilled_revenue, influence_scope e metadata, com paginação de clientes e de pedidos. Sem soma aditiva entre campanhas. Sem endpoint implementado ou consulta dinâmica nesta etapa.

## Paginação e consistência

Coleções: `page` começa em 1; `page_size` padrão 20, mínimo 1/máximo 100; `cursor` na resposta contém o token para a próxima página ou NULL. Página 2+ requer o cursor e o número correspondente. Não há salto arbitrário por offset. Repetir filtros e page_size ao usar cursor.

```text
GET /v1/customers?store_id=loja-sintetica&page_size=20&page=1
GET /v1/customers?store_id=loja-sintetica&page_size=20&page=2&cursor=<token recebido>
```

Detalhe pagina pedidos/produtos independentemente com orders_page/orders_cursor e products_page/products_cursor; page_size é compartilhado. Não aceita page/cursor genérico no detalhe. Listas retornam `{data, pagination:{page,page_size,cursor}, metadata}`. Cliente existente sem compras retorna detalhe com coleções vazias; busca sem correspondência retorna 200 com data=[]; cliente inexistente retorna 404.

Cursor assinado HMAC está vinculado a rota, loja, geração, usuário, role, coleção, filtros e tamanho da página. Não é credencial, não substitui autorização e não contém PII direta; não é criptografado. Mudança de geração exige reiniciar a paginação. Rotação/TTL de chave será responsabilidade do futuro serviço. Metadados retornam loja, geração, policy_hash, as_of, calculated_at, timezone e intervalo reportado.

A construção do adaptador exige uma geração por loja, somente tabelas permitidas, row_keys únicos e policy/geração coerentes; o snapshot é copiado. Timeline pertence ao artefato local e à mesma policy, sem consulta aos Facts originais.

## Projeções e limites

Campos são explicitamente permitidos. Não retornar CPF, CNPJ completo, email, telefone, identity_path, session_id, visitor_id, user_id, landing_url, referrer ou payloads originais. Mesmo admin não recebe esses campos. company_name e trade_name continuam dados comerciais restritos e potencialmente pessoais, sujeitos à autorização.

Dinheiro é string decimal, não float. product_id pode ser NULL com resolução canônica pendente (ver CUSTOMER_360.md). Datas e totais são observados; history_complete=false nunca significa histórico completo. Definições financeiras, qualificação, cobertura de influência e limitações de produtos seguem CUSTOMER_360.md.

Arrays de campanhas expostos são limitados a 100 IDs; marketing inclui campaigns_truncated. Em pedido, comparar campaign_count com tamanho de campaigns; influence_by_scope inclui campaign_count/campaigns_truncated. O artefato interno preserva todas as campanhas e o filtro é aplicado antes do limite de apresentação. Coleções de pedidos/produtos/timeline permanecem paginadas.

## Caminho para 100+ lojas

Esta é referência offline, com varredura/ordenação em memória e limite de entrada do materializador. Não é benchmark nem promessa de escala de produção. A futura interface deve acessar API → modelos materializados, jamais RAW/analytics_events. Próxima implementação deve usar busca por loja/cliente e keyset no armazenamento, limites de consulta/custo/tempo, índices adequados, rate limiting e observabilidade sem PII.

Cache futuro deve incluir loja, geração, policy, rota, filtros, paginação e autorização; invalidar por geração/alteração de acesso. Não compartilhar cache entre tenants. Evitar BigQuery por requisição de frontend; backend de leitura e sua atualização exigem decisão e validação separadas.
