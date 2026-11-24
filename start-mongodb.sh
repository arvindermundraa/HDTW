#!/bin/bash

# Start MongoDB Script for HDTW Project

echo "🗄️  Starting MongoDB..."

# Create data directory if it doesn't exist
DATA_DIR="$HOME/data/db"
if [ ! -d "$DATA_DIR" ]; then
    echo "📁 Creating data directory at $DATA_DIR"
    mkdir -p "$DATA_DIR"
fi

# Check if MongoDB is already running
if pgrep -x "mongod" > /dev/null; then
    echo "✅ MongoDB is already running!"
    echo ""
    echo "Connection string: mongodb://localhost:27017"
    echo "Database name: llhs_db"
    exit 0
fi

# Start MongoDB
echo "🚀 Starting MongoDB on port 27017..."
echo "📁 Data directory: $DATA_DIR"
echo ""
echo "Connection string: mongodb://localhost:27017"
echo "Database name: llhs_db"
echo ""
echo "Press Ctrl+C to stop MongoDB"
echo ""

mongod --dbpath "$DATA_DIR" --port 27017
