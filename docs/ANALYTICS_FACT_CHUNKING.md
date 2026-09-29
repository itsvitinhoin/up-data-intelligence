# Facts acima de 100 mil — preparação offline

## Bloqueio e solução

O reader anterior materializava todos os Facts numa lista. O Transport recusava
mais de 100.000 linhas; o engine de referência também limita a soma de suas entradas
a 100.000. Apenas paginar e concatenar listas não resolveria o segundo bloqueio.

O runtime agora calcula os seis modelos comerciais com o engine existente e lê
Facts separadamente, por **dia local completo**. Todas as queries usam o mesmo
snapshot_at/SourceGeneration, store, source_system=upzero e limites de timestamp
do dia/as_of. Não há OFFSET, LIMIT, CDC nem leitura de Facts fora dos dias afetados.
A policy MX Fashion, seu hash, os schemas e as definições comerciais não mudam.

Cada dia começa com COUNT, COUNT DISTINCT fact_id e validação de chaves. Dias com
mais de 100.000 linhas são subdivididos por prefixos hexadecimais de SHA256(fact_id).
Os prefixos são disjuntos, contados no mesmo snapshot, e recursivamente subdivididos
até cada transporte caber. Cada folha deve retornar exatamente a contagem esperada.
O teto permanece **100.000 linhas**, acrescido de **32 MiB de JSON projetado** por
resposta; payload maior também provoca subdivisão. Um registro individual que não
cabe falha com segurança, nunca é truncado. Releituras por payload consomem orçamento.

Os seis campos projetados são preservados em SQLite temporário privado da execução
(arquivo 0600, diretório privado), com chave única fact_id, índice dia/sessão/instante/
fact_id e metadados auxiliares de ordenação. Duplicatas, inclusive entre dias, falham.
A contagem do dia precisa coincidir com o inventário antes do cálculo. O cursor
ordenado permite reduzir uma sessão inteira sem guardar sua lista em Python,
mesmo que ela atravesse folhas ou tenha mais de 100 mil eventos. Dias sem eventos
produzem a linha diária zero. NULL/whitespace session, desempate fact_id, flags de
cobertura e ordem cart→checkout→purchase preservam o engine de referência.

Nenhum chunk publica. Depois de todos os dias, os sete outputs passam pelas
validações do writer existente: **1 publication_id, 1 transação, 1 HEAD CAS e
1 receipt**. Falha de leitura/capacidade/cálculo impede staging/publicação. O spool
é removido ao sair, inclusive em falhas tratadas; encerramento abrupto depende do
ciclo de vida efêmero do container. Não é checkpoint durável nem artifact/log.
Retry antes de commit relê a fonte; depois de commit reconcilia o receipt. Falha
ambígua da transação exige reconciliação, nunca exclusão manual de HEAD/dados.

## Outros inputs

Orders, customers e order_items continuam limitados a 100 mil linhas e 32 MiB por
leitura; a soma comercial continua limitada pelo engine a 100 mil entradas.
Exceder qualquer limite aborta antes da publicação. Não se divide histórico de
clientes/cohorts arbitrariamente. Crescimento comercial exige outra etapa que
preserve fechamento de dependências. snapshot(include_events=True) permanece como
interface de referência limitada; materialize usa include_events=False e fact_chunks.

## Memória medida, não garantia de capacidade

Benchmark sintético, Python 3.13.7, macOS ARM64, 355.886 Facts, seis campos projetados,
chunks de até 25.000. Executado em processos separados, sem clientes Google.
Resultados reproduzíveis e checksums em `benchmarks/analytics_facts_355886.json`:

| Dias | Estratégia | Pico RSS MiB | SQLite MiB | RSS + SQLite MiB |
|---|---|---:|---:|---:|
| 27 | Lista de referência | 226,5 | 0 | 226,5 |
| 27 | Spool | 36,2 | 174,1 | 210,3 |
| 1 | Lista de referência | 234,4 | 0 | 234,4 |
| 1 | Spool | 41,8 | 174,9 | 216,7 |

