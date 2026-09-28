# Segurança — decisão vigente da Fase 1

> Complemento: [classificação e acesso de identidade](DATA_CLASSIFICATION.md). Nenhuma mudança IAM aplicada; views reduzidas não restringem principais que mantêm leitura direta das tabelas fonte.


A instrução aprovada da Fase 1 substitui RAW original por **RAW sanitizado**. Nenhuma camada deve persistir senha/hash de senha, segredo, token de acesso/refresh/recuperação ou headers de autenticação. O OpenAPI original continua intacto como documentação.

## Sanitização antes da persistência
Implementação: [sanitization.py](../src/security/sanitization.py), política 1.0.0. Recursiva em objetos/arrays, insensível a caixa e separadores; valor bloqueado vira `[REDACTED]`. Trata JSON embutido em string e credenciais evidentes em texto/URL. Nomes mínimos: password, password_hash, api_key, X-API-Key, secret, access_token, refresh_token, recovery_token, authorization. Extensões incluem client_secret, private_key, cookies/headers, id_token, bearer/auth/session tokens, JWT, reset token, signing key, assinaturas de URL e recovery_url. Lista executável está no módulo e é testada.

Campos comerciais/tracking não são excluídos por conveniência: CPF/CNPJ, nome/contato, IDs, visitor/anonymous/session/user, fbclid/fbc/fbp/gclid, UTMs, landing_url/referrer, valores, produtos e status são preservados quando retornados. Em URL com segredo, somente parâmetro secreto/userinfo é redigido; URL sem segredo permanece idêntica. recovery_url é inteiramente redigida por conceder acesso a recuperação. Redação é transformação explícita documentada, não perda silenciosa de tracking.

O conector também remove qualquer ocorrência literal da chave carregada caso a resposta a ecoe. Hash de payload é calculado **depois** da sanitização. Corpo não JSON/ambíguo com chaves duplicadas falha sem persistir bytes potencialmente secretos. Respostas de erro não são armazenadas; somente códigos seguros.

Limite: não existe detector infalível de todo segredo em texto arbitrário/campo novo. Novos campos evidentemente secretos exigem teste e atualização da política antes da promoção. Não exportar RAW sem revisão. Não persistir resposta original nem seu hash como “backup”.

## Secret Manager e conexão
store → source_connection → secret_resource_name. Registro da loja não contém credencial. Runtime usa referência `projects/.../secrets/.../versions/...`, resolvida por ADC/identidade de serviço. Não cria secret nem versão; Terraform apenas concede acesso ao secret informado. Rotação troca referência/versão após validar a loja. Nenhuma chave real foi usada no desenvolvimento.

Modo offline usa chave sintética e MockTransport sem rede; arquivos locais sensíveis ficam em `.local`/`.env`, ignorados. `.env` não é carregado implicitamente. Configuração live exige `--live` e confirmação exata da loja; erros de SDK/client não são propagados textualmente.

## Logs, IAM e isolamento
Logs usam allowlist de run/store/resource/status/código/contagem; bibliotecas HTTP ficam silenciadas. Sem headers, payloads, PII de negócio ou texto livre de exceções. Os IDs operacionais de loja/run são necessários ao suporte.

Terraform concede runtime jobUser e papel customizado de leitura/escrita somente nos datasets RAW/CORE/OPS. Scheduler tem invoker dos jobs. SecretAccessor é restrito ao secret da conexão. Bucket técnico de lease permite criar/consultar/apagar objetos de lock, nunca dados fonte. Não há papéis de consulta para BI/MCP/IA, nem acesso ao up_analytics pelo runtime.

Uma conexão ativa por loja e um escritor por loja são exigidos no piloto. Chaves, joins e queries são escopados por store_id. IDs iguais entre A e B têm testes de isolamento. IAM piloto protege datasets de terceiros, mas não implementa RLS de consumidores de 100 lojas; revisar identidades/políticas antes dessa expansão.

## LGPD e retenção
A sanitização de credenciais não anonimiza dados comerciais ou de tracking. CPF, contatos e IDs de navegação continuam restritos; não compartilhar fixtures reais. Definir finalidade/base legal, retenção e atendimento de direitos com responsável de dados. A [LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) fundamenta necessidade, segurança e direitos; este repositório não certifica conformidade jurídica.

RAW possui expiração configurável explicitamente no Terraform. CORE e históricos não expiram automaticamente nesta fase: definir política antes de dados reais. Páginas RAW podem reunir várias pessoas; exclusão exige processo apropriado por registro/página e propagação de supressão a histórico/replay. Sistema completo de consentimento/exclusão não foi solicitado nem implementado. Nenhum período de retenção de exemplo deve ser aplicado sem revisão.
