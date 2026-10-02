# Comparação de métricas por período

Os cards usam o período imediatamente anterior com a mesma quantidade de dias locais inclusivos. Exemplo: 16–30/09 compara com 01–15/09. Não é automaticamente o mês calendário anterior; isso evita comparar durações diferentes. Loja, operação e demais filtros são preservados.

- Valores e contagens: `(atual - anterior) / abs(anterior) × 100`.
- Taxas em percentual: diferença em pontos percentuais (p.p.).
- Anterior zero e atual diferente de zero: **Sem base percentual**, com o valor anterior visível. Zero/zero representa estabilidade.
- NULL, ausência, formatos incompatíveis e cobertura insuficiente: **Comparação indisponível**, sem transformar ausência em zero.
- Tickets secundários de Novos/Recorrentes também recebem comparação quando os dois valores estão disponíveis.

`MetricComparisonLine` preserva os componentes e a identidade visual. Mostra direção, diferença, valor anterior e tooltip com datas/regra. Custos e cancelamento têm direção favorável invertida; investimento é neutro. As descrições comerciais continuam no ícone de informação.

`usePeriodComparison` faz uma leitura adicional por recurso/recorte, compartilhada pelo cache React Query entre os cards. A comparação não bloqueia o valor atual e sua falha não troca o badge de origem da página. Cancelamento via AbortSignal e keys com escopo/filtros são mantidos. Não há request por card nem coleta de todas as páginas para obter totais.

## Cobertura e dados reais

O adapter demo continua selecionado por padrão. A demonstração cobre setembro/2026; comparações fora dele ficam indisponíveis. Não foram criadas fixtures de meses anteriores.

Em preview real, só endpoints com agregado temporal compatível recebem uma leitura anterior: Overview, Aquisição, Retenção, Funil, Performance e detalhe de Campanha. A comparação usa a mesma geração, policy, loja, moeda, timezone, as_of e geração Analytics vinculada. O intervalo anterior precisa estar dentro da publicação disponível. As keys de Overview também incluem a identidade da publicação, impedindo reutilizar comparação de outra geração.

Clientes ganha indicadores de compradores no recorte; no preview real os totais vêm do agregado Overview certificado, sem somar métricas lifetime de páginas de clientes; métricas individuais que já descrevem o histórico integral não são reinterpretadas como métricas de período. Resumos integrais, listas paginadas sem agregado certificado e métricas de estoque/grade sem snapshot anterior continuam sem comparação quantitativa. Nunca calcular totais da loja a partir de uma página de 25 clientes/produtos.

Nenhuma query SQL, policy, schema, IAM ou infraestrutura foi alterada. Os budgets e guards existentes da Read API continuam aplicáveis às leituras adicionais. Nenhuma operação GCP/live foi executada para esta implementação.
