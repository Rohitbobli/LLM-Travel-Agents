# 🚀 Heroku Deployment Guide for Travel Co-pilot

This comprehensive guide explains how to deploy your Travel Co-pilot application on Heroku. Your project is perfectly suited for Heroku deployment with its FastAPI backend and multi-agent architecture.

## 📋 Project Analysis

Your Travel Co-pilot is a **Python web application** featuring:
- **API Framework**: FastAPI with async support
- **Web Interface**: Gradio (optional, can run API-only)
- **Multi-Agent System**: OpenAI agents with conversation state
- **Database**: Supabase PostgreSQL (external)
- **External APIs**: Agoda affiliate API integration
- **Session Management**: In-memory sessions with conversation tracking

## ✅ Why Heroku is Perfect for Your Project

- ✅ **Full Python Runtime**: Native support for Python web applications
- ✅ **Persistent Processes**: Maintains conversation state and sessions
- ✅ **Database Connections**: Seamless external database integration
- ✅ **Environment Variables**: Secure API key management
- ✅ **Auto-scaling**: Handles traffic spikes automatically
- ✅ **Easy Deployment**: Git-based deployment workflow

## 🛠️ Pre-Deployment Setup

### Step 1: Create Required Heroku Files

#### 1.1 Create `Procfile`
```
web: uvicorn api:app --host 0.0.0.0 --port $PORT
```

#### 1.2 Create `runtime.txt`
```
python-3.10.12
```

#### 1.3 Update `requirements.txt` (if needed)
Ensure your `requirements.txt` includes all dependencies:
```
openai-agents
gradio
fastapi
uvicorn[standard]
python-docx
python-dotenv
httpx
psycopg[binary]
pydantic
```

#### 1.4 Create `app.json` (Optional - for Heroku Button)
```json
{
  "name": "Travel Co-pilot API",
  "description": "AI-powered travel planning assistant with multi-agent system",
  "repository": "https://github.com/yourusername/agent-itinerary",
  "logo": "https://cdn.jsdelivr.net/npm/simple-icons@v3/icons/heroku.svg",
  "keywords": ["python", "fastapi", "ai", "travel", "agents"],
  "env": {
    "AGODA_BASE_URL": {
      "description": "Agoda API base URL",
      "value": "https://affiliate-api.agoda.com/api/v1"
    },
    "AGODA_API_KEY": {
      "description": "Your Agoda affiliate API key"
    },
    "OPENAI_API_KEY": {
      "description": "Your OpenAI API key for the agents"
    },
    "SUPABASE_DB_URL": {
      "description": "Your Supabase PostgreSQL connection string"
    }
  },
  "formation": {
    "web": {
      "quantity": 1,
      "size": "basic"
    }
  }
}
```

### Step 2: Modify API for Heroku

#### 2.1 Update `api.py` for Production
Add this at the end of your `api.py` file:

```python
# Add after the existing code, before if __name__ == "__main__":

import os

# Heroku-specific configuration
PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host=HOST, port=PORT, reload=False)
```

#### 2.2 Create Health Check Endpoint (Already exists)
Your existing `/healthz` endpoint is perfect for Heroku health checks.

### Step 3: Environment Variables Setup

Create a `.env.example` file for reference:
```env
# Required API Keys
AGODA_BASE_URL=https://affiliate-api.agoda.com/api/v1
AGODA_API_KEY=your_agoda_api_key_here
AGODA_SEARCH_PATH=/hotels/search
OPENAI_API_KEY=your_openai_api_key_here

# Database
SUPABASE_DB_URL=postgresql://postgres:password@host:5432/postgres

# Optional
PYTHON_ENV=production
```

## 🚀 Deployment Methods

### Method 1: Heroku CLI (Recommended)

#### Step 1: Install Heroku CLI
Download from: https://devcenter.heroku.com/articles/heroku-cli

