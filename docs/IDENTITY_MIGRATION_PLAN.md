# Identity hardening — plano de migração para revisão

> Escopo aprovado: somente expansão aditiva. Separação física de snapshots/ReceitaWS, up_identity, remoções e mudanças IAM estão adiadas. Aprovação do código não autoriza executar migration/apply/build/deploy/backfill.

**Preparado, não executado.** Nenhuma operação GCP, Terraform plan/apply, Job, replay ou backfill faz parte desta alteração. Sem DROP, DELETE, alteração de retenção ou IAM. Configuração MX Fashion, digest de imagem, Secret Manager e schedulers permanecem inalterados.

## Etapa 1: expansão compatível

Mudanças de schema preparadas em catálogo Python, DDL de criação e JSON Terraform:

| Tabela existente | Colunas novas, todas NULLABLE |
|---|---|
| up_core.customers | 11: email_normalized, phone_normalized, phone_e164, cnpj_digits, cpf_digits, seller_id, state, city, identity_normalization_version, external_ref, identity_normalization_issues |
| up_core.customers_versions | As mesmas 11 |
| up_core.identity_links | 9: source_entity_type, source_entity_id, identifier_type_from, identifier_value_from, identifier_type_to, identifier_value_to, confidence_type, first_seen_at, last_seen_at |

Total: **31 adições em 3 tabelas**. Nenhuma coluna existente removida ou retipada; nenhuma partição/chave de clustering alterada. Tabelas Orders/Orders_versions, RAW e Analytics não mudam de schema. `sql/migrations/003_customer_identity_metadata.sql` contém somente ADD COLUMN IF NOT EXISTS para DEV. DDL não é aplicado automaticamente pelo aplicativo. O gerador de schemas apenas escreve arquivos locais.

Antes da execução, obter aprovação e revisar o plano Terraform com backend remoto por um operador autorizado. O plano deve conter exclusivamente expansão das três tabelas pertinentes, sem replacement de datasets/tabelas; outras mudanças precisam de revisão separada. Não há contagem real de recursos add/change/destroy neste trabalho, pois nenhum plan foi executado. Se aparecer destroy/replacement, parar.

Escolher **um** executor da expansão (Terraform ou SQL revisado). Se SQL for escolhido, reconciliar o schema declarativo e revisar o plan subsequente para evitar drift. Não executar dois caminhos simultaneamente. O arquivo SQL é idempotente para colunas ausentes, mas não verifica tipos de colunas já existentes: conferir schema antes/depois.

Somente depois das colunas existirem, construir/testar nova imagem e aprovar deploy do transformador 1.1.0. Não implantar a nova imagem antes da expansão: o writer usa o catálogo atualizado e precisa das novas colunas. A imagem atualmente publicada não contém este patch; precisará de rebuild posterior. Rollback de código pode retornar à imagem anterior mantendo as colunas adicionais; não remover colunas para rollback. Writers antigos podem gravar novas linhas com campos adicionais nulos.

## Etapa 2: preenchimento controlado e evidências

1. Registrar contagens de RAW/CORE/versões, chave única store/source/entity, duplicatas, pedidos sem cliente e vínculos pendentes. Registrar só agregados/IDs técnicos necessários, sem exportar PII.
2. Campos novos permanecem nulos nos dados existentes até refresh/replay autorizado. Transform_version 1.1.0 gera versões adicionais para conteúdo reprocessado; versões 1.0.0 continuam disponíveis. Replay repetido da mesma versão não duplica entidades/evidências.
3. Replay não é um backfill automático de tudo: priorizar o RAW associado à versão corrente. RAW anterior à observação corrente é rejeitado como stale; não desativar esse guarda-corpo para preencher colunas. Se RAW corrente expirou, fazer refresh autorizado ou desenho específico de reprocessamento baseado na versão preservada, sem fabricar observed_at.
4. Testar uma amostra pequena aprovada de Customer, Order e Facts; comparar originals e derivados, contagens, pagamentos, requested/fulfilled totals, itens e capacidade de JOIN. Não tratar RESERVED/unpaid como recebimento. O cenário sintético cobre essa distinção; conferir o pedido DEV solicitado no ambiente restrito somente durante validação autorizada.
5. Não inferir user_id/customer_id por igualdade de números. Verificar resolução corrente e temporal separadamente. `purchase_order_id_effective_at` permanece null até confirmação da fonte; eventos sem order_id continuam pendentes.
6. Revisar as consultas SELECT propostas em `sql/identity/`. Elas não estão instaladas nem conectadas ao runtime. Para histórico de negócio, definir consulta as-of: observação técnica não equivale ao instante em que a relação passou a valer no mundo real.

