# Cenários técnicos — mês de 30 dias

Gerado por `python -m scripts.estimate_scale_cost --compare`. Valores hipotéticos, não fatura/medição.

Hipóteses: 355.886 Facts/loja/mês, taxa uniforme, page_limit1000, Δ15min, lookback72h; CURRENT inclui reconcile diário de horizonte fixo30dias. Sem retries, mudanças de conteúdo ou reuso RAW; payload1500bytes, CORE efetivo1000bytes/Fact. Quality frequente48/dia; proposta deep1/dia; Analytics0 (desativado neste cenário).

| Lojas | Modelo | Observações/mês | × únicos | Páginas API/RAW | RAW GB/mês | Upserts Facts novos | Execuções Facts | Obs./CURRENT |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | current_pilot | 113,527,634 | 319.0 | 114,480 | 170.406 | 355,886 | 2,910 | 1.0000 |
| 1 | fast_reconcile_1 | 1,423,544 | 4.0 | 3,960 | 2.139 | 355,886 | 2,910 | 0.0125 |
| 1 | fast_reconcile_2 | 2,491,202 | 7.0 | 5,040 | 3.742 | 355,886 | 2,940 | 0.0219 |
| 1 | fast_reconcile_4 | 4,626,518 | 13.0 | 7,200 | 6.947 | 355,886 | 3,000 | 0.0408 |
| 10 | current_pilot | 1,135,276,340 | 319.0 | 1,144,800 | 1704.059 | 3,558,860 | 29,100 | 1.0000 |
| 10 | fast_reconcile_1 | 14,235,440 | 4.0 | 39,600 | 21.393 | 3,558,860 | 29,100 | 0.0125 |
| 10 | fast_reconcile_2 | 24,912,020 | 7.0 | 50,400 | 37.418 | 3,558,860 | 29,400 | 0.0219 |
| 10 | fast_reconcile_4 | 46,265,180 | 13.0 | 72,000 | 69.470 | 3,558,860 | 30,000 | 0.0408 |
| 100 | current_pilot | 11,352,763,400 | 319.0 | 11,448,000 | 17040.593 | 35,588,600 | 291,000 | 1.0000 |
| 100 | fast_reconcile_1 | 142,354,400 | 4.0 | 396,000 | 213.928 | 35,588,600 | 291,000 | 0.0125 |
| 100 | fast_reconcile_2 | 249,120,200 | 7.0 | 504,000 | 374.184 | 35,588,600 | 294,000 | 0.0219 |
| 100 | fast_reconcile_4 | 462,651,800 | 13.0 | 720,000 | 694.698 | 35,588,600 | 300,000 | 0.0408 |

CORE novo é igual entre modelos apenas sob hipótese sem restatements. RAW writes = páginas; BQ transações/jobs não equivalem a um upsert por Fact. Envelope1000bytes/página incluso. Não inclui ingestão de Orders/Customers, open-order revisits, registry, falhas ou páginas extras do servidor; API mínima estimada por arredondamento por consulta.

## Compute e scans — sensibilidade

Suposições:30s/execução,1vCPU,1GiB; scans1000bytes por observação/linha histórica,8jobs por página. Deep corrente145/dia (96sync+48quality+1reconcile); proposta deep1/dia + escopo recente1dia para48quality/dia. Queries históricas repetem leituras e clustering não garante bytes proporcionais: valores são proxies, calibrar pelo ledger. Analytics configurável presume scan histórico por publicação.

| Lojas | Modelo | Jobs BQ estimados | BQ TB/mês | Execuções totais | vCPU-s | GiB-s |
|---:|---|---:|---:|---:|---:|---:|
| 1 | current_pilot | 920,190 | 1.662 | 4,350 | 130,500 | 130,500 |
| 1 | fast_reconcile_1 | 31,710 | 0.029 | 4,380 | 131,400 | 131,400 |
| 1 | fast_reconcile_2 | 40,350 | 0.030 | 4,410 | 132,300 | 132,300 |
| 1 | fast_reconcile_4 | 57,630 | 0.032 | 4,470 | 134,100 | 134,100 |
| 10 | current_pilot | 9,201,900 | 16.616 | 43,500 | 1,305,000 | 1,305,000 |
| 10 | fast_reconcile_1 | 317,100 | 0.292 | 43,800 | 1,314,000 | 1,314,000 |
| 10 | fast_reconcile_2 | 403,500 | 0.303 | 44,100 | 1,323,000 | 1,323,000 |
| 10 | fast_reconcile_4 | 576,300 | 0.324 | 44,700 | 1,341,000 | 1,341,000 |
| 100 | current_pilot | 92,019,000 | 166.163 | 435,000 | 13,050,000 | 13,050,000 |
| 100 | fast_reconcile_1 | 3,171,000 | 2.918 | 438,000 | 13,140,000 | 13,140,000 |
| 100 | fast_reconcile_2 | 4,035,000 | 3.025 | 441,000 | 13,230,000 | 13,230,000 |
| 100 | fast_reconcile_4 | 5,763,000 | 3.239 | 447,000 | 13,410,000 | 13,410,000 |

