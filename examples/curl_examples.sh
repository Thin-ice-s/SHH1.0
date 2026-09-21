#!/usr/bin/env bash
# SHH 1.0 - cURL API Examples

BASE_URL="http://127.0.0.1:18888"

echo "=== 1. Health & Server Info ==="
curl -s "$BASE_URL/api/info" | jq .

echo -e "\n=== 2. List Available Tools ==="
curl -s "$BASE_URL/api/tools" | jq .

echo -e "\n=== 3. Fast Shell Exec ==="
curl -s -X POST "$BASE_URL/api/exec" \
  -H "Content-Type: application/json" \
  -d '{"command": "echo Hello from cURL"}' | jq .

echo -e "\n=== 4. Capture Screen (JSON Base64) ==="
curl -s "$BASE_URL/api/screenshot?format=json&max_width=640" | jq '{width, height, file_size_kb, format}'

echo -e "\n=== 5. Get System Info ==="
curl -s -X POST "$BASE_URL/api/tools/get_system_info" \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