## Etapa 3: redução de duplicação (requer nova aprovação)

Etapa ADIADA pelo responsável. Apenas proposta arquitetural; sem código de projeção ou persistência neste patch. Não existem recursos Terraform novos para esses destinos.

- Criar dataset restrito `up_identity` na localização aprovada, com acesso explicitamente revisado. Preparar `order_party_snapshots`, chave `(store_id, source_system, version_id)`, row_key=version_id, particionamento proposto observed_at e clustering store_id/order_id. Sem expiração até decisão humana de retenção; armazenamento restrito não é retenção eterna aprovada.
- Snapshot contém os metadados de linhagem, order_id/customer_id, customer_snapshot e shipping_address originais sanitizados. Uma linha por versão; RAW pode expirar sem destruir o histórico necessário.
- Criar `orders_v2` e `orders_v2_versions` comerciais, com schema comercial a revisar em uma próxima etapa. Manter customer_id e a referência à versão; preservar item_ids para reconciliação de itens. Não fazer alterações destrutivas no schema de orders original.
- Copiar snapshots a partir de **todas** orders_versions e verificar se algum current version_id está ausente nas versões; incluir a origem corrente faltante. Nunca usar Customer corrente para substituir o snapshot original. Extrair RAW somente quando necessário e disponível, mantendo a linhagem e o sanitizador.
- Copiar facts comerciais e validar chaves, contagens, valores NUMERIC, status, datas, snapshots por versão, customer_id, integridade com itens e as duas vias de reconstrução. Comparar o conteúdo sanitizado sem publicar PII. Zero versões omitidas e zero colisões não resolvidas são gates para avançar.
- Antes do cutover, drenar/parar writers autorizadamente, copiar delta final e validar novamente. Alternativa de escrita dupla exigiria um desenho transacional/testes próprios; não ativá-la implicitamente.
- Trocar writer e consumidores para v2 somente após teste de falha/replay da persistência conjunta fact+snapshot+checkpoint. Hoje não há implementação de separação de snapshots; esse gate ainda exige implementação.
- Preservar tabelas legadas em acesso restrito durante rollback e auditoria. Qualquer desativação/eliminação posterior necessita decisão explícita de retenção, plano e aprovação; não há comando de exclusão neste pacote.

## Decisões humanas e bloqueios antes do backfill

- Aprovar expansão das três tabelas e escolher SQL ou Terraform como executor, após plan sem replacements.
- Aprovar destino restrito, grupos e retenção do histórico; não conceder acesso amplo a up_core para obter somente commerce.
- Validar inventário de chaves/tipos de shipping_address e ReceitaWS, procedência e política de precedência. Sem isso não publicar CNAE/Simples/shipping_city como se fossem dados conhecidos.
- Decidir se backfill aguardará a separação física de Orders; decisão atual: avançar somente com expansão aditiva, mantendo snapshots e shipping nas tabelas atuais. A separação física está adiada e não é pré-requisito desta etapa; o backfill continua sujeito a autorização própria.
- Definir views correntes versus as-of e tratamento de IDs compartilhados/contatos inválidos. Modelo atual aceita uma conexão UP Zero ativa por loja; múltiplas conexões do mesmo namespace exigem revisão de chaves.
- Autorizar depois build/deploy, migration e replay amostral como operações distintas. Nenhuma foi executada aqui.

## Cloud Shell: gerar somente o plano DEV

Na raiz do clone atualizado do repositório, usando Terraform compatível com `~> 1.16.0` e credenciais DEV autorizadas:

```sh
git pull --ff-only origin main
terraform -chdir=infra/terraform init -input=false
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -input=false -var-file=environments/dev.tfvars -out=dev-identity-additive.tfplan
terraform -chdir=infra/terraform show -no-color dev-identity-additive.tfplan
```

O backend GCS já configurado deve apontar para `up-data-intelligence-dev-876521886531-tfstate`, prefix `foundation/dev`. Não migrar state. Se init solicitar migração ou informar backend divergente, parar e investigar. O arquivo de plano fica ignorado pelo Git e deve permanecer no ambiente autorizado.

Expectativa na ausência de drift: **0 add, 3 change in-place, 0 destroy** (customers, customers_versions, identity_links). Não é resultado de plan já executado. Interromper se houver replacement, remoção, mudança de tipo, IAM ou qualquer recurso fora do escopo. Não executar apply nesta etapa. Os dados DEV existentes não foram consultados: a compatibilidade do pedido e dos Facts foi avaliada por schema e testes sintéticos, não por uma nova consulta live.
