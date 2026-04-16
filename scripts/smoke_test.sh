#!/usr/bin/env bash
# Marco live smoke test — verifies the deployed instance at marco.nuriy.com
#
# Usage:
#   MARCO_TOKEN=your_token ./scripts/smoke_test.sh
#   MARCO_TOKEN=your_token MARCO_URL=https://marco.nuriy.com ./scripts/smoke_test.sh

set -euo pipefail

URL="${MARCO_URL:-https://marco.nuriy.com}"
TOKEN="${MARCO_TOKEN:?set MARCO_TOKEN to your login token}"
AUTH="Authorization: Bearer $TOKEN"

PASS=0
FAIL=0

pass() { echo "  PASS  $1"; ((PASS++)); }
fail() { echo "  FAIL  $1 — $2"; ((FAIL++)); }

echo "Marco smoke test → $URL"
echo "---"

# 1. Health / login page responds
echo "[1] Server reachable"
STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$URL/login" || echo "000")
if [[ "$STATUS" == "200" ]]; then pass "GET /login → 200"
else fail "GET /login" "HTTP $STATUS"; fi

# 2. Sessions list
echo "[2] Sessions API"
RESP=$(curl -sf -H "$AUTH" "$URL/api/sessions" || echo "{}")
if echo "$RESP" | grep -q '"sessions"'; then pass "GET /api/sessions → has sessions key"
else fail "GET /api/sessions" "$RESP"; fi

# 3. Create a plan
echo "[3] Create plan"
RESP=$(curl -sf -X POST "$URL/api/sessions/plan" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"goal":"smoke test: verify deployment"}' || echo "{}")
SESSION_ID=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id',''))" 2>/dev/null || echo "")
if [[ -n "$SESSION_ID" ]]; then pass "POST /api/sessions/plan → session_id=$SESSION_ID"
else fail "POST /api/sessions/plan" "$RESP"; fi

# 4. Fetch the session detail
if [[ -n "$SESSION_ID" ]]; then
  echo "[4] Session detail"
  RESP=$(curl -sf -H "$AUTH" "$URL/api/sessions/$SESSION_ID" || echo "{}")
  PHASE=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('phase',''))" 2>/dev/null || echo "")
  if [[ "$PHASE" == "planned" ]]; then pass "GET /api/sessions/$SESSION_ID → phase=planned"
  else fail "GET /api/sessions/$SESSION_ID" "phase='$PHASE'"; fi
fi

# 5. Execute endpoint opens SSE stream (first line check — LLM may or may not be configured)
if [[ -n "$SESSION_ID" ]]; then
  echo "[5] Execute streams SSE"
  FIRST=$(curl -sf -X POST -H "$AUTH" \
    --max-time 10 --no-buffer \
    "$URL/api/sessions/$SESSION_ID/execute" 2>/dev/null | head -2 || echo "")
  if [[ "$FIRST" == event:* || "$FIRST" == data:* ]]; then pass "POST /execute → SSE stream opens"
  else fail "POST /execute" "no SSE data (got: '$FIRST')"; fi
fi

# 6. Patches list
echo "[6] Patches API"
RESP=$(curl -sf -H "$AUTH" "$URL/api/patches" || echo "{}")
if echo "$RESP" | grep -q '"patches"'; then pass "GET /api/patches → has patches key"
else fail "GET /api/patches" "$RESP"; fi

echo "---"
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
