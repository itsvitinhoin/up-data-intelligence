# UP Data Intelligence · Frontend

Base SaaS em Next.js App Router, React e TypeScript. Interface convertida do **UP Glass UI Kit oficial**, com Tailwind, componentes shadcn/Radix, TanStack Query/Table, Recharts, mapa SVG do Brasil, Lucide e Framer Motion.

## Executar localmente

Node.js 22.12+ (validado localmente com Node 25.8.2), npm e acesso ao registry para instalar dependências:

```sh
cd frontend
npm ci
npm run dev
```

Abra **http://127.0.0.1:3100**. Selecione uma identidade demonstrativa: **Admin UP** abre `/admin`; **Maria** recebe somente MX Fashion e escolhe B2B/B2C; **Gestor Lume** entra diretamente em B2B. Não é necessário `.env` nem credencial.

A sessão e os cadastros são temporários, em memória. Recarregar a página reinicia a demonstração. Nenhuma conta, convite, tenant, integração ou credencial real é criada. A senha e as credenciais das integrações são reservadas ao futuro backend seguro; os campos estão desabilitados. Nenhuma senha ou token é coletado.

## O que está implementado

- Login demonstrativo identificado por usuário; acesso vinculado à marca, sem catálogo de outras marcas para clientes. Não existe dashboard genérico de entrada.
- B2B: Overview, Clientes, Aquisição, Comercial, Performance, Produtos, Geografia e Retenção.
- B2C: Overview, Receita, Pedidos, Clientes, Retenção, Produtos, Estoque e Performance, todos como menus principais.
- Customer 360: perfil, valores/quantidades solicitados e atendidos, mídia, timeline, pedidos e produtos.
- UP Admin: cadastro de marcas e usuários vinculados, permissões e cards de integrações por marca; seleção de plataforma, ERP e contas de anúncios. Credenciais reais dependem do backend seguro.
- Filtros de período, canal e coleção; busca por nome/cidade, estado, segmento e mídia; tabelas ordenáveis e paginadas; seleção de estado no mapa; detalhes em drawer.
- Estados reutilizáveis de carregamento, vazio e erro, mensagens de cobertura e tratamento de NULL.
- Roles: ADMIN acessa configuração; MANAGER e VIEWER consultam. Não existe permissão de escrita adicional para MANAGER nesta etapa.

## Estrutura ajustada do produto

- 25 indicadores B2B em Receita/Pedidos/Clientes/Mídia e oito indicadores no Overview B2C, além dos nove de Performance. Pagamentos, receita aberta/aprovada, novos confirmados, CAC e reativação sem fonte/regra permanecem NULL.
- `/campaigns/{id}` lista clientes e pedidos participantes. `/media` e Aquisição deduplicam a união de pedidos, sem somar receita de campanhas sobrepostas.
- Customer 360 tem timeline por `(store_id,customer_id)`, incluindo carrinho e checkout. `/journey` redireciona para Clientes; não há timeline genérica.
- Geografia preservada: seis métricas, resumo do estado, ticket médio, principais cidades e acesso à carteira daquele estado.
- Retenção: transições 1→2, 2→3, 3→4 e 4→5+, média, mediana e percentual sobre a etapa anterior. As coortes sem cobertura continuam sem valores.
- Admin UP pode criar uma marca, criar seu usuário e experimentar o novo acesso após sair, enquanto a página não é recarregada. Os usuários demonstrativos são públicos no seletor; isso não é login de produção.

## Arquitetura

```text
app/                 rotas App Router, layout e boundaries
components/ui/       primitivas shadcn/Radix
components/          UP Glass, tabelas, gráficos, shell e componentes comerciais
features/            páginas funcionais, autenticação mockada e providers
hooks/               consultas TanStack e contexto de requisição
services/api/        fachada DataApi, guardas e transporte HTTP preparado
services/demo/       fixtures sintéticas e adaptador demonstrativo
config/              tenants demonstrativos e navegação
lib/                 formatação e utilitários
types/              contratos internos de apresentação
```

Os componentes não fazem `fetch`. `services/api/index.ts` escolhe explicitamente o adaptador demo. O CHANGE #15A acrescentou em `services/api/http.ts` um cliente separado para a Dashboard Read API, com validação de envelope e view models nullable; ele **não** é selecionado pela UI. As chaves de consulta incluem usuário, role, tenant, store, operação, recurso e filtros. Na troca de contexto, requisições são canceladas, cache limpo e filtros reiniciados. A administração global é uma fronteira exclusiva da UP. Novas marcas começam sem registros comerciais de outras marcas. Usuários clientes não acessam integrações nem configurações internas.

