# Customer Intelligence Data Contract — 1.0.0

CHANGE #12, somente offline. Contrato versionado em `config/contracts/customer-intelligence.v1.json`; referência executável em `src/intelligence/data_contract.py`, sem conexão ao runtime/API existente. Este contrato não cria tabelas, migrations, consultas GCP ou endpoints públicos.

## Entidade CUSTOMER

Chave oficial: **(store_id, customer_id)**. customer_id não é global entre lojas. Identidade oficial não pode ser fabricada por nome, email/telefone fuzzy, CNPJ ou igualdade de user_id com customer_id. Um cliente sem pedidos continua válido quando possui customer_id explícito; um Fact sem vínculo não cria cliente. Múltiplos IDs explícitos permanecem entidades separadas; ambiguidade de sessão/visitante impede atribuir a interação arbitrariamente.

| Componente lógico | Responsabilidade/fonte |
| --- | --- |
| Identity | customer_id, store_id, customer_type, company_name, trade_name, state, city; perfil normalizado explícito |
| Commercial | Pedidos e quantidades solicitadas/atendidas; referência de métricas abaixo |
| Marketing | Participação paga, três escopos independentes, evidência e cobertura |
| Journey | Timeline resolvida e resumo cronológico |
| Retention | Compras qualificantes, frequência, recompra e segmentos observados |
| Health | Contrato reservado; score/status sem fórmula |

Composição de profile, commercial metrics, marketing influence, timeline e segmentation. Não criar customer_360_all_in_one nem duplicar linhas de pedidos por campanha. A futura API faz projeções sobre materializações; não executa joins de RAW no frontend.

## Evidência e relacionamentos

- **DIRECT:** relação explícita Fact.order_id → Order.customer_id; evento de pedido também deriva do pedido explícito. Aprovação de cadastro só vincula cliente com evidência explícita versionada, não pelo nome do evento.
- **CUSTOMER_JOURNEY:** caminho temporal demonstrado por sessão/visitante até conversão resolvida, sem conflito entre clientes.
- **SUPPORTED:** caminho suportado por coocorrências determinísticas explícitas (incluindo usuário), preservando versões/tempos. Não equivale a hipótese ou fuzzy matching.

Esses níveis descrevem suporte do relacionamento, não percentuais de confiança ou causalidade. Toda derivação deve carregar ou referenciar `contract_version`, `policy_hash`, `generation`, cutoff `as_of`, cobertura, regra e identificadores/versionamento das evidências em contexto interno. Uma string DIRECT isolada não prova o vínculo; o produtor deve validar os caminhos antes da projeção. O validador offline verifica estrutura/refs, não autentica a veracidade da fonte.

Identificadores técnicos e evidence_refs ficam internos; a resposta pública autorizada recebe nível e metadados de cobertura permitidos. Cliente sem vínculo/evidência não é associado por fallback. Nenhuma informação ambígua deve ganhar certeza por ser omitida da resposta.

## Marketing e campanhas

| Campo oficial | Definição |
| --- | --- |
| paid_media_influenced_lifetime | Existência de contato pago resolvido no histórico observado do cliente, independentemente de haver compra |
| paid_media_influenced_acquisition | Participação paga antes da primeira compra qualificante **observada** |
| paid_media_influenced_repeat | Participação paga entre compra qualificante anterior e compra 2+ |

Usar bool nullable: true com evidência; false significa ausência no intervalo explicitamente avaliado, não ausência absoluta no histórico da empresa; NULL significa evidência/cobertura insuficiente para avaliar. history_complete=false nunca vira true por possuir um mês completo.

**Compatibilidade:** a flag `paid_media_influenced` do Epic #10 mede influência em pedidos no intervalo de relatório; não atende automaticamente à definição acima de contato pago lifetime. Não renomear nem mapear por conveniência. Aquisição/recompra existentes também estão limitadas à cobertura materializada. Um adaptador futuro deve avaliar a cobertura e retornar NULL quando não consegue cumprir o contrato. Nenhum schema Influence ou algoritmo existente foi alterado no CHANGE #12.

`campaigns_participated`: conjunto de campaign_id conhecidos e distintos em contatos resolvidos, acompanhado do escopo/janela. `first_campaign_id`/`last_campaign_id`: primeira/última campanha **identificada** na sequência `(occurred_at,event_key)`; contatos pagos sem campaign_id não inventam campanha. `campaign_touch_count`: quantidade de Facts pagos distintos com campanha identificada, sem contar cópias por pedido/adset/ad. Não equivale ao número de campanhas. Não duplicar um Fact ao projetá-lo como paid_touch e product_view para essa contagem.

