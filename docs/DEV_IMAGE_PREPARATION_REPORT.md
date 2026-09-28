# Preparação Artifact Registry / Docker DEV — resultado

Alterações locais, sem provisionamento ou publicação.

## Arquivos desta etapa

- `Dockerfile`
- `.dockerignore`
- `.gcloudignore`
- `cloudbuild.yaml`
- `README.md`
- `docs/DEPLOYMENT_DEV.md`
- `infra/terraform/registry/versions.tf`
- `infra/terraform/registry/.terraform.lock.hcl`
- `infra/terraform/registry/variables.tf`
- `infra/terraform/registry/main.tf`
- `infra/terraform/registry/outputs.tf`
- `infra/terraform/registry/environments/dev.tfvars.example`
- `infra/terraform/registry/environments/dev.tfvars`

## Verificação

- 90 testes passaram (rede bloqueada pela suíte).
- Ruff lint passou; Ruff format: 41 arquivos conformes.
- Mypy: 33 arquivos de source, sem erros.
- Terraform fmt recursivo passou.
- Terraform validate passou para Data Foundation e registry independente.
- Init do registry: backend=false, provider Google 8.4.0 reutilizado do cache local com lockfile; sem consulta GCP.
- CLI --help executou com sucesso no Python local.
- Lista local `gcloud meta list-files-for-upload` contém somente Dockerfile, cloudbuild.yaml, .dockerignore, requirements.lock, source Python, SQL e OpenAPI. Nenhum upload realizado.
- OpenAPI SHA256 preservado: 47e863d1942ba4074faaace1398e97fb25f3a1c25e3ab65bed01cafe33b21043.
- dev.tfvars da Foundation e seu example não foram alterados; imagem placeholder/PILOT_STORE preservados.
- Docker não disponível no PATH: build, resolução de base digest, smoke test em Linux e push não executados. Compatibilidade do entrypoint/argumentos revisada no código; execução real no container não confirmada.
- Nenhum plan, apply, deployment, build remoto, API Key ou chamada UP Zero/Meta executado.

## Decisões e pendências

Root registry separado para provisioná-lo antes da imagem, sem contornar a validação de digest dos Jobs. Estado separado obrigatório. IAM Writer/Reader limitado ao repositório, sem admin. As listas de membros estão vazias: definir emails aprovados antes de planejar. O pull no mesmo projeto usa o service agent Cloud Run gerenciado pelo GCP, não o runtime da aplicação.

Antes do primeiro provisionamento: confirmar projeto/billing, autenticação e permissões do executor, definir identidades publisher/deployer, armazenamento protegido de estado, revisar e autorizar o plano registry. Após provisionamento: build Linux amd64 com digest de base, smoke test, push com tag imutável e digest final. Cloud Build é alternativa documentada, dependente de conta, staging e IAM adicionais ainda não provisionados.

Comandos completos no [guia DEV](DEPLOYMENT_DEV.md). Não executar o root Foundation antes da imagem real e dos demais pré-requisitos. Schedules continuam pausados.
