#!/bin/bash
# Run on a fresh Ubuntu EC2 instance to install Docker and set up PitIQ.
set -e

echo "Setting up PitIQ on EC2..."

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y \
    docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

# Allow ubuntu user to run Docker without sudo
sudo usermod -aG docker ubuntu

# Create PitIQ directory structure
mkdir -p /home/ubuntu/pitiq/data/features
mkdir -p /home/ubuntu/pitiq/models

echo ""
echo "Docker installed successfully."
echo "Log out and back in (so docker group takes effect), then:"
echo "  1. Upload data:  ./deploy/upload_data.sh ubuntu@<this-ip>"
echo "  2. Clone repo:   git clone <repo> /home/ubuntu/pitiq  (or rsync)"
echo "  3. Start stack:  cd /home/ubuntu/pitiq && docker compose up -d --build"
