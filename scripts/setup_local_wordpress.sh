#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.wordpress.yml}"
SITE_URL="${WORDPRESS_LOCAL_URL:-http://localhost:8080}"
SITE_TITLE="${WORDPRESS_LOCAL_TITLE:-Blog Agent Test}"
ADMIN_USER="${WORDPRESS_LOCAL_USER:-admin}"
ADMIN_PASSWORD="${WORDPRESS_LOCAL_PASSWORD:-admin-password-change-me}"
ADMIN_EMAIL="${WORDPRESS_LOCAL_EMAIL:-admin@example.com}"
ENV_FILE="${WORDPRESS_LOCAL_ENV_FILE:-.env.wordpress.local}"

docker compose -f "$COMPOSE_FILE" up -d

echo "Waiting for WordPress database..."
for _ in $(seq 1 60); do
  if docker compose -f "$COMPOSE_FILE" run --rm wpcli wp db check >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker compose -f "$COMPOSE_FILE" run --rm wpcli wp core is-installed >/dev/null 2>&1; then
  docker compose -f "$COMPOSE_FILE" run --rm wpcli wp core install \
    --url="$SITE_URL" \
    --title="$SITE_TITLE" \
    --admin_user="$ADMIN_USER" \
    --admin_password="$ADMIN_PASSWORD" \
    --admin_email="$ADMIN_EMAIL" \
    --skip-email
fi

APP_PASSWORD="$(
  docker compose -f "$COMPOSE_FILE" run --rm wpcli wp user application-password create "$ADMIN_USER" blog-agent \
    --porcelain \
    2>/dev/null
)"

cat > "$ENV_FILE" <<EOF
PUBLISHER=wordpress
WORDPRESS_URL=$SITE_URL
WORDPRESS_USERNAME=$ADMIN_USER
WORDPRESS_APP_PASSWORD=$APP_PASSWORD
WORDPRESS_STATUS=draft
EOF

echo "Local WordPress is ready at $SITE_URL"
echo "Credentials were written to $ENV_FILE"
echo "Run: set -a && source $ENV_FILE && set +a && python -m blog_agent.cli run --count 1 --publisher wordpress"
