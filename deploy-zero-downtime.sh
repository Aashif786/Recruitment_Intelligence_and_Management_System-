#!/bin/bash
set -e

echo "🚀 Initiating Zero-Downtime Deployment (Blue/Green)"

# 0. Pull latest changes from GitHub
echo "📥 Syncing code from GitHub..."
git fetch --all
git reset --hard origin/main

# 1. Determine active environment
ACTIVE_ENV=$(docker ps --format "{{.Names}}" | grep -E "frontend_(blue|green)" | head -n 1 | awk -F'_' '{print $2}')
if [ -z "$ACTIVE_ENV" ]; then
    ACTIVE_ENV="green" # Default to green so we deploy blue first
fi

if [ "$ACTIVE_ENV" == "blue" ]; then
    DEPLOY_ENV="green"
    DEPLOY_FRONTEND_PORT="3002"
    DEPLOY_BACKEND_PORT="8002"
else
    DEPLOY_ENV="blue"
    DEPLOY_FRONTEND_PORT="3001"
    DEPLOY_BACKEND_PORT="8001"
fi

echo "Active environment is: $ACTIVE_ENV. Deploying to: $DEPLOY_ENV"

# 2. Build and boot the new environment safely in the background
docker compose -f docker-compose.prod.yml up -d --build frontend_$DEPLOY_ENV backend_$DEPLOY_ENV

# 3. Wait for Healthchecks (Wait up to 120 seconds)
echo "⌛ Waiting for $DEPLOY_ENV to become healthy..."
MAX_RETRIES=24
RETRY_COUNT=0
BACKEND_HEALTH="starting"

# Dynamically find the actual container name to handle prefixes/suffixes correctly
CONTAINER_NAME=$(docker ps --format '{{.Names}}' -f "name=backend_$DEPLOY_ENV" | head -n 1)

if [ -z "$CONTAINER_NAME" ]; then
    echo "⚠️ Warning: Could not find container for backend_$DEPLOY_ENV"
    # Fallback to a guess if search fails
    CONTAINER_NAME="rims-backend_$DEPLOY_ENV-1"
fi

while [ "$BACKEND_HEALTH" != "healthy" ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 5
    BACKEND_HEALTH=$(docker inspect --format='{{.State.Health.Status}}' $CONTAINER_NAME 2>/dev/null || echo "unhealthy")
    echo "Current status: $BACKEND_HEALTH ($((RETRY_COUNT * 5))s / 120s)"
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ "$BACKEND_HEALTH" != "healthy" ]; then
    echo "❌ DEPLOYMENT FAILED: Background health-check failed on $DEPLOY_ENV after 120 seconds."
    echo "Last logs:"
    docker logs $CONTAINER_NAME | tail -n 20
    docker compose -f docker-compose.prod.yml stop frontend_$DEPLOY_ENV backend_$DEPLOY_ENV
    exit 1
fi

echo "✅ New environment $DEPLOY_ENV is healthy."

echo "✅ New environment $DEPLOY_ENV is healthy."

# 4. Traffic Switching (Step 4 & 7)
echo "🔀 Switching NGINX traffic to $DEPLOY_ENV..."
sed -i "s/server frontend_$ACTIVE_ENV:3000;/server frontend_$DEPLOY_ENV:3000;/g" nginx.conf
sed -i "s/server backend_$ACTIVE_ENV:10000;/server backend_$DEPLOY_ENV:10000;/g" nginx.conf
docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload

echo "✅ Traffic successfully routed to $DEPLOY_ENV."

# 5. Stabilize (Step 9: Observability Window)
echo "🛑 Keeping old environment '$ACTIVE_ENV' alive for 15 minutes for instant rollback coverage..."
# In a real environment, a separate cron task would spin down the old container after confirming 0 error spikes.

echo "🎉 ZERO-DOWNTIME DEPLOYMENT COMPLETE."
