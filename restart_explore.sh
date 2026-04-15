#!/bin/bash

echo "================================================"
echo "  Restarting Explore (7041) + Practice (7042)"
echo "================================================"

# ── Kill existing processes ──────────────────────────
echo ""
echo "🔴 Stopping port 7041 (Explore)..."
sudo fuser -k 7041/tcp 2>/dev/null || true

echo "🔴 Stopping port 7042 (Practice)..."
sudo fuser -k 7042/tcp 2>/dev/null || true

echo "🧹 Cleaning old uvicorn processes..."
ps aux | grep '[u]vicorn.*srilankan_explore_mode_v1' | awk '{print $2}' | xargs -r sudo kill -9 2>/dev/null || true
ps aux | grep '[u]vicorn.*srilankan_practice_mode_v2' | awk '{print $2}' | xargs -r sudo kill -9 2>/dev/null || true

sleep 3

# ── Load env ─────────────────────────────────────────
echo ""
echo "📦 Loading .env..."
export $(grep -v '^#' /home/ubuntu/cicd-setup/.env | xargs)

# ── Start Explore on 7041 ────────────────────────────
echo ""
echo "🚀 Starting Explore service on port 7041..."
nohup /home/ubuntu/anaconda3/envs/myenv/bin/uvicorn \
    srilankan_explore_mode_v1:app \
    --host 0.0.0.0 \
    --port 7041 \
    --workers 2 \
    --loop uvloop \
    --http httptools \
    > /home/ubuntu/cicd-setup/explore.log 2>&1 &

EXPLORE_PID=$!
echo "   Explore PID: $EXPLORE_PID"

# ── Start Practice on 7042 ───────────────────────────
echo ""
echo "🚀 Starting Practice service on port 7042..."
nohup /home/ubuntu/anaconda3/envs/myenv/bin/uvicorn \
    srilankan_practice_mode_v2:app \
    --host 0.0.0.0 \
    --port 7042 \
    --workers 2 \
    --loop uvloop \
    --http httptools \
    > /home/ubuntu/cicd-setup/practice.log 2>&1 &

PRACTICE_PID=$!
echo "   Practice PID: $PRACTICE_PID"

# ── Wait for services to boot ────────────────────────
echo ""
echo "⏳ Waiting for services to start..."
sleep 5

# ── Health checks ────────────────────────────────────
echo ""
echo "🏥 Health checking port 7041 (Explore)..."
if curl -s --max-time 5 http://localhost:7041/docs > /dev/null; then
    echo "   ✅ Explore is UP on port 7041"
else
    echo "   ❌ Explore NOT responding on port 7041"
    tail -n 10 /home/ubuntu/cicd-setup/explore.log
    exit 1
fi

echo ""
echo "🏥 Health checking port 7042 (Practice)..."
if curl -s --max-time 5 http://localhost:7042/docs > /dev/null; then
    echo "   ✅ Practice is UP on port 7042"
else
    echo "   ❌ Practice NOT responding on port 7042"
    tail -n 10 /home/ubuntu/cicd-setup/practice.log
    exit 1
fi

# ── Summary ──────────────────────────────────────────
echo ""
echo "================================================"
echo "✅ Both services running!"
echo "   Explore  → http://0.0.0.0:7041"
echo "   Practice → http://0.0.0.0:7042"
echo "================================================"
echo ""
echo "🌐 Port check:"
netstat -tuln | grep -E '7041|7042'
echo ""
echo "📄 Explore last logs:"
tail -n 5 /home/ubuntu/cicd-setup/explore.log
echo ""
echo "📄 Practice last logs:"
tail -n 5 /home/ubuntu/cicd-setup/practice.log