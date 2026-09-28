# DEV: Artifact Registry e imagem dos Jobs

Preparação local somente. Os comandos operacionais deste documento são para execução futura, após autorização. Não executar apply, push ou build remoto nesta etapa. Não há conexão UP Zero/Meta nem API Key no build.

## Ordem e estados Terraform

Há dois roots independentes. `infra/terraform/registry` gerencia somente a API Artifact Registry, o repositório Docker e seu IAM. `infra/terraform` gerencia a Data Foundation. Cada root precisa de estado próprio, com armazenamento protegido; nunca reutilizar a mesma chave/prefixo de backend. A Foundation agora declara backend GCS DEV, dependente do bootstrap separado descrito em [TERRAFORM_BACKEND_DEV.md](TERRAFORM_BACKEND_DEV.md); não inicializar/migrar antes de o bucket existir. O registry mantém seu estado separado; não foi migrado.

Isso resolve a dependência inicial: registry → build/push → digest → plano completo dos Jobs. Não usar `-target`, digest fictício ou enfraquecer a validação da imagem. O registry não lê `infra/terraform/environments/dev.tfvars`; possui seu próprio arquivo. O placeholder original, PILOT_STORE e schedules pausados permanecem intactos.

Configuração do registry DEV: projeto `up-data-intelligence-dev` (número `876521886531`), região `southamerica-east1`, repository ID `up-data-intelligence`, formato `DOCKER`, tags imutáveis e `prevent_destroy=true`. Sem política automática de limpeza por enquanto. Imagem: `southamerica-east1-docker.pkg.dev/up-data-intelligence-dev/up-data-intelligence/foundation`.

## Identidades e IAM

Antes do primeiro plano, preencher no arquivo DEV sem secrets `infra/terraform/registry/environments/dev.tfvars` as identidades existentes e aprovadas:

```hcl
publisher_members = ["user:EMAIL_REAL_DO_OPERADOR_BUILD"]
deployer_members  = ["user:EMAIL_REAL_DO_OPERADOR_TERRAFORM"]
```

São exemplos de formato, não identidades criadas. Para CI, usar `serviceAccount:EMAIL_REAL` com federação/impersonação. Não criar chave JSON. As listas inicialmente vazias evitam inventar identidades; sem preenchê-las, nenhum binding adicional será criado.

- Publisher: `roles/artifactregistry.writer`, apenas no repositório. Não recebe admin, deploy, acesso a dados ou secrets.
- Deployer: `roles/artifactregistry.reader`, apenas no repositório. Se for o mesmo publisher, Writer já inclui leitura e não é necessário duplicar o binding.
- Pull Cloud Run no mesmo projeto: usa o service agent `service-876521886531@serverless-robot-prod.iam.gserviceaccount.com`, com o papel gerenciado `roles/run.serviceAgent` estabelecido pelo GCP ao ativar Run. A conta de runtime `up-foundation-dev` não faz o pull e não recebe Writer/Reader adicional. Conferir o papel do service agent antes do deployment; se a imagem migrar de projeto, revisar o binding Reader para esse agente.
- Executor Terraform: precisa previamente de permissões para habilitar a API, criar repositório e administrar o IAM desse repositório. Esses poderes de provisionamento não são concedidos ao publisher por este código. A identidade não pode elevar a si mesma se ainda não possui esses direitos.

