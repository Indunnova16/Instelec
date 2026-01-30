#!/bin/bash
# =============================================================================
# Low Cost Deployment Script for Instelec (TransMaint)
# Project: appsindunnova
# Database: Consolidated (existing PostgreSQL instance)
# =============================================================================

set -e

# Configuration
PROJECT_ID="appsindunnova"
REGION="us-central1"
SERVICE_NAME="instelec-api"
REPO_NAME="instelec"
IMAGE_NAME="instelec-api"
DB_INSTANCE="consolidated"
BUCKET_NAME="instelec-media"

echo "=========================================="
echo "Instelec - Low Cost Cloud Run Deployment"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Database: $DB_INSTANCE (existing)"
echo ""

# Set project
gcloud config set project "$PROJECT_ID"

# Step 1: Enable required APIs
echo "[1/8] Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    storage.googleapis.com \
    cloudbuild.googleapis.com

# Step 2: Create Artifact Registry repository (if not exists)
echo ""
echo "[2/8] Creating Artifact Registry repository..."
gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Instelec Docker images" \
    2>/dev/null || echo "  Repository already exists."

# Step 3: Create Cloud Storage bucket (if not exists)
echo ""
echo "[3/8] Creating Cloud Storage bucket..."
gsutil mb -p "$PROJECT_ID" -l "$REGION" -c STANDARD "gs://$BUCKET_NAME" 2>/dev/null || echo "  Bucket already exists."

# Step 4: Create service account
echo ""
echo "[4/8] Creating service account..."
gcloud iam service-accounts create instelec-api \
    --display-name="Instelec API Service Account" \
    2>/dev/null || echo "  Service account already exists."

# Grant permissions
echo "  Granting permissions..."
for ROLE in "roles/cloudsql.client" "roles/secretmanager.secretAccessor" "roles/storage.objectAdmin"; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:instelec-api@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="$ROLE" \
        --quiet 2>/dev/null
done

# Step 5: Create database in Consolidated instance
echo ""
echo "[5/8] Creating database in Consolidated instance..."
gcloud sql databases create instelec \
    --instance="$DB_INSTANCE" \
    2>/dev/null || echo "  Database already exists."

# Create database user
echo "  Creating database user..."
DB_PASSWORD=$(openssl rand -base64 24)
gcloud sql users create instelec \
    --instance="$DB_INSTANCE" \
    --password="$DB_PASSWORD" \
    2>/dev/null || echo "  User already exists (using existing password)."

# Step 6: Create secrets
echo ""
echo "[6/8] Creating secrets in Secret Manager..."

# Generate Django secret key
DJANGO_SECRET=$(openssl rand -base64 50 | tr -dc 'a-zA-Z0-9' | head -c 50)

# Create DATABASE_URL secret
DATABASE_URL="postgres://instelec:${DB_PASSWORD}@/instelec?host=/cloudsql/${PROJECT_ID}:${REGION}:${DB_INSTANCE}"
echo -n "$DATABASE_URL" | gcloud secrets create instelec-database-url \
    --data-file=- \
    2>/dev/null || echo "  Secret instelec-database-url already exists."

# Create SECRET_KEY secret
echo -n "$DJANGO_SECRET" | gcloud secrets create instelec-secret-key \
    --data-file=- \
    2>/dev/null || echo "  Secret instelec-secret-key already exists."

# Step 7: Build and push Docker image
echo ""
echo "[7/8] Building and pushing Docker image..."
cd "$(dirname "$0")/../.."

# Configure Docker for Artifact Registry
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# Build image
docker build \
    -f infrastructure/docker/Dockerfile \
    -t "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:latest" \
    .

# Push image
docker push "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:latest"

# Step 8: Deploy to Cloud Run
echo ""
echo "[8/8] Deploying to Cloud Run..."
gcloud run services replace infrastructure/cloudrun/service-low-cost.yaml \
    --region="$REGION"

# Make service public (optional - remove if auth required)
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
    --region="$REGION" \
    --member="allUsers" \
    --role="roles/run.invoker"

# Get service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format="value(status.url)")

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Service URL: $SERVICE_URL"
echo ""
echo "Next steps:"
echo "1. Run migrations:"
echo "   gcloud run jobs execute instelec-migrate --region=$REGION"
echo ""
echo "2. Create superuser (if needed):"
echo "   gcloud run jobs create instelec-createsuperuser \\"
echo "     --image=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME:latest \\"
echo "     --region=$REGION \\"
echo "     --set-cloudsql-instances=$PROJECT_ID:$REGION:$DB_INSTANCE \\"
echo "     --command=python,manage.py,createsuperuser,--noinput \\"
echo "     --set-env-vars=DJANGO_SUPERUSER_USERNAME=admin,DJANGO_SUPERUSER_EMAIL=admin@instelec.com,DJANGO_SUPERUSER_PASSWORD=changeme123"
echo ""
echo "Cost Optimizations Applied:"
echo "  - Scale to zero (no idle costs)"
echo "  - CPU throttling enabled"
echo "  - 512MB RAM / 1 CPU (minimum)"
echo "  - Using existing Consolidated database"
echo "  - No Redis (using Django's local memory cache)"
echo ""
