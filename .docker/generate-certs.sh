#!/usr/bin/env bash
# Generates a self-signed wildcard certificate for *.changeme.com.
# Output: .docker/certs/cert.pem and .docker/certs/key.pem
#
# These files are excluded from git (.gitignore: *.pem).
# Run this script once before starting docker-compose.prod.yml.
# Replace changeme.com with your actual domain when using real certs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="$SCRIPT_DIR/certs"
DOMAIN="${1:-changeme.com}"

mkdir -p "$CERTS_DIR"

openssl req -x509 \
  -newkey rsa:4096 \
  -keyout "$CERTS_DIR/key.pem" \
  -out    "$CERTS_DIR/cert.pem" \
  -days   365 \
  -nodes \
  -subj "/C=FR/O=changeme/CN=*.$DOMAIN" \
  -addext "subjectAltName=DNS:*.$DOMAIN,DNS:$DOMAIN"

echo "Certificates written to $CERTS_DIR"
echo "  cert: $CERTS_DIR/cert.pem"
echo "  key:  $CERTS_DIR/key.pem"
echo ""
echo "These are self-signed certificates for local/staging use only."
echo "Replace with real certificates before going to production."