Referências: [IAM Artifact Registry](https://docs.cloud.google.com/artifact-registry/docs/access-control), [integração Cloud Run](https://docs.cloud.google.com/artifact-registry/docs/integrate-cloud-run).

## Provisionar somente o registry — etapa futura

Executar a partir da raiz do repositório. Os dois arquivos DEV sem secrets são versionados. Preencher as identidades aprovadas no arquivo do registry antes de planejar; não adicionar credenciais. O example continua disponível para novos ambientes.

```bash
# Apenas em checkout sem o arquivo real:
# cp infra/terraform/registry/environments/dev.tfvars.example infra/terraform/registry/environments/dev.tfvars

gcloud auth application-default login
terraform -chdir=infra/terraform/registry init
terraform -chdir=infra/terraform/registry fmt -check -recursive
terraform -chdir=infra/terraform/registry validate
terraform -chdir=infra/terraform/registry plan \
  -var-file=environments/dev.tfvars -out=registry-dev.tfplan
terraform -chdir=infra/terraform/registry show registry-dev.tfplan
```

Revisar: somente API Artifact Registry, um repositório e os bindings aprovados; nenhum Job/dataset/secret. Após autorização específica para provisionar, o comando será `terraform -chdir=infra/terraform/registry apply registry-dev.tfplan`. **Não executado nesta preparação.** O projeto/billing e as credenciais/permissões do executor são pré-requisitos externos; não foram verificados na nuvem.

## Docker: revisão e contrato

Python 3.13 é compatível com `requires-python >=3.13,<3.14`. Base slim Debian Bookworm; dependências runtime transitivas fixadas e verificadas com `--require-hashes`. `--only-binary=:all:` evita compilar dependências/downloads de build fora do lock: se não houver wheel Linux amd64, o build falha explicitamente. Para release, fixar também o digest da base usando `PYTHON_BASE`.

O entrypoint `python -m src.jobs.cli` recebe os argumentos `--live --confirm-store PILOT_STORE --mode sync|reconcile|quality --resource all` já definidos no Terraform. A configuração vem de `UP_CONFIG_JSON`, portanto os Jobs não precisam de config.example.json/fixtures. Código, SQL e contrato OpenAPI estão em `/app`; usuário UID/GID 10001, sem escrita no código e sem porta HTTP. A CLI retorna exit status de sucesso/falha. O CMD padrão é `--help`, sem acessar APIs; os argumentos dos Jobs o substituem.

`.dockerignore` permite apenas os arquivos necessários. `.gcloudignore` aplica allowlist também ao upload Cloud Build (que não é controlado pelo Docker). Credenciais, `.env`, `.git`, estados/tfvars, ambientes virtuais, dados locais e testes não são enviados. Secrets não são argumentos de build nem camadas da imagem.

Referência: [contrato Cloud Run](https://docs.cloud.google.com/run/docs/container-contract). O build real/smoke test Linux ainda precisa ser realizado; verificações Python locais não comprovam o funcionamento de wheels no container.

## Autenticar, construir, testar e publicar — etapa futura

Requer Docker com buildx, gcloud e identidade incluída em `publisher_members`. Os comandos não executam deployment. Usar Bash a partir da raiz do repositório:

```bash
set -euo pipefail
PROJECT_ID=up-data-intelligence-dev
REGION=southamerica-east1
IMAGE_PATH="$REGION-docker.pkg.dev/$PROJECT_ID/up-data-intelligence/foundation"
VERSION="dev-$(git rev-parse --short=12 HEAD)-$(date -u +%Y%m%dT%H%M%SZ)"

gcloud auth login
gcloud auth configure-docker southamerica-east1-docker.pkg.dev

# Consultar e fixar o digest real da base antes do build; nenhuma credencial GCP na imagem.
BASE_TAG=python:3.13-slim-bookworm
BASE_DIGEST=$(docker buildx imagetools inspect "$BASE_TAG" | awk '$1 == "Digest:" {print $2; exit}')
[[ "$BASE_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
PYTHON_BASE="$BASE_TAG@$BASE_DIGEST"

docker buildx build --platform linux/amd64 --load \
  --build-arg "PYTHON_BASE=$PYTHON_BASE" \
  --tag "up-data-intelligence:$VERSION" .
docker run --rm --network none "up-data-intelligence:$VERSION" --help
# Confere imports, timezone e leitura do contrato sem rede nem dados reais.
docker run --rm --network none --entrypoint python "up-data-intelligence:$VERSION" \
  -c 'import json; from pathlib import Path; from zoneinfo import ZoneInfo; import src.jobs.cli; ZoneInfo("America/Sao_Paulo"); json.loads(Path("docs/upzero-openapi.json").read_text()); print("runtime smoke OK")'

docker tag "up-data-intelligence:$VERSION" "$IMAGE_PATH:$VERSION"
docker push "$IMAGE_PATH:$VERSION"
DIGEST=$(gcloud artifacts docker images describe "$IMAGE_PATH:$VERSION" \
  --project="$PROJECT_ID" --format='value(image_summary.digest)')
[[ "$DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
export IMAGE_REF="$IMAGE_PATH@$DIGEST"
printf '%s\n' "$IMAGE_REF"
```

Não reutilizar tags (imutáveis). Registrar commit, alterações locais se houver, VERSION, digest da base e digest final no registro de release. Preferir checkout revisado e commitado. Usar linux/amd64 inclusive em Mac ARM. Login gcloud usado pelo Docker e ADC usado pelo Terraform são configurações distintas. [Autenticação Docker oficial](https://docs.cloud.google.com/artifact-registry/docs/docker/authentication).

## Atualizar o placeholder — somente após push confirmado

Na mesma sessão Bash, com `IMAGE_REF` exportada pelo passo anterior:

```bash
python3 - <<'PY'
import os
import re
from pathlib import Path

ref = os.environ['IMAGE_REF']
expected = r'southamerica-east1-docker\.pkg\.dev/up-data-intelligence-dev/up-data-intelligence/foundation@sha256:[a-f0-9]{64}'
if not re.fullmatch(expected, ref):
    raise SystemExit('Referência/digest DEV inválido')
path = Path('infra/terraform/environments/dev.tfvars')
text = path.read_text()
placeholder = 'REPLACE_WITH_IMAGE@sha256:REPLACE_WITH_DIGEST'
if text.count(placeholder) != 1:
    raise SystemExit('Placeholder ausente/ambíguo; revisar manualmente')
path.write_text(text.replace(placeholder, ref))
PY
terraform -chdir=infra/terraform fmt environments/dev.tfvars
terraform -chdir=infra/terraform validate
```

Isso não executa apply/deploy. O módulo principal gerencia o container de Secret Manager com réplica em var.region e proteção contra destruição; o IAM depende desse recurso. Não gerencia versões nem valores. Antes do apply, conferir permissões, estado e eventual container preexistente a importar; a versão real será adicionada posteriormente fora do Terraform, antes da ingestão. Manter scheduler pausado. Não configurar API Key nesta etapa.

## Alternativa: Google Cloud Build (opcional)

Útil se Docker Linux não estiver disponível localmente. `cloudbuild.yaml` apenas constrói, testa `--help` sem rede e publica a imagem; não faz deploy. Não foi submetido.

Antes de usar, uma etapa separada e autorizada deverá habilitar Cloud Build, escolher/criar uma service account dedicada, conceder Writer somente neste repositório via `publisher_members`, `roles/logging.logWriter` no projeto e leitura (`roles/storage.objectViewer`) apenas no bucket/prefixo de staging usado. O bucket de staging deve existir, com retenção/acesso definidos; não usar o bucket de leases. A identidade que submete precisa de `cloudbuild.builds.create/get`, upload no staging e `iam.serviceAccounts.actAs` na conta escolhida. Não assumir o default SA ou conceder Editor/Owner. Esses recursos/permissões opcionais não são provisionados pelo root registry.

Com staging e identidade aprovados, substituir as duas referências abaixo e reutilizar VERSION/PYTHON_BASE definidos acima (o digest da base também pode ser obtido de um ambiente com Docker):

```bash
BUILD_SA='EMAIL_REAL_DA_SERVICE_ACCOUNT_BUILD'
SOURCE_STAGING='gs://BUCKET_STAGING_APROVADO/source'
# Revisar exatamente o conjunto de arquivos que será enviado:
gcloud meta list-files-for-upload

gcloud builds submit . --project=up-data-intelligence-dev \
  --region=southamerica-east1 --config=cloudbuild.yaml \
  --service-account="projects/up-data-intelligence-dev/serviceAccounts/$BUILD_SA" \
  --gcs-source-staging-dir="$SOURCE_STAGING" \
  --substitutions="_VERSION=$VERSION,_PYTHON_BASE=$PYTHON_BASE"
```

Após sucesso, obter DIGEST e atualizar o tfvars usando os mesmos comandos da rota Docker. [Conta customizada Cloud Build](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts).

## Verificação desta preparação

Consultar o relatório entregue junto à alteração para os resultados locais. Nenhum plan/apply/push/build remoto foi necessário. Pendências operacionais: identidades publisher/deployer, autenticação/billing/permissões, política de estado Terraform, provisionamento autorizado do registry e primeiro build Linux com digest real.
