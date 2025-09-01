import os
import shutil
from pathlib import Path

def build_static():
    """Build static files for Netlify deployment"""
    
    # Create public directory
    public_dir = Path("public")
    public_dir.mkdir(exist_ok=True)
    
    # Copy static assets
    static_files = ["README.md", "city_mapping.csv"]
    for file in static_files:
        if os.path.exists(file):
            shutil.copy2(file, public_dir / file)
    
    # Create index.html
    index_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Travel Co-pilot API</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }
        .api-endpoint {
            background: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            font-family: monospace;
        }
        .warning {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <h1>🧳 Travel Co-pilot API</h1>
    
    <div class="warning">
        <strong>⚠️ Limited Functionality Notice:</strong>
        This Netlify deployment provides basic API endpoints but lacks full multi-agent conversation state. 
        For complete functionality, deploy to Heroku, Render, or Railway.
    </div>
    
    <h2>📡 Available API Endpoints</h2>
    
    <h3>Health Check</h3>
    <div class="api-endpoint">GET /api/healthz</div>
    
    <h3>Chat (Simplified)</h3>
    <div class="api-endpoint">POST /api/chat</div>
    <p>Send JSON: <code>{"message": "Plan a trip to Paris"}</code></p>
    
    <h2>🧪 Test the API</h2>
    <button onclick="testHealth()">Test Health Check</button>
    <button onclick="testChat()">Test Chat</button>
    
    <div id="results"></div>
    
    <script>
        async function testHealth() {
            try {
                const response = await fetch('/api/healthz');
                const data = await response.json();
                document.getElementById('results').innerHTML = 
                    '<h3>Health Check Result:</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
            } catch (error) {
                document.getElementById('results').innerHTML = 
                    '<h3>Error:</h3><pre>' + error.message + '</pre>';
            }
        }
        
        async function testChat() {
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: 'Hello, plan a trip to Tokyo' })
                });
                const data = await response.json();
                document.getElementById('results').innerHTML = 
                    '<h3>Chat Result:</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
            } catch (error) {
                document.getElementById('results').innerHTML = 
                    '<h3>Error:</h3><pre>' + error.message + '</pre>';
            }
        }
    </script>
    
    <h2>📚 Documentation</h2>
    <p>For full API documentation and deployment guides, check the repository files:</p>
    <ul>
        <li><strong>HEROKU_DEPLOYMENT_GUIDE.md</strong> - Recommended deployment platform</li>
        <li><strong>NETLIFY_DEPLOYMENT_GUIDE.md</strong> - This platform (limited functionality)</li>
        <li><strong>api.py</strong> - Full API implementation</li>
    </ul>
</body>
</html>"""
    
    with open(public_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)
    
    print("✅ Static build completed for Netlify")
    print(f"📁 Files created in: {public_dir.absolute()}")

if __name__ == "__main__":
    build_static()
