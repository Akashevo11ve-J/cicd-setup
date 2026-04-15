#!/bin/bash

echo "🔴 Stopping existing process on port 7041..."
sudo fuser -k 7041/tcp

# Kill any old explore processes (safety)
echo "🧹 Cleaning old explore processes..."
ps aux | grep '[u]vicorn.*srilankan_explore_mode_v1' | awk '{print $2}' | xargs -r sudo kill -9

sleep 2

# Load env variables
echo "📦 Loading .env..."
export $(grep -v '^#' .env | xargs)

# Start service
echo "🚀 Starting Explore service on port 7041..."

nohup /home/ubuntu/anaconda3/envs/myenv/bin/uvicorn \
srilankan_explore_mode_v1:app \
--host 0.0.0.0 \
--port 7041 \
--workers 2 \
--loop uvloop \
--http httptools \
> explore.log 2>&1 &
nohup /home/ubuntu/anaconda3/envs/myenv/bin/uvicorn srilankan_practice_mode_v2:app --host 0.0.0.0 --port 7042 --workers 2 --loop uvloop --http httptools > practice.log 2>&1 &
sleep 2

# Verify
echo ""
echo "✅ Running processes:"
ps aux | grep -E '[u]vicorn|[g]unicorn|main.py'
echo ""
echo "🌐 Port check:"
netstat -tuln | grep 7041

echo ""
echo "📄 Last logs:"
tail -n 5 explore.log

echo ""
echo "✅ Explore service restarted successfully on port 7041"