Os checksums coincidem para cada par. **A lista sintética coube em 4 GiB**; não há
evidência de OOM para esse fixture. Isso não remove os limites técnicos nem prova
segurança para strings reais, clientes BigQuery, objetos comerciais e staging.
No Cloud Run o filesystem temporário também usa memória: RSS sozinho subestima
consumo. A soma acima não inclui pico do journal SQLite, buffers do SDK nem todo o
Job. Há teto de 512 MiB para páginas do banco/index (rollback ao exceder) e cache de
2 MiB; journal/overhead podem exceder esse teto. 32 MiB de JSON não é teto de heap
Python. Nenhuma garantia de milhões de eventos arbitrários ou de desempenho cloud.
O volume 355.886 é da cobertura CORE informada; a janela local aprovada pode conter
menos eventos. O runtime confere a contagem real por dia no snapshot escolhido.

Reprodução local, sem GCP:

```bash
python -m scripts.benchmark_analytics_facts --mode reference --facts 355886 --days 27
python -m scripts.benchmark_analytics_facts --mode spool --facts 355886 --days 27
python -m scripts.benchmark_analytics_facts --mode reference --facts 355886 --days 1
python -m scripts.benchmark_analytics_facts --mode spool --facts 355886 --days 1
```

## Custo e observabilidade

maximum_bytes_billed continua por query. O live exige também
`--maximum-total-bytes-billed`: guard operacional conservador da soma dos tetos
reservados antes de cada submissão, incluindo preflight, inventários, subdivisões,
leituras, staging, commit e reconciliação. Se o saldo não cobre outro teto, a query
não é enviada. Reservas não são devolvidas por cache, DDL ou falha. Não é estimativa
de fatura nem substituto de controles de cobrança. Bytes processados medidos são
separados; falha/metadado ausente produz desconhecido, não zero inventado.

Sem subdivisões, 27 dias não vazios requerem 54 queries de Facts (inventário+leitura),
além das demais. Prefixos podem reler partições: aumentam scans/custo mesmo com
projeções/pruning. Mais divisões ou payloads maiores exigem mais reservas. Aprovar
ambos os tetos antes do run; não há default de orçamento monetário.
Exaustão durante staging não publica. Se houver commit e a reconciliação perder
orçamento/conexão, o resultado pode ficar incerto para o cliente; reconciliar numa
nova execução, preservando a atomicidade e o receipt já confirmado no servidor.

Logs seguros: source_chunks (folhas aceitas), source_rows_read (Facts aceitos),
source_bytes_processed (queries de Facts incluindo inventários/divisões), chunk_days,
largest_chunk_rows. query_count/reserved_query_bytes são operacionais. Não logar
Fact IDs, sessões ou payloads. Métricas finais de fonte só indicam janela concluída;
falhas têm status failed, sem inventar contagem final completa.

## Infraestrutura e próximo passo

Terraform altera somente os argumentos do Job Analytics proposto e adiciona a
entrada obrigatória analytics_maximum_total_bytes_billed. Sem schemas, tabelas,
IAM, UP Zero, imagem DEV.4 ou Scheduler alterados. Runtime novo continua proposto;
nenhum plan foi executado. É necessária nova imagem para este código, sem build
nesta etapa. Primeiro run e comandos futuros estão em `ANALYTICS_FIRST_DEV_RUN.md`.

Validação local não valida execução das novas queries no BigQuery real. Uma futura
validação autorizada no DEV deve observar orçamento, memória/tempo, contagens dos
dias e reconciliação da publicação antes de consumo. Nenhuma operação GCP ocorreu.

## Validação desta alteração

388 testes passaram, incluindo mais de 100 mil Facts em um/múltiplos dias,
comparação exata ao funil de referência, mesma sessão atravessando chunks, snapshot
único, isolamento, limite por payload, duplicatas, inventário incompleto, falha
intermediária/depois de dia fechado sem publicação e retry com receipt/generation
únicos. Clientes BigQuery são fakes; nenhum teste executa SQL remoto.
Ruff lint/format, mypy (68 módulos), git diff --check e Terraform fmt/validate
passaram. O validate precisou liberar o handshake local do provider instalado,
sem init, plan ou chamadas GCP.
