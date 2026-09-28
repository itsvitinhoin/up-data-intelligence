# Classificação e acesso — Identity Hardening

Política técnica proposta, sem aplicação de IAM nesta etapa. Classificação é contextual: um ID técnico ligado a comportamento deixa de ser dado anônimo. Termo HIGH-SENSITIVITY PII é uma categoria interna de restrição, não uma afirmação sobre categorias jurídicas da LGPD. CNPJ empresarial não implica automaticamente pessoa natural, mas pode ser ligado a titulares e contatos; tratá-lo de forma restrita neste produto.

| Dados | Classificação interna | Destino e exposição |
|---|---|---|
| API Key, access/refresh/recovery tokens, password, password_hash, cookies de autenticação | SECRET | Secret Manager para credenciais da integração; redigir credenciais acidentais na origem antes de RAW/CORE; nunca em logs/SQL/outputs |
| CPF, endereço completo, QSA identificável | HIGH-SENSITIVITY PII | Customer/profiles e histórico restrito quando necessário; sem replicação em analytics; CPF original preservado |
| Email, phone, nomes pessoais | PII | Customer restrito, originais + normalizados; snapshots históricos restritos; não em eventos/touchpoints ou logs |
| CNPJ, company_name/trade_name, enrichment empresarial | CONFIDENTIAL; elevar a PII conforme vínculo | Customer/business profiles restritos; uso analítico aprovado por projeções mínimas |
| customer_id, user_id | PII (identificadores pseudônimos) | CORE e joins autorizados, sem assumir anonimato |
| visitor_id, anonymous_id, session_id | PII (comportamento pseudônimo) | Analytics CORE restrito e grafo com tenant/fonte; session_id de analytics não é cookie de autenticação |
| order_id | CONFIDENTIAL; PII quando associado | Fact comercial e relações autorizadas |
| fbclid, fbc, fbp, gclid | PII (tracking pseudônimo) | Preservar matching; acesso restrito, não confundir fbp/fbc com secrets de autenticação |
| campaign_id, adset_id, ad_id e nomes internos | CONFIDENTIAL | STRING, join por IDs; nomes não são chave; sem conexão Meta neste patch |
| Receita, totais de pedido, descontos e pagamentos | CONFIDENTIAL | Commerce/analytics autorizado; status financeiro preservado, sem inferir receita paga |
| UTMs, landing_url, referrer | CONFIDENTIAL, elevar a PII/SECRET conforme conteúdo | Manter fonte sanitizada no CORE restrito; projetar/remover query strings em views gerais conforme política aprovada |
| store_id, connection_id, status de sync e regras de qualidade | INTERNAL | OPS/autorização operacional; IDs não substituem controle de acesso |
| Versão de schema/parser, contagens e latências agregadas | TECHNICAL | Observabilidade com allowlist; avaliar exposição contextual |
| raw_record_id/run_id/version_id e hashes de payload | INTERNAL | Linhagem; hashes não tornam o payload anônimo nem substituem contatos originais |

## Acesso recomendado, sem alteração aplicada

| Camada | Quem deve acessar | Restrição proposta |
|---|---|---|
| RAW | runtime de ingestão e auditores específicos | Sem dataset viewer para analistas gerais; consultas investigativas por principal auditável |
| CORE Identity (Customers, profiles, grafo e snapshots) | runtime e operadores autorizados de identidade | Acesso por tabela/view ou dataset restrito; dados cadastrais originais preservados |
| CORE Commerce | runtime e analistas comerciais autorizados | Enquanto Orders tem PII, expor somente view com allowlist comercial; depois orders_v2 |
| ANALYTICS | consumidores autorizados, BI/IA somente conforme necessidade | Views sem PII direta, agregação adequada e tenant explícito; sem acesso automático aos datasets fonte |
| OPS | operação/observabilidade | Allowlist, códigos de erro seguros, sem payloads ou credenciais |

`up_core` hoje reúne identidade e commerce. Uma concessão dataset-wide de leitura permite ler Customers/snapshots apesar de existir uma view reduzida. Para separar efetivamente, remover/substituir concessões amplas **somente após plano e aprovação** por acesso em tabelas/views autorizadas ou mover identidade para dataset dedicado por migração. Não basta uma view se o principal mantém acesso ao original. A proposta inicial de up_identity é para snapshots e futuro enrichment, não move Customers automaticamente.

Runtime mantém apenas permissões de execução/Jobs e leitura/escrita necessárias nos destinos aprovados; acesso ao secret específico, não a todos os secrets. Analistas não devem receber Secret Accessor, acesso a state nem permissões administrativas. Isolamento de lojas exige políticas por tenant ou destinos separados para consumidores externos: filtro store_id feito pela aplicação sozinho não é barreira IAM. Serviço interno multi-tenant e identidades consumidoras têm responsabilidades diferentes. Nenhuma permissão foi modificada neste patch.

## Preservação, LGPD e limites

Preservar originais necessários ao propósito comercial não dispensa decisões de retenção, base/finalidade de uso, atendimento a direitos e responsáveis pelo acesso. Estas decisões devem ser validadas pelo responsável por privacidade. Não excluir dados sob pretexto de minimização neste trabalho. RAW mantém 365 dias conforme DEV; retenção de snapshots/versões requer decisão explícita antes da migração.

O sanitizador continua redigindo chaves de secrets, tokens em URLs e JSON embutido, e valores conhecidos de credenciais no caminho de ingestão. A normalização acrescenta sanitização defensiva antes do CORE. Ele não identifica infalivelmente todo segredo arbitrário sem nome conhecido; nenhuma promessa de detecção universal. Logs mantêm allowlist e erros seguros; testes usam marcadores sintéticos, não credenciais reais. URLs/UTMs livres podem carregar PII residual e precisam de revisão na exposição analítica, sem apagar tracking necessário no CORE restrito.
