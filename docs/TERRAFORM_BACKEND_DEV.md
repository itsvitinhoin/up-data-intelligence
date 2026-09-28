# Backend Terraform DEV — bootstrap e migração

Preparação somente: nenhum apply, bucket criado ou state migrado. Terraform 1.16.x e provider Google 8.4.0.

## Arquitetura e arquivos

- `infra/terraform/bootstrap/`: root independente com versions.tf, lockfile, variables.tf, main.tf, outputs.tf e environments/dev.tfvars (+ example). Cria apenas bucket/IAM de state. State local próprio `infra/terraform/bootstrap/terraform.tfstate`, ignorado pelo Git; preservar em armazenamento administrativo seguro, com backup e acesso restrito. Nunca usar o state da Foundation para esse root. A localização persistente e o responsável pelo state do bootstrap devem ser definidos antes do apply. Não executar em pasta temporária de Cloud Shell nem descartar seu disco sem backup.
- `infra/terraform/backend.tf`: backend GCS exclusivo DEV, bucket `up-data-intelligence-dev-876521886531-tfstate`, prefixo `foundation/dev`. Workspace `default` resulta em `foundation/dev/default.tfstate`; backend GCS gerencia locking. Nenhuma senha/token na configuração.
- `infra/terraform/registry/`: root/state independente existente, não migrado nesta etapa. Não misturar seu state com bootstrap/Foundation.
- `.gitignore`: inclui a configuração não secreta DEV do bootstrap; continua excluindo states, planos, credenciais, caches e `.terraform/`.

O root principal não chama bootstrap como módulo e não declara seu bucket. `terraform validate` não testa existência/acesso ao backend. Backend configurado ainda não está inicializado. Não executar principal com fallback local, `-lock=false`, `-target` ou plano antigo. Outros ambientes precisam de bucket/prefixo próprios: passar prod.tfvars não muda o backend DEV.

## Bucket e retenção

Projeto `up-data-intelligence-dev` (876521886531), localização `southamerica-east1`, classe STANDARD. Uniform bucket-level access, public access prevention enforced, labels application=up-data-intelligence, environment=dev, purpose=terraform-state. Sem ACL pública ou grant allUsers/allAuthenticatedUsers.

Versioning habilitado; soft delete de 7 dias; force_destroy=false; lifecycle.prevent_destroy=true. Esta última proteção vale enquanto o recurso permanece na configuração e não impede ações externas de administradores. Nenhum lock de retenção WORM: poderia impedir remoção do lock operacional do backend.

Lifecycle de exclusão somente para versões ARCHIVED, não atuais há 365 dias **e** com pelo menos 20 versões mais novas (condições cumulativas). Nenhuma exclusão do objeto atual por idade. Há custo de versões/soft delete e a retenção de históricos não é ilimitada. A política não equivale a backup independente nem protege contra todos os administradores do projeto. Sem CMEK nesta fase; criptografia padrão gerenciada pelo Google, sem criar nova dependência KMS.

## IAM e pré-requisitos

`state_members` aceita identidades user:email ou serviceAccount:email e rejeita acesso público. Concede `roles/storage.objectAdmin` somente no bucket de state, permitindo ler/gravar state e criar/remover locks. Não concede administração do bucket, Owner ou Editor. Runtime Cloud Run, Scheduler e publisher de imagens não recebem acesso.

A lista está vazia, portanto o plano atual não cria binding. Antes do apply, preencher com a identidade real que executará Terraform (e identidades de recuperação aprovadas, se necessárias). Não inferir identidade pelo usuário git. Exemplo de formato, substituir pelo email aprovado:

```hcl
state_members = ["user:EMAIL_REAL_DO_OPERADOR"]
```

O operador do bootstrap precisa previamente de `storage.buckets.create/get/update` e, para configurar IAM, `storage.buckets.getIamPolicy/setIamPolicy`, no escopo adequado; o teste dessas permissões não é garantido pelo plan. Acesso a objetos para migração requer Object Admin conforme acima. A API Storage precisa estar habilitada. Este root não gerencia a API para evitar sobreposição com o recurso já declarado na Foundation. Permissões herdadas do projeto continuam aplicáveis e precisam de revisão. Credenciais via ADC/identidade do ambiente; nenhuma chave JSON no repositório.

## Cloud Shell — preparar e revisar, sem apply

