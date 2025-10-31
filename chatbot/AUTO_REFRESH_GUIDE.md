# Auto-Refresh Cache Feature

## Overview

The chatbot now **automatically refreshes its cache every 2 minutes** to ensure you're always querying the latest documents from ChromaDB. This means any documents you add, update, or delete in the main UI will be available in the chatbot within 2 minutes (or immediately with manual refresh).

---

## How It Works

### Automatic Refresh
- **Default interval:** 120 seconds (2 minutes)
- **Triggered:** Before each query, if cache is older than the interval
- **Transparent:** Happens automatically in the background
- **User notification:** Shows "🔄 Cache refreshed! Searching latest documents..." when triggered

### Smart Caching
The system balances performance with freshness:
1. **First load:** Loads vector store on startup
2. **Query time:** Checks if cache needs refresh
3. **If stale:** Reloads vector store with latest data
4. **If fresh:** Uses cached version (fast)

---

## Configuration

### Environment Variable
Control the refresh interval via `.env`:

```bash
# Refresh every 2 minutes (default)
CACHE_REFRESH_SECONDS=120

# Refresh every 30 seconds (more frequent, for active development)
CACHE_REFRESH_SECONDS=30

# Refresh every 5 minutes (less frequent, for stable environments)
CACHE_REFRESH_SECONDS=300
```

### How to Change
1. Edit `chatbot/.env`
2. Add or modify `CACHE_REFRESH_SECONDS=<seconds>`
3. Restart the chatbot

---

## User Commands

### `/info` - Check Cache Status
Shows when the cache was last refreshed and when it will refresh next:

```
⚙️ Current Configuration:
- Cache Refresh: Every 120s (2 min)
- Status: Last refresh: 45s ago | Next: 75s
```

### `/refresh` - Manual Refresh
Force an immediate cache refresh without waiting for the automatic interval:

```
/refresh
```

Response:
```
✅ Cache manually refreshed! Now querying latest documents.
```

**Use cases:**
- You just uploaded important documents
- You want immediate access to changes
- Testing after document updates

### `/switch <collection>` - Switch Collections
Automatically refreshes cache when switching to ensure you get the latest data:

```
/switch MyCollection
```

Response:
```
✅ Switched to collection: MyCollection
🔄 Cache refreshed with latest documents
```

---

## Example Workflow

### Scenario: Adding New Documents

**Step 1:** Upload documents via main UI
```bash
# In browser: Upload policy.pdf to VectorDB
```

**Step 2:** Query in chatbot (within 2 minutes)
```
User: What is our vacation policy?

Chatbot: 🔄 Cache refreshed! Searching latest documents...
[Automatically gets the new document and answers]
```

**Alternative:** Force immediate refresh
```
User: /refresh
Chatbot: ✅ Cache manually refreshed!

User: What is our vacation policy?
Chatbot: [Answers using the newly uploaded document]
```

---

## Performance Considerations

### Why Cache?
Loading embeddings is expensive (~2-3 seconds per collection). Caching prevents this overhead on every query.

### Why Refresh?
Without refreshing, the chatbot would miss new/updated/deleted documents until restart.

### Optimal Balance
**2 minutes** is optimal for most use cases:
- ✅ Fast queries (uses cache)
- ✅ Recent updates (auto-refresh)
- ✅ Low overhead (only refreshes when needed)

### Adjust for Your Needs

| Use Case | Recommended Interval | Setting |
|----------|---------------------|---------|
| Active development | 30-60 seconds | `CACHE_REFRESH_SECONDS=30` |
| Production (frequent updates) | 120 seconds (default) | `CACHE_REFRESH_SECONDS=120` |
| Production (stable docs) | 300-600 seconds | `CACHE_REFRESH_SECONDS=300` |
| Demo/testing | Use manual refresh | `/refresh` command |

---

## Technical Details

### What Gets Refreshed
- ✅ Vector store connection
- ✅ Document embeddings
- ✅ Retriever configuration
- ✅ QA chain with latest retriever

### What Persists
- ✅ LLM connection (no need to reconnect)
- ✅ User session
- ✅ Collection selection

### Cache Check Logic
```python
# Pseudo-code
if time_since_last_refresh >= CACHE_REFRESH_SECONDS:
    reload_vector_store()
    update_qa_chain()
    reset_timer()
```

### Logging
Check logs to see when refreshes happen:
```
2025-10-19 21:25:00 - Cache refresh triggered (last refresh: 120s ago)
2025-10-19 21:25:02 - Loaded vector store from ../backend/chroma_db (collection: default)
2025-10-19 21:25:02 - Vector store cache refreshed successfully
```

---

## Troubleshooting

### Cache Not Refreshing
**Check:**
1. Verify `CACHE_REFRESH_SECONDS` is set in `.env`
2. Check logs for refresh messages
3. Try manual refresh: `/refresh`

### Too Frequent Refreshes
**Solution:** Increase the interval
```bash
CACHE_REFRESH_SECONDS=300  # 5 minutes
```

### Need Immediate Updates
**Use manual refresh:**
```
/refresh
```

---

## Best Practices

### Development
```bash
# .env
CACHE_REFRESH_SECONDS=30  # Quick feedback
```

### Production
```bash
# .env  
CACHE_REFRESH_SECONDS=120  # Balanced
```

### Manual Control
If you prefer full control, set a high interval and use `/refresh`:
```bash
# .env
CACHE_REFRESH_SECONDS=3600  # 1 hour

# Then use /refresh command when needed
```

---

## Summary

| Feature | Benefit |
|---------|---------|
| **Auto-refresh** | Always query latest documents |
| **2-min default** | Perfect balance of speed and freshness |
| **Configurable** | Adjust via `CACHE_REFRESH_SECONDS` |
| **Manual override** | `/refresh` for immediate updates |
| **Cache status** | `/info` shows when next refresh |
| **Smart caching** | Only refreshes when needed |

**Result:** You get a fast chatbot that automatically stays in sync with your document updates! 🚀