O guard de UI **não é autenticação/autorização de produção**. O backend deverá validar identidade, role e vínculo tenant/store em toda requisição. A seleção do navegador nunca concede autorização.

## Preparação para os contratos existentes

Leia [API e integração futura](docs/api-integration.md). `DataApi` é um **contrato de apresentação**, não uma cópia dos DTOs do backend. O transporte HTTP de leitura Analytics V1 está implementado separadamente, sem autenticação real ou seleção pela UI; rotas administrativas e diversas rotas de dashboard ainda não existem. Não basta trocar a URL para habilitar dados reais.

Antes do cutover visual: adequar os componentes aos view models nullable, mapear explicitamente os contratos Changes #11/#12/#14 quando forem promovidos e integrar autenticação real no backend. A Read API #15A foi implementada para Analytics V1 e é testada offline; nenhuma query real, deploy ou troca de adaptador ocorreu.

Dinheiro permanece string decimal no contrato. Conversão para Number ocorre somente na apresentação e no cenário sintético, sem pretensão de cálculo contábil. Receita atendida não é receita paga. Clientes novos/CAC ficam sem confirmação quando não há histórico completo. Campanhas participantes não recebem atribuição exclusiva e não têm receitas somáveis. Os cards e séries demonstrativos ilustram componentes; não são um ledger conciliado nem resultados da MX Fashion.

Períodos demonstrativos terminam em 30/09/2026. Filtros alteram o cenário sintético no adaptador, não consultam materializações reais. Coortes não maduras, aprovação financeira e tempos de pagamento aparecem indisponíveis. Estoque/grade são sintéticos.

## Design e fontes

[Proveniência visual](docs/design-source.md). Tokens, gradientes, raios, espaçamentos, sidebar e superfícies foram convertidos do HTML fornecido. `up-glass.css` preserva a base; `globals.css` adapta shadcn, estados e novas telas ao mesmo sistema.

Neue Montreal e Lovelace continuam prioritárias nas pilhas. Seus arquivos licenciados não foram fornecidos. Os mesmos fallbacks do HTML — Hanken Grotesk, Playfair Display e JetBrains Mono — são hospedados localmente por Fontsource, sem Google Fonts em runtime. O monograma UP segue a referência.

O mapa usa `@svg-maps/brazil`, derivado de MapSVG, CC BY 4.0, com atribuição na tela. Pontos de concentração são marcadores estaduais aproximados; não geocodificam clientes nem representam seus endereços.

## Validar

