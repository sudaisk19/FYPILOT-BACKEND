#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# FYPilot Backend - Rollback Script
# Usage: ./rollback.sh [commit-sha]
# Without args: rolls back to previous image
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

cd /opt/fypilot-backend

REGISTRY="ghcr.io"
# Update this with your actual GitHub owner/org
IMAGE_NAME="${GITHUB_OWNER:-your-github-username}/fypilot-backend"

if [ -n "${1:-}" ]; then
    TAG="$1"
    echo "🔄 Rolling back to commit: $TAG"
    # Update docker-compose to use specific tag
    sed -i "s|image:.*fypilot-backend.*|image: ${REGISTRY}/${IMAGE_NAME}:${TAG}|g" docker-compose.yml
else
    echo "🔄 Rolling back to previous image..."
    # Get the second-to-last image
    PREVIOUS_IMAGE=$(docker images "${REGISTRY}/${IMAGE_NAME}" --format "{{.Tag}}" | sed -n '2p')
    if [ -z "$PREVIOUS_IMAGE" ]; then
        echo "❌ No previous image found to roll back to."
        exit 1
    fi
    TAG="$PREVIOUS_IMAGE"
    echo "   Using image tag: $TAG"
    sed -i "s|image:.*fypilot-backend.*|image: ${REGISTRY}/${IMAGE_NAME}:${TAG}|g" docker-compose.yml
fi

# Restart with rollback image
docker compose down --timeout 30
docker compose up -d

# Health check
echo "⏳ Checking health..."
for i in $(seq 1 20); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "✅ Rollback successful! Running on: $TAG"
        exit 0
    fi
    sleep 2
done

echo "❌ Health check failed after rollback."
docker compose logs --tail=30
exit 1
