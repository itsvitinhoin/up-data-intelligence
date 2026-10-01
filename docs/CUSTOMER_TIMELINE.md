# CHANGE #09 — Customer Timeline Layer (offline)

> Proposta/reference offline histórica. O contrato físico live DEV vigente é [CHANGE #16](CHANGE_16_DEV.md): nomes Meta `meta_live_*`, generation INT64 e publicação Intelligence independente. Conteúdo anterior preservado para auditoria.

A timeline mostra a jornada **observada e resolvida** de cada cliente, sem inventar
história quando a identidade não está comprovada. Mesmo resolver da influência:
`src/influence/identity.py`. Modelo: `analytics_customer_timeline`.

## Grão e conteúdo

Uma linha por evento de jornada por store/customer:
- `record_type=FACT`: uma linha por fact_id resolvido; campos originais event_id,
  event_name, occurred_at, session/visitor/user, IDs Meta/UTMs, produto, valor,
  quantidade, channel/source/device. `variant_id` mapeia exatamente
  CORE.product_variant_id; não inventamos coluna CORE nova.
- `record_type=ORDER`: uma linha derivada de cada pedido conhecido do cliente,
  event_name=order_created e occurred_at=orders.created_at. Não é Fact de tracking:
  fact_id/event_id NULL, sem sessão ou campanha inferida. Preserva requested_total,
  fulfilled_total, requested_items_qty, fulfilled_items_qty e order_status.

O pedido derivado e um purchase Fact podem coexistir: representam evidências
*diferentes*. A UI não deve contar ambos como duas compras nem somar receita por
linha da timeline. `value` é valor original do Fact, inclusive sinal; não é fallback
de requested/fulfilled. Métricas B2B são colunas separadas nas linhas ORDER.

row_key estável inclui store/customer e namespace FACT ou ORDER e seu ID. Não
colide quando order_id=fact_id; event_id repetido em Facts distintos não remove
histórico. Saída ordenada customer, occurred_at, row_key; não fabrica uma ordem
causal entre timestamps iguais. Eventos após/igual as_of são excluídos. Timeline
inclui todo histórico **fornecido** anterior ao cutoff, não só report_from/report_to
que limita pedidos nos agregados de influência.

## Ordem de resolução

### 1. Pedido explícito

Fact.order_id→orders.customer_id→customer existente, na mesma store/source upzero.
Tem precedência sobre tracking compartilhado. confidence_type=DIRECT, identity_path
com order_id/customer_id e versão quando disponível. Order_id declarado mas ausente
ou cliente não encontrado não faz fallback adivinhado para outro cliente.
Cancelados podem resolver identidade/timeline; não se tornam compra qualificante.

### 2. Cadastro aprovado

O nome register_approved NÃO contém um customer_id confiável por si só. É necessária
prova explícita, versionada, na lista de identity_links fornecida offline:

- store_id/source_system=upzero e link_id único;
- source_fact_id do register_approved, source_version_id igual à versão desse Fact;
- left_namespace=fact_id, left_id=esse Fact;
- right_namespace=customer_id, right_id=cliente existente;
- confidence_type=DETERMINISTIC;
- evidence_type=observed_registration_customer;
- occurred_at igual ao timestamp do register_approved.

Este é um **contrato opcional de evidência**, não afirmação de que a API fornece
esse relacionamento. O normalizador Foundation atual não produz esses links.
Eles só podem vir de fonte/prova explícita autorizada; esta entrega não os cria no
CORE nem deriva right_id de user_id. first_seen_at/last_seen_at são tempos de
observação, não intervalos de validade de pessoa.

Com prova válida, o próprio cadastro resolve; outros Facts anteriores podem ligar
pela mesma session/visitor, sem ambiguidade. Não se usa user_id para a etapa cadastro.
Cadastros/contatos posteriores não são unidos indefinidamente: eventos após esse
anchor precisam pedido explícito ou outro anchor temporal posterior válido.

### 3. Jornada temporal antes da compra

Anchor purchase/purchase_item contém order_id conhecido e ocorre a partir de
order.created_at e antes de as_of. Fact candidato deve ser anterior à criação do
pedido e ao anchor. Igualdade session/visitor liga a esse cliente. Para user_id,
exigem-se duas provas session→user observed_cooccurrence, confidenceDETERMINISTIC,
source_fact_id/source_version_id/occurred_at correspondentes a cada evento.
Igualdade numérica user_id/customer_id nunca é um vínculo.

confidence_type: DIRECT para sessão de conversão, CUSTOMER_JOURNEY para visitor/
cadastro e SUPPORTED para user comprovado sem ligação direta. identity_path preserva
anchors/versões/tempo, namespace, cliente/pedido e link IDs; não guarda nomes/tokens.
Eventos antes de cadastro podem aparecer na timeline se depois resolvidos por
cadastro comprovado ou compra; isso é resolução retrospectiva de jornada observada.

## Ambiguidade, precedência e ausência

Namespace/ID associado a mais de um cliente nos anchors conhecidos é ambíguo; não
fazer union-find. Isso inclui anchors de pedidos cancelados na checagem de conflito.
Na etapa temporal, conflito bloqueia resolução, mesmo que outra rota fraca ofereça
um cliente. Contradição de cadastro não é arbitrada por ordem de input. Prioridade
de relação explícita por pedido permanece; não se apaga evidência forte por cookie.

Sem customer resolvido, Fact permanece nos inputs/CORE e, quando pago, na tabela de
touchpoints. Não há linha de timeline com customer inventado/NULL, pois o grão é por
cliente. O receipt expõe unresolved_facts. Essa contagem é dos Facts da store antes
de as_of; não é número de clientes perdidos nem SLA de completude.

Não há matching por nome, fuzzy email/telefone, CNPJ como dedupe ou user_id=customer.
IDs compartilhados/reutilizados podem causar falsos negativos conservadores. Não
prometemos reconstruir pessoa/dispositivo ou cadastro sem evidência na fonte.

## UI futura e limites

Pode mostrar contato pago, produto visualizado, cadastro, checkout, purchase Fact e
pedido derivado em sequência, sempre conforme dados reais fornecidos. Não fabricar
“Meta Ads Campanha X” sem ID/nome validado ou status de cadastro sem evento observado.
Nomes de campanha e identificação comercial são joins autorizados futuros por IDs;
nenhum lookup de nomes é realizado nesta camada.

Timeline é read model, não event sourcing imutável: reflete versões atuais dos
snapshots; auditoria imutável continua RAW/CORE versions existentes. Backfill histórico,
correção de identidade ou cancelamento pode alterar o próximo snapshot local.
Não remove RAW/CORE, não faz migration nem muda schemas existentes.

Schemas em `infra/terraform/paid_influence_proposed/schemas/`; partição occurred_at,
cluster store/customer/order. `calculated_at`, policy_hash, currency, as_of e flags
de cobertura dão contexto. Scope LIFETIME/ACQUISITION/REPEAT_PURCHASE muda agregados
de influência, não recorta os eventos da timeline. Materialização local reúne todos
os4 modelos num artifact atômico descrito em [PAID_MEDIA_INFLUENCE.md](PAID_MEDIA_INFLUENCE.md).

IDs/pseudônimos/identity_path/UTMs são dados restritos. Não publicar artifact real em
Git/logs nem disponibilizar para qualquer tenant. Testes desta entrega são sintéticos.
