#!/bin/bash
# =============================================================================
# GCP Infrastructure Setup Script for TransMaint
# =============================================================================

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="transmaint-api"
DB_INSTANCE_NAME="transmaint-db"
REDIS_INSTANCE_NAME="transmaint-cache"
BUCKET_NAME="transmaint-${PROJECT_ID}-media"

echo "=========================================="
echo "TransMaint - GCP Infrastructure Setup"
echo "=========================================="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "Error: gcloud CLI not found. Please install Google Cloud SDK."
    exit 1
fi

# Check if project ID is set
if [ -z "$PROJECT_ID" ]; then
    echo "Error: GCP_PROJECT_ID environment variable not set."
    echo "Usage: GCP_PROJECT_ID=your-project-id ./setup_gcp.sh"
    exit 1
fi

echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Set project
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    redis.googleapis.com \
    storage.googleapis.com \
    cloudbuild.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com \
    compute.googleapis.com

echo ""
echo "Creating Artifact Registry repository..."
gcloud artifacts repositories create transmaint \
    --repository-format=docker \
    --location="$REGION" \
    --description="TransMaint Docker images" \
    2>/dev/null || echo "Repository already exists."

echo ""
echo "Creating Cloud Storage bucket..."
gsutil mb -p "$PROJECT_ID" -l "$REGION" "gs://$BUCKET_NAME" 2>/dev/null || echo "Bucket already exists."
gsutil cors set infrastructure/gcs-cors.json "gs://$BUCKET_NAME" 2>/dev/null || true

echo ""
echo "Creating Cloud SQL instance..."
gcloud sql instances create "$DB_INSTANCE_NAME" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --storage-auto-increase \
    --backup-start-time=03:00 \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=04 \
    2>/dev/null || echo "Cloud SQL instance already exists."

# Create database
echo "Creating database..."
gcloud sql databases create transmaint \
    --instance="$DB_INSTANCE_NAME" \
    2>/dev/null || echo "Database already exists."

echo ""
echo "Creating Redis instance (Memorystore)..."
gcloud redis instances create "$REDIS_INSTANCE_NAME" \
    --size=1 \
    --region="$REGION" \
    --redis-version=redis_7_0 \
    2>/dev/null || echo "Redis instance already exists or creation in progress."

echo ""
echo "Creating VPC connector..."
gcloud compute networks vpc-access connectors create transmaint-vpc \
    --region="$REGION" \
    --range=10.8.0.0/28 \
    2>/dev/null || echo "VPC connector already exists."

echo ""
echo "Creating service accounts..."
# API service account
gcloud iam service-accounts create transmaint-api \
    --display-name="TransMaint API Service Account" \
    2>/dev/null || echo "API service account already exists."

# Worker service account
gcloud iam service-accounts create transmaint-worker \
    --display-name="TransMaint Worker Service Account" \
    2>/dev/null || echo "Worker service account already exists."

# Scheduler service account
gcloud iam service-accounts create transmaint-scheduler \
    --display-name="TransMaint Scheduler Service Account" \
    2>/dev/null || echo "Scheduler service account already exists."

# Grant permissions
echo ""
echo "Granting IAM permissions..."
for SA in transmaint-api transmaint-worker; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/cloudsql.client" \
        --quiet

    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet

    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/storage.objectAdmin" \
        --quiet
done

# Grant Cloud Run invoker to scheduler
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
    --member="serviceAccount:transmaint-scheduler@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --region="$REGION" \
    2>/dev/null || echo "Cloud Run service not yet deployed."

echo ""
echo "Creating secrets..."
# Note: These need actual values - prompting user
echo "Please create the following secrets in Secret Manager:"
echo "  - DATABASE_URL"
echo "  - DJANGO_SECRET_KEY"
echo "  - REDIS_URL"
echo "  - SENTRY_DSN (optional)"
echo ""
echo "Use: gcloud secrets create SECRET_NAME --data-file=/path/to/secret"

echo ""
echo "=========================================="
echo "GCP Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Create secrets in Secret Manager"
echo "2. Build and push Docker images"
echo "3. Deploy to Cloud Run"
echo ""
echo "To deploy:"
echo "  gcloud builds submit --config=infrastructure/cloudbuild/cloudbuild.yaml"
echo ""