#### Step 2: Login and Create App
```bash
# Login to Heroku
heroku login

# Create new app (replace 'your-app-name' with desired name)
heroku create your-travel-copilot-api

# Or if you want to specify region
heroku create your-travel-copilot-api --region us
```

#### Step 3: Set Environment Variables
```bash
# Set required environment variables
heroku config:set AGODA_BASE_URL="https://affiliate-api.agoda.com/api/v1"
heroku config:set AGODA_API_KEY="your_actual_api_key"
heroku config:set AGODA_SEARCH_PATH="/hotels/search"
heroku config:set OPENAI_API_KEY="your_actual_openai_key"
heroku config:set SUPABASE_DB_URL="your_actual_supabase_url"
heroku config:set PYTHON_ENV="production"

# Verify environment variables
heroku config
```

#### Step 4: Deploy
```bash
# Add Heroku remote (if not done automatically)
heroku git:remote -a your-travel-copilot-api

# Deploy to Heroku
git add .
git commit -m "Prepare for Heroku deployment"
git push heroku main

# Open your app
heroku open
```

### Method 2: GitHub Integration

#### Step 1: Connect Repository
1. Go to [Heroku Dashboard](https://dashboard.heroku.com)
2. Click "New" → "Create new app"
3. Choose app name and region
4. In "Deployment method", select "GitHub"
5. Connect your repository

#### Step 2: Configure Environment Variables
1. Go to "Settings" tab
2. Click "Reveal Config Vars"
3. Add all required environment variables:
   - `AGODA_BASE_URL`
   - `AGODA_API_KEY`
   - `OPENAI_API_KEY`
   - `SUPABASE_DB_URL`
   - `AGODA_SEARCH_PATH`

#### Step 3: Deploy
1. Go to "Deploy" tab
2. Enable "Automatic deploys" (optional)
3. Click "Deploy Branch"

## 🔧 Configuration Files Reference

### Complete `Procfile`
```
web: uvicorn api:app --host 0.0.0.0 --port $PORT --workers 1
```

### Complete `runtime.txt`
```
python-3.10.12
```

### Updated `requirements.txt`
```
openai-agents>=1.0.0
gradio>=4.0.0
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
python-docx>=0.8.11
python-dotenv>=1.0.0
httpx>=0.24.0
psycopg[binary]>=3.1.0
pydantic>=2.0.0
```

## 📊 API Endpoints

Your deployed API will have these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Health check |
| `/chat` | POST | Send message to travel agent |
| `/itineraries/{conversation_id}` | GET | Get itinerary |
| `/itineraries/{conversation_id}/populate-accommodations` | POST | Populate hotels |

### Example API Usage

```bash
# Health check
curl https://your-app-name.herokuapp.com/healthz

# Start conversation
curl -X POST https://your-app-name.herokuapp.com/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to plan a trip to Paris for 5 days"}'

# Get itinerary
curl https://your-app-name.herokuapp.com/itineraries/{conversation_id}
```

## 🔍 Monitoring and Troubleshooting

### View Logs
```bash
# View real-time logs
heroku logs --tail

# View recent logs
heroku logs --num 100
```

### Scale Dynos
```bash
# Scale up
heroku ps:scale web=2

# Scale down
heroku ps:scale web=1

# Check dyno status
heroku ps
```

### Restart App
```bash
heroku restart
```

## 💰 Heroku Pricing Tiers

| Tier | Price | Features |
|------|-------|----------|
| **Eco** | $5/month | Sleeps after 30min inactivity |
| **Basic** | $7/month | Never sleeps, custom domains |
| **Standard-1X** | $25/month | Better performance, metrics |
| **Standard-2X** | $50/month | 2x RAM and CPU |

**Recommendation**: Start with **Basic** ($7/month) for production use since your app needs persistent sessions.

## 🛡️ Security Best Practices

### 1. Environment Variables
- Never commit API keys to Git
- Use Heroku Config Vars for all secrets
- Rotate API keys regularly

### 2. Database Security
- Use connection pooling for Supabase
- Enable SSL connections
- Monitor database access logs

### 3. API Security
```python
# Add to api.py for production security
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["your-app-name.herokuapp.com", "localhost"]
)
```

## 🚀 Advanced Configuration

### Custom Domain
```bash
# Add custom domain
heroku domains:add www.yourdomain.com

# Get DNS target
heroku domains
```

### SSL Certificate
```bash
# Add SSL (automatic with custom domains)
heroku certs:auto:enable
```

### Database Connection Pooling
Add to your `api.py`:
```python
import os
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

# For better database performance
if os.getenv("SUPABASE_DB_URL"):
    engine = create_engine(
        os.getenv("SUPABASE_DB_URL"),
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True
    )
```

## 📈 Performance Optimization

### 1. Memory Usage
- Monitor memory usage with `heroku logs`
- Consider upgrading to Standard-2X if needed
- Implement session cleanup for old conversations

### 2. Response Times
- Use async/await throughout your code
- Implement caching for frequent requests
- Monitor with Heroku metrics

### 3. Session Management
Add session cleanup to `api.py`:
```python
import time
from datetime import datetime, timedelta

# Clean old sessions (add to api.py)
def cleanup_old_sessions():
    cutoff = datetime.now() - timedelta(hours=24)
    # Implement cleanup logic based on last activity
    pass

# Call periodically or on app startup
```

## 🔄 CI/CD Pipeline

### GitHub Actions (Optional)
Create `.github/workflows/deploy.yml`:
```yaml
name: Deploy to Heroku
on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - uses: akhileshns/heroku-deploy@v3.12.12
      with:
        heroku_api_key: ${{secrets.HEROKU_API_KEY}}
        heroku_app_name: "your-app-name"
        heroku_email: "your-email@example.com"
```

## 🆘 Common Issues and Solutions

### Issue 1: App Crashes on Startup
```bash
# Check logs
heroku logs --tail

# Common fixes:
# 1. Check Procfile syntax
# 2. Verify all environment variables are set
# 3. Ensure requirements.txt is complete
```

### Issue 2: Memory Errors
```bash
# Upgrade dyno type
heroku ps:scale web=1:standard-2x
```

### Issue 3: Slow Response Times
- Check database connection pooling
- Monitor external API response times (Agoda)
- Consider caching frequently accessed data

### Issue 4: Session State Lost
- Implement Redis for session storage (Heroku Redis add-on)
- Or use database-backed sessions

## 📞 Support and Resources

### Heroku Resources
- [Heroku Dev Center](https://devcenter.heroku.com/)
- [Python on Heroku](https://devcenter.heroku.com/categories/python-support)
- [Heroku CLI Reference](https://devcenter.heroku.com/articles/heroku-cli-commands)

### Your App Monitoring
```bash
# Monitor your deployed app
heroku logs --tail --app your-travel-copilot-api
heroku ps --app your-travel-copilot-api
heroku config --app your-travel-copilot-api
```

## ✅ Deployment Checklist

- [ ] Create `Procfile`
- [ ] Create `runtime.txt`
- [ ] Update `requirements.txt`
- [ ] Set all environment variables
- [ ] Test API endpoints locally
- [ ] Deploy to Heroku
- [ ] Verify health check endpoint
- [ ] Test conversation flow
- [ ] Monitor logs for errors
- [ ] Set up custom domain (optional)
- [ ] Configure SSL (optional)

## 🎯 Next Steps After Deployment

1. **Test Your API**: Use the provided curl examples
2. **Monitor Performance**: Check Heroku metrics dashboard
3. **Set Up Alerts**: Configure log-based alerts
4. **Scale as Needed**: Monitor usage and scale dynos
5. **Implement Caching**: Add Redis for better performance
6. **Add Monitoring**: Consider APM tools like New Relic

Your Travel Co-pilot API will be live at: `https://your-app-name.herokuapp.com`

Happy deploying! 🚀
