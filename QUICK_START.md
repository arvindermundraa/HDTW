# Quick Start Guide 🚀

## Setup Complete! ✅

Your Live Long, Heart Strong (LLHS) project is ready to run.

---

## Running the Project (3 Easy Steps)

### Step 1: Start MongoDB
In Terminal 1:
```bash
./start-mongodb.sh
```
Or manually:
```bash
mongod --dbpath ~/data/db --port 27017
```

### Step 2: Start Backend
In Terminal 2:
```bash
./start-backend.sh
```
Backend will be available at: http://localhost:8000  
API Documentation at: http://localhost:8000/docs

### Step 3: Start Frontend
In Terminal 3:
```bash
./start-frontend.sh
```
Then press `w` to open in your browser.

---

## Important Configuration

### Before First Run
Edit `backend/.env` and update:
- `JWT_SECRET` - Set a secure random string
- `TAMUS_KEY_ENCRYPTION_SECRET` - Set a secure random string
- `RESEARCH_API_KEY` - Add your research API key (optional for testing)

### Default Configuration
- **MongoDB:** localhost:27017
- **Backend:** localhost:8000
- **Frontend:** localhost:3000
- **Database Name:** llhs_db

---

## What This App Does

Live Long, Heart Strong (LLHS) is a dietary-behavior intervention app for emerging adults (18-25) featuring:

- **Health HQ** - Food, Move, and Rest tracking (no calories shown)
- **AI Coach** - "Future Me" conversational assistant (requires TAMU AI key)
- **Meal Logging** - Text and photo-based meal tracking
- **Dining Integration** - Real Texas A&M dining hall menus
- **Curriculum** - Nutrition literacy videos and mini-games
- **Wings** - Social group features (team goals, not rankings)
- **HEI-2020 Integration** - Research-imported diet quality scores

---

## Testing

### Run Backend Tests
The suite registers many users, so run it against a separate server with rate limiting off and a fresh database:
```bash
cd backend
source venv/bin/activate
RATE_LIMIT_ENABLED=false DB_NAME=llhs_pytest_$(date +%s) uvicorn server:app --port 8011 &
export $(grep '^RESEARCH_API_KEY' .env)
RATE_LIMIT_ENABLED=false EXPO_PUBLIC_BACKEND_URL=http://localhost:8011 python -m pytest tests/ -n 0
```
HEI-2020 scoring unit tests alone (no server needed): `python -m pytest tests/test_hei2020_scoring.py -n 0`

### Research admin (ASA24 upload)
Create the first researcher admin once: `cd backend && python manage_researchers.py add you@tamu.edu --admin` (prompts for a password). Then open http://localhost:8000/research-admin and sign in; add other staff from the page. Staff steps: `docs/ASA24-STAFF-GUIDE.md`. A synthetic sample file is at `backend/tests/fixtures/asa24_totals_sample.csv`.

### Check System Status
```bash
# Check if MongoDB is running
pgrep -l mongod

# Check if ports are available
lsof -i :27017  # MongoDB
lsof -i :8000   # Backend
lsof -i :3000   # Frontend
```

---

## Key Features to Test

1. **User Registration/Login** - JWT-based authentication
2. **Meal Logging** - Text or photo (requires TAMU key)
3. **Dining Hall Menus** - Real-time data from Commons & Sbisa
4. **AI Coach Chat** - Conversational assistant (requires TAMU key)
5. **Health Domains** - Food, Move, Rest tracking
6. **Onboarding Survey** - Nutrition & Lifestyle Profile

---

## Troubleshooting

### "Connection refused" error
- MongoDB is not running. Run `./start-mongodb.sh`

### "Module not found" error
**Backend:**
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

**Frontend:**
```bash
cd frontend
yarn install
```

### Port already in use
```bash
# Find and kill the process using a port
lsof -ti:8000 | xargs kill -9  # Backend
lsof -ti:3000 | xargs kill -9  # Frontend
```

### TAMU AI not working
- Users need to add their TAMU API key in app Settings
- Get key from: https://chat.tamu.edu
- Admin test accounts can be configured in `.env` with `TAMUS_ADMIN_TEST_EMAILS` and `TAMUS_ADMIN_API_KEYS`

---

## Development Tools

### View Database
Use MongoDB Compass to connect to: `mongodb://localhost:27017`

### API Testing
Interactive API docs available at: http://localhost:8000/docs

### Frontend Debugging
- Press `j` in Expo to open debugger
- Press `m` to toggle menu in app
- Press `r` to reload

---

## Need More Details?

- **Full Setup Instructions:** See `SETUP_INSTRUCTIONS.md`
- **Project Documentation:** See `README.md`
- **Test Coverage:** See `backend/tests/backend_test.py`
- **Latest changes & open questions:** See `docs/CHANGELOG-2026-09-24.md`
- **ASA24 staff workflow:** See `docs/ASA24-STAFF-GUIDE.md`

---

## Project Structure

```
.
├── backend/           # FastAPI + MongoDB backend
│   ├── server.py      # Main API server
│   ├── dining_*.py    # Dining hall integration
│   ├── tamus_client.py # TAMU AI integration
│   └── tests/         # Test suite
│
├── frontend/          # React Native + Expo app
│   ├── app/           # Main app screens
│   │   ├── (tabs)/    # Tab navigation
│   │   ├── auth.tsx   # Authentication
│   │   ├── build-meal.tsx
│   │   └── ...
│   └── src/           # Components and utilities
│
└── Quick start scripts (this directory)
```

---

Ready to go! 🎉

Run `./start-mongodb.sh`, `./start-backend.sh`, and `./start-frontend.sh` in separate terminals to get started.
