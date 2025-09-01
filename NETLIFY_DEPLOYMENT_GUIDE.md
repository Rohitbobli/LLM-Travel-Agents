# 🚀 Netlify Deployment Guide for Travel Co-pilot

This guide explains how to deploy your Travel Co-pilot application on Netlify. **Important**: This is a Python-based application with Gradio web interface, which requires special configuration for Netlify deployment.

## 📋 Project Analysis

Your project is a **Python web application** with:
- **Framework**: Gradio (Python web framework)
- **Backend**: FastAPI, Python agents, Agoda API integration
- **Database**: Supabase PostgreSQL
- **Dependencies**: OpenAI agents, httpx, psycopg, python-dotenv

## ⚠️ Important Considerations

**Netlify Limitation**: Netlify primarily hosts static sites and serverless functions. Your application is a full Python web server that requires:
- Continuous server runtime
- Database connections
- External API calls
- Multi-agent conversation state

**Recommended Alternatives**:
1. **Render** - Better for Python web apps
2. **Railway** - Excellent for Python deployments
3. **Heroku** - Traditional choice for Python apps
4. **DigitalOcean App Platform** - Good Python support

## 🔧 Netlify Deployment Options

### Option 1: Static Build + Serverless Functions (Limited)

This approach converts your app to static files with serverless functions, but **will lose real-time conversation state**.

#### Step 1: Create Build Configuration

Create `netlify.toml`:
```toml
[build]
  command = "python -m pip install -r requirements.txt && python build_static.py"
  publish = "dist"

[build.environment]
  PYTHON_VERSION = "3.10"

[[redirects]]
  from = "/api/*"
  to = "/.netlify/functions/:splat"
  status = 200

[functions]
  directory = "netlify/functions"
```

#### Step 2: Create Static Build Script

Create `build_static.py`:
```python
import os
import shutil
from pathlib import Path

# Create dist directory
dist_dir = Path("dist")
dist_dir.mkdir(exist_ok=True)

# Copy static assets
static_files = ["README.md", "city_mapping.csv"]
for file in static_files:
    if os.path.exists(file):
        shutil.copy2(file, dist_dir / file)

# Create index.html
index_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Travel Co-pilot</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body>
    <div id="app">
        <h1>Travel Co-pilot</h1>
        <p>This application requires server-side functionality.</p>
        <p>Please deploy to a platform that supports Python web applications.</p>
    </div>
</body>
</html>
"""

with open(dist_dir / "index.html", "w") as f:
    f.write(index_html)

print("Static build completed")
```

#### Step 3: Create Serverless Functions

Create `netlify/functions/chat.py`:
```python
import json
import os
from urllib.parse import parse_qs

# Simplified version - loses conversation state
def handler(event, context):
    try:
        if event['httpMethod'] != 'POST':
            return {
                'statusCode': 405,
                'body': json.dumps({'error': 'Method not allowed'})
            }
        
        body = json.loads(event['body'])
        message = body.get('message', '')
        
        # Simple response - you'd need to implement agent logic here
        response = {
            'response': f"Received: {message}. Note: Full agent functionality requires server deployment."
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(response)
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

### Option 2: Docker Container (Advanced)

Create `Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["python", "app.py"]
```

Create `netlify.toml` for container:
```toml
[build]
  command = "docker build -t travel-copilot ."

[build.environment]
  DOCKER_ENABLED = true
```

## 🌟 Recommended: Deploy to Render (Better Alternative)

### Step 1: Prepare for Render

Create `render.yaml`:
```yaml
services:
  - type: web
    name: travel-copilot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python app.py
    envVars:
      - key: PYTHON_VERSION
        value: 3.10.0
      - key: AGODA_API_KEY
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: SUPABASE_DB_URL
        sync: false
```

### Step 2: Update app.py for Production

Add to the end of `app.py`:
```python
if __name__ == "__main__":
    demo = create_chatbot()
    # Get port from environment (Render provides PORT)
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port, share=False)
```

## 📝 Environment Variables Setup

For any deployment platform, you'll need these environment variables:

```env
# Required
AGODA_BASE_URL=https://affiliate-api.agoda.com/api/v1
AGODA_API_KEY=your_agoda_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
SUPABASE_DB_URL=postgresql://postgres:password@host:5432/postgres

# Optional
AGODA_SEARCH_PATH=/hotels/search
```

## 🚀 Deployment Steps

### For Netlify (Limited Functionality):

1. **Prepare Repository**:
   ```bash
   git add .
   git commit -m "Prepare for Netlify deployment"
   git push origin main
   ```

2. **Connect to Netlify**:
   - Go to [netlify.com](https://netlify.com)
   - Click "New site from Git"
   - Connect your repository
   - Configure build settings:
     - Build command: `python build_static.py`
     - Publish directory: `dist`

3. **Set Environment Variables**:
   - Go to Site settings → Environment variables
   - Add all required environment variables

4. **Deploy**:
   - Netlify will automatically build and deploy
   - Note: Limited functionality due to serverless constraints

### For Render (Recommended):

1. **Create Render Account**: Go to [render.com](https://render.com)

2. **Connect Repository**: 
   - Click "New Web Service"
   - Connect your GitHub repository

3. **Configure Service**:
   - Environment: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`

4. **Set Environment Variables**: Add all required variables

5. **Deploy**: Render will build and deploy automatically

## 🔧 Troubleshooting

### Common Issues:

1. **Port Binding**: Ensure your app binds to `0.0.0.0` and uses `PORT` environment variable
2. **Dependencies**: Make sure all dependencies are in `requirements.txt`
3. **File Paths**: Use relative paths for file operations
4. **Database**: Ensure Supabase URL is correctly formatted

### Netlify-Specific Issues:

1. **Function Timeout**: Netlify functions have 10-second timeout
2. **Memory Limits**: Limited memory for serverless functions
3. **State Management**: No persistent state between function calls

## 📊 Platform Comparison

| Platform | Python Support | Real-time Apps | Database | Cost |
|----------|---------------|----------------|----------|------|
| Netlify | Limited (Functions) | ❌ | External only | Free tier |
| Render | ✅ Excellent | ✅ | ✅ | Free tier |
| Railway | ✅ Excellent | ✅ | ✅ | Usage-based |
| Heroku | ✅ Good | ✅ | ✅ | Paid plans |

## 🎯 Final Recommendation

**For your Travel Co-pilot application, I strongly recommend using Render or Railway instead of Netlify** because:

1. ✅ Full Python runtime support
2. ✅ Persistent connections and state
3. ✅ Better suited for Gradio applications
4. ✅ Easier deployment process
5. ✅ Better performance for real-time chat

If you must use Netlify, be aware that you'll need to significantly modify the application architecture and lose some functionality.

## 📞 Need Help?

If you need assistance with:
- Setting up environment variables
- Modifying the code for deployment
- Troubleshooting deployment issues
- Migrating to a different platform

Feel free to ask for specific guidance!
