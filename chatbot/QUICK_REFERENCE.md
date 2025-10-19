# Chatbot Quick Reference Card

## 🚀 Start the Chatbot

```bash
cd chatbot
./start-chatbot.sh
```

Then open: http://localhost:8001

---

## 💬 Chat Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `/info` | Show config & cache status | `/info` |
| `/collections` | List all collections | `/collections` |
| `/switch <name>` | Switch collection | `/switch hr-docs` |
| `/refresh` | Refresh cache now | `/refresh` |
| `/help` or `/?` | Show help | `/help` |

---

## ⚙️ Environment Variables

Create or edit `chatbot/.env`:

```bash
# VectorDB
CHROMA_DB_PATH=../backend/chroma_db

# Cache (auto-refresh)
CACHE_REFRESH_SECONDS=120        # Default: 2 minutes

# LLM Provider
LLM_PROVIDER=groq                # groq, gemini, or openai
MODEL_NAME=mixtral-8x7b-32768   # Model to use
TEMPERATURE=0.7                  # Creativity (0-1)
MAX_TOKENS=1024                  # Response length

# API Keys (choose one)
GROQ_API_KEY=your_key_here      # Get from: https://console.groq.com/keys
# GOOGLE_API_KEY=your_key_here  # Get from: https://makersuite.google.com/app/apikey
# OPENAI_API_KEY=your_key_here  # Get from: https://platform.openai.com/api-keys
```

---

## 🔄 Manual Refresh (Default)

### How It Works
- **Manual mode (default):** Say "refresh" when you upload documents
- **Auto mode (optional):** Enable `CACHE_AUTO_REFRESH=true` for automatic checks
- **Fast:** No background checks in manual mode
- **Control:** You decide exactly when to reload

### How to Refresh
Just say any of these:
- `refresh`
- `reload`
- `update`
- `/refresh`

**Example:**
```
[Upload document in main UI]
User: refresh
Bot: ✅ Cache refreshed! Documents: 5 → 6 (+1 change)
```

### Enable Auto-Refresh (Optional)
```bash
# .env
CACHE_AUTO_REFRESH=true
CACHE_REFRESH_SECONDS=120  # Check every 2 minutes
```

### Check Status
```
/info
```

Shows refresh mode and last refresh time.

---

## 📚 Typical Workflow

### 1. Upload Documents (Main UI)
```bash
# Start backend
cd backend
uvicorn main:app --reload

# Open: http://localhost:8000
# Upload documents via UI
```

### 2. Query Documents (Chatbot)
```bash
# Start chatbot
cd chatbot
./start-chatbot.sh

# Open: http://localhost:8001
```

**Ask questions:**
```
What is our vacation policy?

How do I deploy to production?

What are the security guidelines?
```

### 3. Get Latest Documents
**Option A - Wait for auto-refresh (2 minutes):**
```
[After uploading new doc, wait 2 minutes]
Ask your question
→ Chatbot automatically refreshes and uses new doc
```

**Option B - Force immediate refresh:**
```
/refresh
Ask your question
→ Chatbot immediately uses new doc
```

---

## 🎯 Common Tasks

### Switch Between Document Collections
```
/collections                 # See available collections
/switch technical-docs      # Switch to technical docs
```

### Check What LLM Is Being Used
```
/info
```

Shows current LLM provider, model, and configuration.

### Get Help
```
/help
```

Shows all available commands.

---

## 🔧 Troubleshooting

### Chatbot Not Finding New Documents
**Solution:** Say "refresh"
```
refresh
```

Or use command:
```
/refresh
```

### Want Automatic Updates
**Solution:** Enable auto-refresh in `.env`
```bash
CACHE_AUTO_REFRESH=true
CACHE_REFRESH_SECONDS=120
```

Then restart chatbot.

### API Key Error
**Solution:** Check `.env` file
```bash
cd chatbot
cat .env                    # Verify key is set
nano .env                   # Edit if needed
```

### Collection Not Found
**Solution:** List collections
```
/collections                # See what's available
/switch <name>             # Switch to correct one
```

---

## 📖 Documentation

- **Main README:** `chatbot/README.md`
- **Auto-Refresh Guide:** `chatbot/AUTO_REFRESH_GUIDE.md`
- **Implementation Details:** `AUTO_REFRESH_IMPLEMENTATION.md`
- **This Card:** `chatbot/QUICK_REFERENCE.md`

---

## 💡 Pro Tips

### Tip 1: Use Manual Refresh for Demos
Set long auto-refresh interval and control manually:
```bash
# .env
CACHE_REFRESH_SECONDS=3600  # 1 hour
```

Then use `/refresh` command when you upload demo documents.

### Tip 2: Check Cache Before Important Queries
```
/info                       # See cache status
/refresh                    # Refresh if needed
Ask your question
```

### Tip 3: Monitor Logs
Watch terminal for cache refresh messages:
```
2025-10-19 21:25:00 - Cache refresh triggered (last refresh: 120s ago)
2025-10-19 21:25:02 - Vector store cache refreshed successfully
```

---

## 🎉 Quick Start Example

```bash
# 1. Start backend (if not running)
cd backend && uvicorn main:app --reload &

# 2. Start chatbot
cd chatbot && ./start-chatbot.sh

# 3. Open browser
open http://localhost:8001

# 4. Chat!
/info                                    # Check status
What documents are available?            # Ask a question
/collections                             # See collections
/refresh                                 # Force refresh
```

---

**That's it! You're ready to use the VectorDB Chatbot! 🚀**

