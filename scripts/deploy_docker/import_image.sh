#!/bin/bash
set -e

echo "========================================"
echo "   MyAPS Docker Import Script"
echo "========================================"
echo ""

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EXPORT_DIR="$SCRIPT_DIR/../../docker_images"

if [ ! -d "$EXPORT_DIR" ]; then
    echo "[ERROR] docker_images directory not found!"
    echo "Please copy images to: $EXPORT_DIR"
    exit 1
fi

echo "Importing images..."
echo ""

for file in "$EXPORT_DIR"/*.tar; do
    [ -f "$file" ] || continue
    echo "Importing: $(basename "$file")"
    docker load -i "$file"
    if [ $? -ne 0 ]; then
        echo ""
        echo "[ERROR] Failed to import $(basename "$file")!"
        exit 1
    fi
done

echo ""
echo "========================================"
echo "   Import completed!"
echo "========================================"
echo ""
echo "Images:"
docker images | grep -E "(myaps|postgres|redis|nginx)"
echo ""
echo "Next steps:"
echo "  1. Run: docker-compose -f scripts/deploy_docker/docker-compose.yml up -d"
echo "  2. Run: docker-compose -f scripts/deploy_docker/docker-compose.yml ps"
echo ""