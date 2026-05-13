#!/bin/bash
# Usage: ./deploy/upload_data.sh ubuntu@YOUR_EC2_IP
set -e

EC2_HOST=${1:-"ubuntu@YOUR_EC2_IP"}
PITIQ_DIR="/home/ubuntu/pitiq"

echo "Uploading data/features to $EC2_HOST..."
rsync -avz --progress data/features/ "$EC2_HOST:$PITIQ_DIR/data/features/"

echo "Uploading models to $EC2_HOST..."
rsync -avz --progress models/ "$EC2_HOST:$PITIQ_DIR/models/"

echo "Done. Now run:"
echo "  ssh $EC2_HOST 'cd $PITIQ_DIR && docker compose up -d --build'"