Múltiplas campanhas podem participar do mesmo pedido. Dizer “Campanha X participou da jornada”. Não dizer “gerou 100% da venda”. Totais de clientes/pedidos usam IDs distintos, não a soma de linhas por campanha. Receita por campanha é participação não aditiva, nunca divisão automática de crédito ou ROAS/CAC sem fonte de custos.

## Timeline oficial

Cada evento possui event_key, store_id, customer_id, event_type, occurred_at, order_id/campaign_id nullable e evidence_type. event_key é estável por origem/regra/entidade, não um índice da lista. Referências auditáveis ficam internas. Ordenação por occurred_at UTC e event_key como desempate; cutoff as_of exclusivo. Ingestão tardia não troca occurred_at por horário de chegada.

| Categoria | Eventos e condições |
| --- | --- |
| MARKETING | paid_touch e campaign_interaction exigem sinal pago/campanha comprovado; page_view e product_view exigem Fact observado |
| IDENTITY | register_submitted, register_approved, login exigem observação e vínculo resolvido; não criam identidade por si |
| COMMERCIAL | cart_created exige criação explícita de carrinho; checkout_started e purchase preservam observação; order_created deriva do pedido; order_updated exige versões/mudança demonstrada |
| RETENTION | repeat_purchase deriva da compra qualificante 2+; reactivation depende de futura policy de inatividade |

Vocabulário oficial não significa que todos os eventos já tenham produtor. `add_to_cart` não equivale automaticamente a `cart_created`; snapshot atual não prova `order_updated`; não gerar `reactivation` sem regra aprovada. Evento desconhecido ou sem evidência não entra na timeline oficial; permanece auditável na fonte/camada apropriada, sem apagar RAW. Timeline atual event_name/confidence_type precisará de adaptador explícito; nenhuma tradução automática foi ativada.

Evento atrasado válido demanda nova geração/publicação autorizada e recomputação dos segmentos/resumos afetados. Repetição da mesma chave não duplica; o validador de referência rejeita duplicatas para exigir resolução upstream. Clientes sem eventos têm timeline vazia, não eventos inventados.

## Segmentação e Health

Segmentos são flags independentes, não classificação mutuamente exclusiva. Cada avaliação futura deve ter regra/versionamento, as_of, cobertura e motivo. NULL é diferente de false.

| Segmento | Regra oficial nesta etapa |
| --- | --- |
| NEW_CUSTOMER | Exatamente uma compra qualificante observada; sem inferir que acabou de comprar ou que nunca comprou antes do histórico disponível |
| REPEAT_CUSTOMER | purchase_count > 1 no histórico observado |
| PAID_ACQUIRED | paid_media_influenced_acquisition=true; desconhecido propaga NULL |
| ACTIVE_CUSTOMER | Atividade recente; pendentes definição de atividade e janela de recência; NULL até aprovação |
| HIGH_VALUE_CUSTOMER | Relevância por solicitado, atendido e frequência; pendentes thresholds, período e combinação AND/OR; NULL |
| AT_RISK | Histórico elegível sem atividade recente; pendentes elegibilidade, atividade e janela; NULL |

`health_score=null`, `health_status=null`, cálculo NOT_DEFINED. Não inventar escala 0–100, pesos, cortes ou rótulo saudável. Fatores futuros: recência, frequência, solicitado/atendido, recompra, influência de mídia e atendimento. Aprovação comercial necessária antes de fórmula/segmentos pendentes. Isso não bloqueia a documentação e os testes offline.

## Multi-tenant, segurança e limitações

Toda entidade, coleção e evidence lookup é delimitado por store_id. IDs iguais entre lojas não autorizam cruzamento. Principal autenticado e allowlist de lojas precedem consulta/cache. Nenhum admin recebe acesso global implicitamente.

Classificação de **dados**, diferente de role de usuário:

- INTERNAL: customer_id, IDs técnicos e refs de evidência; acesso operacional autorizado e minimizado.
- ANALYTICS: empresa, localização e métricas para consumo autorizado; continuam confidenciais e podem conter dados pessoais.
- RESTRICTED: CPF, CNPJ completo, telefone, email; não expor automaticamente, inclusive a admin. Nenhum endpoint desse contrato os inclui.

viewer/manager/admin existentes continuam sem bypass. customer_id é exceção explícita de projeção para endereçar a entidade autorizada; não expõe demais identificadores internos. Não logar payloads/URLs/identidades; retenção, exclusão e controles LGPD exigem projeto próprio, não apenas remover campos da resposta.

Product_id canônico segue não resolvido onde CORE não fornece relacionamento: não inventar a partir de SKU/asset_id. Receita atendida não prova pagamento; lifetime não significa histórico completo. Health e reativação seguem não definidos. Estes limites devem aparecer na futura interface.
