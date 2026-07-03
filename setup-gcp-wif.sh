#!/usr/bin/env bash
# One-time, idempotent GCP setup for the optional Cloud Run fallback:
# Workload Identity Federation (keyless GitHub Actions auth), service
# accounts, roles, and an Artifact Registry docker repo.
#
# Run in Cloud Shell on the target project:
#   PROJECT=<gcp-project-id> REPO=<github-owner>/<repo> REGION=<region> \
#     bash setup-gcp-wif.sh
#
# Prints the workload_identity_provider string and service account email
# to paste into .github/workflows/deploy.yml.
set -euo pipefail

: "${PROJECT:?set PROJECT=<gcp-project-id>}"
: "${REPO:?set REPO=<github-owner>/<repo>}"
REGION="${REGION:-europe-north1}"
AR_REPO="${AR_REPO:-scrapers}"
POOL="${POOL:-github-pool}"
PROVIDER="${PROVIDER:-github-provider}"
DEPLOYER_SA="${DEPLOYER_SA:-github-deployer}"
RUNNER_SA="${RUNNER_SA:-scraper-runner}"
OWNER="${REPO%%/*}"

gcloud config set project "$PROJECT"

echo "--- Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  logging.googleapis.com

echo "--- Artifact Registry repo: $AR_REPO ($REGION)"
gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format docker --location "$REGION"

echo "--- Workload Identity pool + GitHub OIDC provider"
gcloud iam workload-identity-pools describe "$POOL" --location global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" \
    --location global --display-name "GitHub Actions"
gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --location global --workload-identity-pool "$POOL" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --location global --workload-identity-pool "$POOL" \
    --display-name "GitHub OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
    --attribute-condition "assertion.repository_owner=='$OWNER'"

echo "--- Service accounts"
for sa in "$DEPLOYER_SA" "$RUNNER_SA"; do
  gcloud iam service-accounts describe "$sa@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$sa" --display-name "$sa"
done

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')

echo "--- Binding repo $REPO to $DEPLOYER_SA (workloadIdentityUser)"
# This binding is the piece that's missing when deploys fail with
# "iam.serviceAccounts.getAccessToken denied".
gcloud iam service-accounts add-iam-policy-binding \
  "$DEPLOYER_SA@$PROJECT.iam.gserviceaccount.com" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$REPO" \
  --quiet

echo "--- Granting deployer roles"
for role in roles/artifactregistry.writer roles/run.developer roles/logging.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member "serviceAccount:$DEPLOYER_SA@$PROJECT.iam.gserviceaccount.com" \
    --role "$role" --quiet >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding \
  "$RUNNER_SA@$PROJECT.iam.gserviceaccount.com" \
  --role roles/iam.serviceAccountUser \
  --member "serviceAccount:$DEPLOYER_SA@$PROJECT.iam.gserviceaccount.com" \
  --quiet

echo
echo "Done. Paste these into .github/workflows/deploy.yml:"
echo "  workload_identity_provider: projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
echo "  service_account: $DEPLOYER_SA@$PROJECT.iam.gserviceaccount.com"
