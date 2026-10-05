import "server-only";
import { getVercelOidcToken } from "@vercel/oidc";
import {
  ExternalAccountClient,
  GoogleAuth,
  Impersonated,
} from "google-auth-library";

/** Configuration is server-owned. Neither token nor credential config is accepted from a request. */
export function federationConfig(env: NodeJS.ProcessEnv = process.env) {
  const project = env.GCP_PROJECT_ID ?? "";
  const number = env.GCP_PROJECT_NUMBER ?? "";
  const pool = env.GCP_WORKLOAD_IDENTITY_POOL_ID ?? "";
  const provider = env.GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID ?? "";
  const account = env.GCP_SERVICE_ACCOUNT_EMAIL ?? "";
  if (
    !/^[a-z][a-z0-9-]{5,62}$/.test(project) ||
    !/^\d{6,20}$/.test(number) ||
    !/^[a-z][a-z0-9-]{3,31}$/.test(pool) ||
    !/^[a-z][a-z0-9-]{3,31}$/.test(provider) ||
    account !== `up-product-vercel-dev@${project}.iam.gserviceaccount.com` ||
    !["production", "preview"].includes(env.VERCEL_ENV ?? "")
  )
    throw new Error("vercel_federation_configuration_required");
  return {
    audience: `//iam.googleapis.com/projects/${number}/locations/global/workloadIdentityPools/${pool}/providers/${provider}`,
    account,
  };
}

async function federatedIdToken(audience: string) {
  const config = federationConfig();
  // STS verifies the Vercel signature and the provider's exact team/project/environment condition.
  const source = ExternalAccountClient.fromJSON({
    type: "external_account",
    audience: config.audience,
    subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
    token_url: "https://sts.googleapis.com/v1/token",
    subject_token_supplier: { getSubjectToken: () => getVercelOidcToken() },
  });
  if (!source) throw new Error("vercel_federation_configuration_required");
  // Direct generateIdToken avoids granting the Vercel service account data-layer permissions.
  const identity = new Impersonated({
    sourceClient: source,
    targetPrincipal: config.account,
    targetScopes: [],
    delegates: [],
    lifetime: 600,
  });
  return identity.fetchIdToken(audience, { includeEmail: true });
}

export async function serviceAuthorization(
  audience: string,
  dependencies: {
    env?: NodeJS.ProcessEnv;
    federated?: (audience: string) => Promise<string>;
    cloudRun?: (audience: string) => Promise<string>;
  } = {},
) {
  const env = dependencies.env ?? process.env;
  if (![env.UP_READ_SERVICE_URL, env.UP_ADMIN_SERVICE_URL].includes(audience))
    throw new Error("private_service_audience_forbidden");
  if (env.VERCEL === "1") {
    federationConfig(env); // Fail closed before exchange; never fall back to ADC on Vercel.
    const token = await (dependencies.federated ?? federatedIdToken)(audience);
    if (!token) throw new Error("private_service_identity_unavailable");
    return `Bearer ${token}`;
  }
  if (env.K_SERVICE !== "up-web") throw new Error("serving_identity_required");
  const token = await (
    dependencies.cloudRun ??
    (async (target) => {
      const client = await new GoogleAuth().getIdTokenClient(target);
      return client.idTokenProvider.fetchIdToken(target);
    })
  )(audience);
  if (!token) throw new Error("private_service_identity_unavailable");
  return `Bearer ${token}`;
}
