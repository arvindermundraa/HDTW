# Project Setup Complete! 🎉

## What's Been Done

### ✅ Backend Setup
1. Created Python virtual environment (`backend/venv`)
2. Installed all Python dependencies from `requirements.txt`
3. Created `.env` configuration file (from `.env.example`)

### ✅ Frontend Setup
1. Installed all Node.js dependencies using Yarn
2. All Expo and React Native packages are ready

### ✅ Database
- MongoDB 8.2.4 is installed and available

---

## Next Steps to Run the Project

### 1. Start MongoDB (Required)
MongoDB needs to be running before starting the backend. Run this in a terminal:

```bash
mongod --dbpath ~/data/db --port 27017
```

**Note:** You may need to create the data directory first:
```bash
mkdir -p ~/data/db
```

### 2. Configure Environment Variables
Edit the `.env` file in the `backend` directory:

```bash
cd backend
nano .env
```

**Important variables to configure:**
- `JWT_SECRET` - Change to a secure random string for production
- `TAMUS_KEY_ENCRYPTION_SECRET` - Change to a secure random string
- `RESEARCH_API_KEY` - Set your research API key
- `CORS_ALLOWED_ORIGINS` - Add your frontend URLs

### 3. Start the Backend Server
In a new terminal:

```bash
cd backend
source venv/bin/activate
uvicorn server:app --reload --port 8000
```

The backend will be available at: `http://localhost:8000`
API docs at: `http://localhost:8000/docs`

### 4. Start the Frontend Development Server
In another terminal:

```bash
cd frontend
yarn start
```

This will start the Expo development server on port 3000.

### 5. Run the App
After `yarn start`, you can:
- Press `w` to open in web browser
- Press `i` to open in iOS simulator (requires Xcode)
- Press `a` to open in Android emulator (requires Android Studio)
- Scan the QR code with Expo Go app on your phone

---

## Running Tests

### Backend Tests
```bash
cd backend
source venv/bin/activate
pytest -v
```

Note: Some tests require `RESEARCH_API_KEY` to be set in the environment.

---

## Project Architecture

### Backend (FastAPI + MongoDB)
- **Location:** `/backend`
- **Main file:** `server.py`
- **Key modules:**
  - `dining_scraper.py` - Real Texas A&M dining hall integration
  - `dining_classifier.py` - Food categorization
  - `plate_composer.py` - Meal suggestions
  - `tamus_client.py` - TAMU AI integration

### Frontend (React Native + Expo)
- **Location:** `/frontend`
- **Main navigation:** `app/(tabs)` directory
- **Key screens:**
  - Home/Health HQ - Food, Move, Rest domains
  - Coach - AI chat assistant
  - Learn - Curriculum and games
  - Social - Wings (group features)
  - Profile - Settings and user info

---

## Troubleshooting

### MongoDB Connection Issues
If you see "MongoError: connect ECONNREFUSED":
1. Make sure MongoDB is running: `pgrep -l mongod`
2. Check the connection string in `.env`
3. Ensure the data directory exists and has permissions

### Port Conflicts
- Backend uses port **8000**
- Frontend uses port **3000**
- MongoDB uses port **27017**

If any port is in use, you can:
- Change the port in the respective configuration
- Kill the process using the port: `lsof -ti:PORT | xargs kill -9`

### Missing Dependencies
If you encounter import errors:
- Backend: `pip install -r requirements.txt` in the venv
- Frontend: `yarn install` or `yarn add <package>`

### TAMU AI Features
The app requires TAMU AI keys for:
- AI coach chat
- Photo meal logging
- Text meal categorization
- Dining hall chat assistant

Users need to add their TAMU API key from `chat.tamu.ai` in the app settings.

---

## Development Tips

### Backend Hot Reload
The `--reload` flag enables auto-restart when code changes.

### Frontend Metro Bundler
Press `r` to reload the app, or `Shift + R` for a full refresh.

### View API Documentation
Visit `http://localhost:8000/docs` for interactive API documentation.

### Database GUI
Consider using MongoDB Compass for visual database management:
`mongodb://localhost:27017`

---

## Important Security Notes

⚠️ **Before deploying to production:**

1. Change all default secrets in `.env`
2. Set up proper CORS origins
3. Configure a production MongoDB instance
4. Enable HTTPS
5. Review rate limiting settings
6. Set up proper logging and monitoring

---

## Resources

- **Expo Documentation:** https://docs.expo.dev/
- **FastAPI Documentation:** https://fastapi.tiangolo.com/
- **MongoDB Documentation:** https://docs.mongodb.com/
- **React Native Documentation:** https://reactnative.dev/

---

For questions or issues, refer to the main `README.md` file.