```sh
npm run test
npm run lint
npm run typecheck
npm run format:check
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright inicia/reutiliza somente o servidor local na porta 3100. Opcionalmente, `PLAYWRIGHT_CHROMIUM_EXECUTABLE` pode apontar para um Chromium já instalado. Cobertura: login, filtros/vazio, Customer 360, troca de operação, módulos B2B/B2C, mapa, drawers, formulários, roles e mobile. Testes de contrato cobrem partições, permissões, abort, NULL e contexto HTTP.

Não houve alteração de Terraform, BigQuery, jobs, policies, GCP ou integrações live. Não houve deploy, build de imagem Docker ou publicação no Git.

## Campanhas / Marketing

`/campaigns` organiza indicadores, Top 3 de criativos (CTR, CPL/custo por compra, leads/compras), séries de investimento/resultado/ROAS, plataforma e tabela de campanhas. A estrutura analítica foi inspirada em `/marketing` do repositório `itsvitinhoin/up-dash-b2b`; o design continua UP Glass.

O recurso `marketing` do adaptador demo fornece dados sintéticos por anúncio; as imagens em `public/demo-creatives` são ilustrações originais locais, não anúncios de clientes. A série diária distribui totais sintéticos uniformemente, não representa veiculação observada. Rankings usam todos os anúncios do recorte antes da paginação, excluem denominadores zero e usam compras para custo/resultado B2C. CTR agregado usa soma de cliques / soma de impressões. CPA B2B significa custo por cadastro aprovado; compras Meta não são pedidos ERP conciliados. ROAS usa receita comercial influenciada, não prova atribuição exclusiva ou lucro. Receita global usa pedidos deduplicados; receitas individuais de campanhas não são aditivas. Não há meta de ROAS presumida.

ROAS regional e demografia não são calculados sem a base necessária. A integração real deve fornecer métricas, cobertura, moeda, período e URLs autorizadas de criativos pelo adaptador autenticado; nenhum token Meta fica no navegador. Backend e integrações existentes não foram modificados.

## Período, estoque e ciclo do cliente

O período global fica no topo ao lado da busca. Atalhos: este mês, últimos 7/30/90 dias, este ano, mês passado, semana iniciada na segunda-feira e datas personalizadas inclusivas. A referência da demonstração é 30/09/2026 (America/Sao_Paulo), exibida no seletor. `from`/`to` integram a chave do cache e o transporte HTTP futuro. Pedidos são filtrados pelas datas; seus valores não são multiplicados pela duração do recorte. Campanhas usam uma cobertura sintética de setembro. Estoque é um snapshot demonstrativo, não um saldo histórico recalculado por período.

O produto exibe variantes cor × tamanho com quantidades que conciliam com o estoque total. Zero significa variante sem estoque; NULL significa desconhecido. Os detalhes de pedidos usam uma consulta autorizada por operação e ID, com itens, cores, tamanhos e quantidades, além do cliente e contatos fictícios. Linhas de itens são fixtures sintéticas e conciliam em centavos com o pedido; não foram importados contatos reais.

A progressão mostra compradores da primeira compra qualificante **observada** no período, acompanhados até a data final. Etapas 1–4 têm receita própria; 5+ reúne pedidos da quinta compra em diante. Coortes agrupam o mês da primeira compra observada; os meses seguintes medem retorno mensal, não cumulativo. Meses não fechados ficam NULL. O cenário atual contém pedidos de setembro, portanto não demonstra retenção de meses anteriores. Histórico comercial completo continua não confirmado.

Velocidade de conversão usa datas explícitas de aprovação sintética até o primeiro pedido qualificante observado. Exclui datas ausentes/inválidas/negativas e pedidos CANCELED. Faixas são exclusivas (0, 1–3, 4–7, 8–14, 15–30, 31–60, 61+ dias). Média e mediana usam apenas compradores elegíveis; não estima tempo para a base que ainda não comprou, nem assume pagamento pelo status comercial.

## Organização B2B: aquisição geral e mídia paga

Menu: Overview → Pedidos → Aquisição → Retenção → Clientes → Produtos → Geografia → Performance. O rótulo Pedidos preserva a rota `/b2b/commercial` e seu resumo comercial existente. O seletor redundante Atacado/Varejo foi removido dos filtros de página; a navegação e o seletor de operação no topo continuam disponíveis.

Aquisição B2B usa o recurso `acquisition`: todas as origens da marca, primeiros pedidos qualificantes observados no intervalo, receita/tickets da primeira compra, velocidade de conversão e respectivas listas. Um filtro de mídia herdado de outra página não restringe essa base. Primeira compra observada é selecionada depois de ordenar todo o histórico disponível, nunca pela primeira compra apenas dentro do recorte. Histórico completo permanece falso e novos clientes confirmados permanecem NULL. Não se presume cobertura de cadastros que ainda não compraram.

Performance B2B reúne clientes/pedidos influenciados, receita solicitada/atendida influenciada deduplicada, investimento, ROAS e ROI (NULL sem custos/margem), suas listas e campanhas participantes. A página Campanhas continua dedicada aos criativos e métricas de anúncios. Não houve mudança em backend, GCP ou integrações reais.

### Overview e valor do relacionamento

O Overview B2B encerra com quatro cards de relacionamento. Os cards de mídia e a lista de pedidos atribuídos saíram dessa página; Performance mantém suas listas e agora exibe duas linhas de faturamento atendido influenciado × investimento imediatamente após os oito KPIs. As séries respeitam o período e reconciliam com os totais de mídia demonstrativos.

- Frequência: pedidos qualificantes no período / clientes compradores distintos no período, de todas as origens da operação selecionada.
- LTV geral: permanece não confirmado porque o histórico está incompleto. O valor secundário é a receita atendida qualificante média por cliente no histórico disponível até o fim do recorte, explicitamente parcial, sem inferir pagamento.
- Dias para primeira compra: média entre aprovação e primeira compra qualificante observada, para primeiras compras no período. Datas ausentes, inválidas ou negativas não entram na média.
- Dias para compras recorrentes: média de cada intervalo consecutivo elegível cuja recompra ocorre no período, incluindo a compra anterior ao início do recorte. Não é uma média de médias por estágio.

Qualificantes: RESERVED, CONFIRMED, PROCESSING, INVOICED e SHIPPED; CANCELED é excluído. Ausência de base elegível resulta em NULL. Os quatro indicadores abrangem todas as origens, preservam operação, coleção e período, e usam dados sintéticos. Não há consulta ou alteração de infraestrutura real.

### Navegação direta B2B e leads da marca

Na operação B2B, Overview, Pedidos, Aquisição, Retenção, Clientes, Produtos, Geografia e Performance são links principais com ícones próprios, sem agrupador B2B. A troca de operação permanece no seletor do topo; a navegação B2C é exibida apenas nessa operação. Clientes 360° continua acessível separadamente, com nome distinto de Clientes B2B.

Overview (logo após os quatro indicadores de receita) e Aquisição compartilham os mesmos cards do recurso demonstrativo `leads`. A base é uma coorte de cadastros únicos no intervalo selecionado, incluindo não compradores e todas as origens. Leads aprovados são os membros dessa coorte aprovados até o fim do intervalo; qualificação = aprovados / cadastros. Conversão = membros aprovados com ao menos um pedido qualificante após aprovação e até o fim do intervalo / aprovados. Recompras não multiplicam o numerador; CANCELED não qualifica, aprovação futura não entra e denominador zero produz NULL. Esses cadastros sintéticos são independentes de leads Meta, de canal, coleção e filtros de cliente. Datas e operação são respeitadas. Não representam aquisição histórica comprovada nem pagamento confirmado. Integração real de cadastros/aprovações permanece pendente, sem criar endpoint de backend nesta alteração.

### Retenção, Geografia e ERP

Retenção inicia com compradores distintos, compradores com recompra, percentual recorrentes/compradores e ticket de retenção (receita atendida apenas de recompras / pedidos de recompra). O gráfico mostra a mesma razão por semana (segunda a domingo), contando compradores distintos dentro do recorte, sem calcular média de percentuais diários e sem conectar semanas sem base. Compras anteriores ao período são consideradas ao classificar recompra; CANCELED é excluído. A progressão e o cohort continuam separados, com sua base pela primeira compra observada.

Geografia adiciona aprovados sem compra e conversão ao detalhe do estado, utilizando a mesma coorte de cadastros do recurso leads: aprovados até o fim do intervalo, com ou sem compra qualificante posterior à aprovação. Esses dois campos consideram todas as origens e não seguem coleção. Estados com cadastros e nenhuma venda também são mantidos. Sem UF informada, nenhum estado é inferido. O link duplicado Clientes 360° saiu do menu; suas URLs continuam compatíveis.

ERP: referência funcional `itsvitinhoin/up-dash-b2b`, checkout local `b93552a`, `artifacts/up-dash/src/pages/erp.tsx` e `artifacts/api-server/src/services/erpMetrics.ts`. Foram adaptados os comportamentos, mantendo os componentes UP Glass:

| Área       | Métricas e funcionalidades                                                                                                                                                                                                                           |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Overview   | Líquido/bruto, pedidos/ticket, compradores/recorrentes, retenção, peças/média, descontos/taxa, devoluções/taxa, cancelamentos/valor; evolução receita/pedidos e novos observados/recorrentes; pagamentos, vendedores, estados, produtos e influência |
| Pedidos    | Busca por pedido/cliente/documento, status, ordenação e paginação de 20, linhas expansíveis com SKU/produto/categoria/cor/tamanho/quantidade/preço/custo/desconto/líquido; XLSX de todos os resultados filtrados                                     |
| Clientes   | Busca por nome/documento/email, tipo observado, período versus histórico, LTV não confirmado e receita histórica observada separada; dialog de todo histórico disponível até o fim do período; XLSX                                                  |
| Produtos   | Receita, lucro/margem, giro/cobertura, poder de venda; categorias/cores/tamanhos; busca/SKU/categoria, filtro de estoque, sete ordenações; produtos expansíveis por variante; XLSX                                                                   |
| Estoque    | Saldo, poder de venda, cobertura, SKUs zerados/negativos; grade SKU/cor/tamanho com giro, custo/margem e cobertura; filtros e XLSX                                                                                                                   |
| Vendedores | Ativos/lojas, receita/pedidos, ticket, clientes por vendedor; ranking de equipes/filiais e produtividade/participação; CSV                                                                                                                           |

O ledger ERP é **sintético e independente do UP Zero**. Os fixtures explicitamente acrescentam descontos, devoluções, custos, vendedores, filiais e pagamentos ilustrativos; não se presume que diferença solicitado/atendido seja desconto ou devolução. Receita líquida de pedidos válidos = bruto − descontos − devoluções. Cancelados ficam visíveis mas fora da receita. Giro = vendidas / (vendidas + estoque positivo); cobertura = estoque positivo / venda média diária; poder de venda = estoque positivo × preço de catálogo. Estoque é snapshot atual, não uma reconstrução histórica. Dados sem vendas têm cobertura NULL. Receita de produtos desconta as devoluções rateadas, e soma por SKU/produto reconcilia com pedidos. Lucro é comercial bruto demonstrativo, sem inferir impostos ou despesas. Novos históricos e LTV continuam desconhecidos. “Primeira observada” e valor histórico parcial são identificados como tais.

Consultas e exportações usam a operação autorizada e o período global. Busca/status/categoria filtram a tabela/exportação; KPIs e gráficos ERP mantêm o período inteiro, como na referência. Filtros de mídia/coleção herdados não restringem o ERP. Downloads são locais, XLSX verdadeiro via ExcelJS carregado sob demanda; células textuais não viram fórmulas, e CSV protege fórmulas. UUID transitivo está fixado em 11.1.1, compatível com o uso v4 de ExcelJS e sem o advisory da versão antiga. Não existe conexão, importação ou sincronização ERP real nesta entrega.

### Exportações e cadastro visual

- O ícone **i** dos cards mostra a definição da métrica ao passar o mouse ou focar pelo teclado; Escape fecha a ajuda.
- **Exportar lista** oferece CSV (UTF-8 com BOM, separador `;`) e XLSX. **Página atual** respeita a paginação; **Todos** exporta todos os registros do recorte já carregado, na ordem selecionada e em uma única aba. Marca, operação e filtros continuam delimitando os dados. Listas sem paginação têm o mesmo conjunto nas duas opções. Campos desconhecidos ficam vazios; logos, credenciais e objetos internos não são exportados automaticamente.
- **Exportar PDF**, disponível nas áreas da marca e administração, abre a impressão do navegador. Escolha **Salvar como PDF**; o CSS define **A4 vertical**. A exportação contém a página/aba ativa, filtros e todos os registros das tabelas paginadas. Não combina todas as rotas em um documento. Ative gráficos de fundo e desative cabeçalhos/rodapés do navegador para melhor resultado. Não envia dados para um serviço externo.
- Clientes da UP permite informar/editar plataforma (UP Zero, Vesti, Nuvemshop, Shopify, Outros) e ERP (Miré, Mansé, Bling, Shop9, Outros). Sem informação confirmada, permanece **Não informado**.
- O cadastro recebe upload PNG/JPEG/WebP de até 2 MB, com prévia e remoção. A imagem é decodificada e regravada em PNG de até 512 px; não aceita SVG. Assim como os demais cadastros desta demonstração, logo e tags ficam **em memória nesta sessão**, sem upload para um backend ou persistência após recarregar.

Ao conectar paginação de servidor no futuro, a opção Todos deve usar uma operação de exportação autorizada que percorra todas as páginas do mesmo recorte; o contrato atual recebe o conjunto completo do adaptador demonstrativo.

### B2C e integrações por marca

- Navegação B2C direta: Overview, Receita, Pedidos, Clientes, Retenção, Produtos, Estoque e Performance. Aquisição redireciona para Clientes; Mídia e Funil para Performance; Grade para Estoque. Links anteriores continuam válidos.
- Overview tem oito cards na ordem comercial solicitada. Aprovação financeira e percentual de pedidos pagos continuam desconhecidos enquanto não houver fonte de pagamentos. `Order.paid` no adaptador antigo significa influência de mídia e **nunca** alimenta o indicador de pagamento. O gráfico reserva a série Aprovado como `null`, exibindo Captado enquanto falta cobertura financeira.
- Performance reúne nove indicadores e o funil. Apenas Meta tem dados sintéticos de investimento; Google e TikTok permanecem desconhecidos. O investimento total é a soma das três plataformas **somente quando houver cobertura de todas**; ROAS e custo por sessão permanecem desconhecidos por isso. Taxa de conversão usa pedidos não cancelados / sessões e não afirma pagamento.
- Clientes B2C omite influência de mídia, inclusive no filtro e exportação. A classificação de primeira compra continua observada; aquisição histórica não é confirmada sem histórico completo.
- Produtos B2B/B2C mostram barras de peças vendidas por cor e tamanho, com exportação. Dados de variante são sintéticos e independentes do estoque atual; suas somas reconciliam com as unidades do produto. Recortes usam cobertura demonstrativa de setembro de 2026. Estoque representa um snapshot, não vendas acumuladas. No B2C o popup exibe faturamento captado, pedidos e compradores.
- `/admin` é a seção única **Marcas**, em cards pesquisáveis pelo nome; `/admin/integrations` redireciona para ela. O topo oferece cadastro de marca; cada card permite selecionar plataforma e ERP, editar integrações e acessar o dashboard da operação escolhida. A data de criação é registrada para marcas novas; nas marcas demonstrativas legadas, a data permanece indisponível. A bolinha verde exige contagem de conexões verificadas pelo serviço; todas as conexões demo seguem cinza porque habilitar uma configuração não conecta a API. O editor prepara Meta/Google/TikTok por cliente e troca a conta Meta do inventário demonstrativo; vínculos Meta pertencentes a outra marca são recusados.
- **Edição de API Keys reais ainda não disponível:** o editor mostra o ponto de gestão da credencial, mas o campo permanece desabilitado até existir backend autenticado com escrita em Secret Manager e autorização por marca. Chaves não são recebidas, registradas em logs, persistidas no navegador ou incluídas nas exportações. Nenhuma chamada GCP/Meta/Google/TikTok/ERP é executada. Toda configuração segue em memória de demonstração.

### B2C: Pedidos, catálogo e campanhas

- **Pedidos** reúne os indicadores de faturamento, a evolução diária e duas listas. “Pedidos no recorte” respeita período e filtros do topo; “Todos os pedidos” lê o histórico da operação autorizada, mesmo fora do recorte. `/b2c/revenue` redireciona para Pedidos. O modal B2C e sua exportação mostram somente produto, cor, tamanho, peças compradas e valor; faturamento é o valor captado. A confirmação de pagamento permanece desconhecida.
- **Análise de Produtos** mostra peças vendidas, giro (`peças vendidas / estoque atual × 100`), risco e grade quebrada. A regra demonstrativa de risco exige conversão `pedidos / views ≥ 1,5%` e ao menos uma variante sem estoque. “Promissor” exige views abaixo da mediana do catálogo e conversão ≥ 1,5%. Ambos são rótulos exploratórios, não decisões automáticas de reposição. Gráficos agrupam vendas por categoria, tamanho e cor; ranking filtra Curva A/B/C ou promissores e distingue grade completa/quebrada.
- **Estoque** usa snapshot sem filtro de período, lista produtos ativos e inativos e permite filtrá-los. Poder de venda é `estoque ativo × preço atual de venda`; produto sem preço torna o total desconhecido. Giro mensal é `faturamento captado no mês / poder de venda do estoque ativo atual × 100`, usando apenas o único mês demonstrativo disponível (setembro/2026); pode ultrapassar 100% e ainda não representa média histórica. Vendas do modal de estoque são históricas dentro da cobertura observada. O HEX das cores é metadata **sintética explícita** nos produtos demo; dados futuros sem HEX usam indicador neutro. Status ativo e preço não são inferidos do estoque.
- **Campanhas** agrupa Meta, Google, Pinterest e TikTok em submenus. Os oito indicadores usam definições por plataforma. Meta possui gasto, cliques, impressões e compras reportadas sintéticos; alcance único, atribuição de faturamento e ROAS atribuído permanecem desconhecidos. Google, Pinterest e TikTok ainda não têm cobertura. Os rankings Meta comparam CTR, custo por compra e compras reportadas. Gráficos e tabelas existentes seguem abaixo dos destaques Meta.
- **Cliente B2C** mostra Pedidos, Receita captada, Frequência de Compra (intervalo médio em dias entre compras qualificantes consecutivas observadas) e LTV. O LTV fica não confirmado porque o histórico é parcial e não existe confirmação financeira. O detalhe mantém apenas o histórico de pedidos da operação, independente do período no topo; não monta Jornada nem apresenta métricas de solicitado/atendido do B2B.
