#!/bin/bash

# Start Frontend Development Server Script for HDTW Project

echo "🚀 Starting HDTW Frontend Development Server..."

# Navigate to frontend directory
cd "$(dirname "$0")/frontend"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "❌ Dependencies not installed. Run setup first."
    exit 1
fi

# Start the Expo development server
echo "🌟 Starting Expo development server on http://localhost:3000"
echo ""
echo "Commands:"
echo "  Press 'w' - Open in web browser"
echo "  Press 'i' - Open in iOS simulator"
echo "  Press 'a' - Open in Android emulator"
echo "  Press 'r' - Reload app"
echo ""
yarn start