Usar checkout atualizado contendo estas mudanças (ainda não publicadas neste pedido), em diretório persistente. Os comandos abaixo partem da raiz desse checkout. Se apenas clonar o GitHub atual, estas alterações podem ainda não estar disponíveis. Não imprimir state nem credenciais.

```bash
set -euo pipefail
umask 077
terraform version
# Se ADC não estiver disponível no ambiente autorizado:
# gcloud auth application-default login

gcloud config set project up-data-intelligence-dev
# Preencher state_members antes de gerar o plano definitivo:
cloudshell edit infra/terraform/bootstrap/environments/dev.tfvars
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap fmt -check
terraform -chdir=infra/terraform/bootstrap validate
terraform -chdir=infra/terraform/bootstrap plan \
  -var-file=environments/dev.tfvars -out=bootstrap-dev.tfplan
terraform -chdir=infra/terraform/bootstrap show bootstrap-dev.tfplan
```

Conferir somente o bucket correto e um binding por identidade aprovada, sem outros recursos. **Parar para revisão e autorização.** O comando de provisionamento futuro será `terraform -chdir=infra/terraform/bootstrap apply bootstrap-dev.tfplan`; não foi executado. Depois dele, fazer backup protegido do state do bootstrap. Nunca enviar esse state ao Git ou copiá-lo para o diretório principal.

## Foundation: init -migrate-state, somente depois do bucket existir

1. Suspender execuções concorrentes de Terraform. Confirmar bucket e permissões/IAM propagadas. Verificar que prefixo/workspace destino são os corretos e não contêm state de outra execução; não sobrescrever state remoto existente. Confirmar existência e origem de eventual state local da Foundation. Se ele estiver em outro computador, transferir de forma segura para o root correto antes de migrar; nunca substituir por state vazio.
2. Usar o mesmo checkout/diretório onde está o state local original, preservando os metadados `.terraform`. Guardar backup seguro; arquivos de state podem conter dados sensíveis mesmo sem API Key neste projeto. O exemplo abaixo cria cópia local com permissões restritas, que deve ser levada ao armazenamento de backup aprovado.
3. Não usar `-force-copy`, `-reconfigure` ou resposta automática para substituir a revisão do destino de migração.

```bash
# Da raiz do checkout, após provisionamento autorizado do bucket:
umask 077
mkdir -p .local/state-backups
if [ -f infra/terraform/terraform.tfstate ]; then
  cp -p infra/terraform/terraform.tfstate \
    ".local/state-backups/foundation-$(date -u +%Y%m%dT%H%M%SZ).tfstate"
fi
terraform -chdir=infra/terraform init -migrate-state
# Ler os prompts e confirmar a cópia somente para o backend DEV esperado.
terraform -chdir=infra/terraform workspace show
terraform -chdir=infra/terraform state list
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan \
  -var-file=environments/dev.tfvars -out=dev-remote.tfplan
```

Usar workspace default para o caminho documentado. Se houver múltiplos workspaces, inventariar todos antes de confirmar migração. Se nenhum apply/import prévio gerou state local, não há conteúdo a migrar: init configura GCS e pode não pedir cópia; state list vazio é esperado, mas só depois de confirmar que não existe state autoritativo em outro local. Não usar planos binários antigos gerados com backend local. Regerar/revisar o plano principal após init; **não aplicar** sem nova autorização. Um objeto remoto pode ainda não existir até a primeira escrita de state quando não há estado prévio.

Backup/restauração de gerações deve ser feito apenas sem operação Terraform concorrente. Não restaurar state antigo arbitrariamente: comparar lineage/serial e recursos reais, salvar geração atual e obter revisão operacional. Não remover lock sem confirmar que o processo proprietário terminou.

## Resultado desta preparação

- fmt passou; validate bootstrap e principal passaram.
- Init local do bootstrap com backend=false, usando provider instalado; backend GCS principal não inicializado.
- Plan somente bootstrap: 1 add / 0 change / 0 destroy; zero bindings porque state_members está vazio.
- Warnings Terraform: nenhum.
- Bucket real não criado; state não migrado; nenhum apply ou Job executado; sem UP Zero/Meta.
- Pendências: identidades, política/backup do state bootstrap, permissões/API/billing e disponibilidade do nome global do bucket. Plan não comprova ausência de bucket/recurso já existente fora do state; se existir, avaliar import no bootstrap antes de aplicar.

Fontes: [backend GCS e locking](https://developer.hashicorp.com/terraform/language/backend/gcs), [lifecycle de objetos](https://docs.cloud.google.com/storage/docs/lifecycle).
