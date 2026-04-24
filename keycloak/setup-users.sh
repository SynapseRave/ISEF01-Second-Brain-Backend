#!/usr/bin/env bash
# Setzt Passwörter für Test-User via Keycloak Admin API.
# Nötig weil Keycloak 26 plain-text Passwörter beim Realm-Import nicht zuverlässig übernimmt.
# Aufruf: ./keycloak/setup-users.sh

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM="second-brain"

echo "Warte auf Keycloak..."
until curl -sf "${KEYCLOAK_URL}/health/ready" > /dev/null 2>&1; do
  sleep 2
done
echo "Keycloak bereit."

TOKEN=$(curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin&grant_type=password&client_id=admin-cli" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

set_password() {
  local username="$1"
  local password="$2"

  USER_ID=$(curl -sf -H "Authorization: Bearer $TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=${username}" \
    | python3 -c "import sys,json; users=json.load(sys.stdin); print(users[0]['id'] if users else '')")

  if [ -z "$USER_ID" ]; then
    echo "User '${username}' nicht gefunden — übersprungen."
    return
  fi

  HTTP=$(curl -sf -o /dev/null -w "%{http_code}" -X PUT \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${USER_ID}/reset-password" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"password\",\"value\":\"${password}\",\"temporary\":false}")

  echo "User '${username}': Passwort gesetzt (HTTP ${HTTP})"
}

set_password "testuser" "test"