## Storage retido (steady-state, GB decimais)

Retenção365dias hipotética para projeção, inclusive CORE/versions/OPS; não é política de expiração implementada. RAW365 é a configuração DEV atual. CORE/versions atuais não recebem TTL nesta mudança. Analytics e Meta zero porque frequência/inputzero, não promessa de custo zero ao habilitar. CORE efetivo deve incluir fanout touchpoints/links/identidade ao calibrar core_row_bytes. Este modelo não soma tabelas comerciais automaticamente. GB retido steady-state equivale a GB-mês de armazenamento num mês nesse nível; não confundir com ingestão GB/mês.

| Lojas | Modelo | RAW | CORE Facts efetivo | Versions | OPS | Analytics | Meta futuro | Total TB |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | current_pilot | 2073.272 | 4.330 | 4.330 | 0.106 | 0.000 | 0.000 | 2.082 |
| 1 | fast_reconcile_1 | 26.028 | 4.330 | 4.330 | 0.107 | 0.000 | 0.000 | 0.035 |
| 10 | current_pilot | 20732.722 | 43.299 | 43.299 | 1.058 | 0.000 | 0.000 | 20.820 |
| 10 | fast_reconcile_1 | 260.279 | 43.299 | 43.299 | 1.066 | 0.000 | 0.000 | 0.348 |
| 100 | current_pilot | 207327.216 | 432.995 | 432.995 | 10.585 | 0.000 | 0.000 | 208.204 |
| 100 | fast_reconcile_1 | 2602.786 | 432.995 | 432.995 | 10.658 | 0.000 | 0.000 | 3.479 |
| 200 | current_pilot | 414654.432 | 865.989 | 865.989 | 21.170 | 0.000 | 0.000 | 416.408 |
| 200 | fast_reconcile_1 | 5205.572 | 865.989 | 865.989 | 21.316 | 0.000 | 0.000 | 6.959 |

## Uso e fórmulas

```bash
python -m scripts.estimate_scale_cost --preset mx-fashion --compare
python -m scripts.estimate_scale_cost --preset 10-stores --compare
python -m scripts.estimate_scale_cost --preset 100-stores --compare
python -m scripts.estimate_scale_cost --stores 200 --facts-payload-bytes 3000 \
  --reconcile-frequency-per-day 2 --raw-retention-days 365 --core-retention 730 \
  --quality-frequency 48 --deep-quality-frequency 1 --analytics-frequency 6
```

Todos os parâmetros de Scenario têm opção CLI, inclusive payload/envelope, tamanho
CORE efetivo, version_multiplier, history_days, seconds/CPU/GiB e scans/jobs por página.
Preset só define stores; demais valores são hipóteses visíveis no JSON de saída.
`--compare` varia cadência de reconcile, não constitui escolha operacional.

Fast novo observa F; reconcile observa F×L/24×r. Atual adiciona F×L/Δ e
F×history_days. Páginas = soma dos ceil por consulta, com pelo menos uma resposta
para intervalo vazio; reconcile em sub-janelas de até um dia, como CLI atual.
Retained RAW = ingestão mensal×retention/30. CORE rows = F×core_retention/30;
versions = CORE bytes×version_multiplier (1 default = primeira versão por Fact).
Storage não modela compressão, preços, free tier, BigQuery long-term storage ou
multirregional. OPS proxy bytes/run não inclui ledger de query grande: calibrar.
Duração constante ignora proporcionalidade entre lotes grandes/pequenos e custo de
inicialização: comparar como sensibilidade, não dimensionamento garantido. Custos
do dispatcher/queue, API fonte e comercial não estão incluídos. Preços devem ser
aplicados externamente a estas quantidades, segundo contrato/região vigentes.
