# API Usage Examples

This document provides example API calls for the VectorDB Manager API.

## Base URL
```
http://localhost:8000
```

## Collections API

### List all collections
```bash
curl -X GET "http://localhost:8000/collections"
```

Response:
```json
{
  "collections": [
    {
      "name": "my-knowledge-base",
      "id": "collection-id",
      "metadata": {
        "description": "My first collection"
      },
      "count": 5
    }
  ]
}
```

### Create a collection
```bash
curl -X POST "http://localhost:8000/collections" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-knowledge-base",
    "description": "My first collection",
    "metadata": {}
  }'
```

Response:
```json
{
  "name": "my-knowledge-base",
  "id": "collection-id",
  "metadata": {
    "description": "My first collection"
  },
  "message": "Collection created successfully"
}
```

### Delete a collection
```bash
curl -X DELETE "http://localhost:8000/collections/my-knowledge-base"
```

Response:
```json
{
  "message": "Collection 'my-knowledge-base' deleted successfully"
}
```

## Documents API

### List documents in a collection
```bash
curl -X GET "http://localhost:8000/collections/my-knowledge-base/documents?skip=0&limit=100"
```

Response:
```json
{
  "documents": [
    {
      "id": "doc-uuid",
      "collection_name": "my-knowledge-base",
      "metadata": {
        "name": "Sample Document",
        "purpose": "Testing",
        "tags": ["test", "sample"],
        "created_at": "2025-10-19T10:00:00",
        "updated_at": "2025-10-19T10:00:00"
      },
      "content": "This is the document content...",
      "created_at": "2025-10-19T10:00:00",
      "updated_at": "2025-10-19T10:00:00"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

### Get a specific document
```bash
curl -X GET "http://localhost:8000/collections/my-knowledge-base/documents/{document_id}"
```

Response:
```json
{
  "id": "doc-uuid",
  "collection_name": "my-knowledge-base",
  "metadata": {
    "name": "Sample Document",
    "purpose": "Testing",
    "tags": ["test", "sample"]
  },
  "content": "This is the document content...",
  "created_at": "2025-10-19T10:00:00",
  "updated_at": "2025-10-19T10:00:00"
}
```

### Create a document
```bash
curl -X POST "http://localhost:8000/collections/my-knowledge-base/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "my-knowledge-base",
    "metadata": {
      "name": "Sample Document",
      "purpose": "Testing the system",
      "tags": ["test", "sample"],
      "custom_metadata": {
        "author": "John Doe",
        "version": "1.0"
      }
    },
    "content": "This is a sample document for testing. It contains important information about the system."
  }'
```

Response:
```json
{
  "document_id": "doc-uuid",
  "task_id": "task-uuid",
  "message": "Document queued for processing",
  "status": "pending"
}
```

### Update a document
```bash
curl -X PUT "http://localhost:8000/collections/my-knowledge-base/documents/{document_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {
      "name": "Updated Document Name",
      "purpose": "Updated purpose",
      "tags": ["updated", "test"],
      "custom_metadata": {
        "author": "Jane Doe",
        "version": "2.0"
      }
    },
    "content": "This is the updated content of the document."
  }'
```

Response:
```json
{
  "document_id": "doc-uuid",
  "task_id": "task-uuid",
  "message": "Document update queued for processing",
  "status": "pending"
}
```

### Delete a document
```bash
curl -X DELETE "http://localhost:8000/collections/my-knowledge-base/documents/{document_id}"
```

Response:
```json
{
  "message": "Document 'doc-uuid' deleted successfully"
}
```

### Search documents
```bash
curl -X POST "http://localhost:8000/collections/my-knowledge-base/search?query=testing&n_results=5"
```

Response:
```json
{
  "query": "testing",
  "results": [
    {
      "id": "doc-uuid_chunk_0",
      "content": "This is a sample document for testing...",
      "metadata": {
        "name": "Sample Document",
        "purpose": "Testing",
        "chunk_index": 0,
        "parent_id": "doc-uuid"
      },
      "distance": 0.123
    }
  ],
  "count": 1
}
```

## Tasks API

### Get task status
```bash
curl -X GET "http://localhost:8000/tasks/{task_id}/status"
```

Response:
```json
{
  "task_id": "task-uuid",
  "status": "completed",
  "message": "Document processed successfully",
  "progress": 100,
  "created_at": "2025-10-19T10:00:00",
  "updated_at": "2025-10-19T10:00:05"
}
```

### List all tasks
```bash
curl -X GET "http://localhost:8000/tasks"
```

Response:
```json
{
  "tasks": [
    {
      "task_id": "task-uuid",
      "status": "completed",
      "message": "Document processed successfully",
      "progress": 100,
      "created_at": "2025-10-19T10:00:00",
      "updated_at": "2025-10-19T10:00:05"
    }
  ],
  "total": 1
}
```

### List tasks by status
```bash
curl -X GET "http://localhost:8000/tasks?status=processing"
```

## Health Check

### Check API health
```bash
curl -X GET "http://localhost:8000/health"
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-19T10:00:00"
}
```

### Get API info
```bash
curl -X GET "http://localhost:8000/"
```

Response:
```json
{
  "message": "VectorDB Management API",
  "version": "1.0.0",
  "status": "running"
}
```

## Python Examples

### Using Python requests library

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Create a collection
response = requests.post(
    f"{BASE_URL}/collections",
    json={
        "name": "my-collection",
        "description": "My test collection"
    }
)
print(response.json())

# Add a document
response = requests.post(
    f"{BASE_URL}/collections/my-collection/documents",
    json={
        "collection_name": "my-collection",
        "metadata": {
            "name": "Test Document",
            "purpose": "Testing",
            "tags": ["test"],
            "custom_metadata": {}
        },
        "content": "This is my test document content."
    }
)
task = response.json()
print(f"Task ID: {task['task_id']}")

# Check task status
task_id = task['task_id']
response = requests.get(f"{BASE_URL}/tasks/{task_id}/status")
print(response.json())

# List documents
response = requests.get(f"{BASE_URL}/collections/my-collection/documents")
documents = response.json()
print(f"Total documents: {documents['total']}")

# Search documents
response = requests.post(
    f"{BASE_URL}/collections/my-collection/search",
    params={"query": "test", "n_results": 5}
)
results = response.json()
print(f"Found {results['count']} results")
```

## JavaScript/TypeScript Examples

### Using fetch API

```javascript
const BASE_URL = 'http://localhost:8000';

// Create a collection
async function createCollection() {
  const response = await fetch(`${BASE_URL}/collections`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: 'my-collection',
      description: 'My test collection'
    })
  });
  const data = await response.json();
  console.log(data);
}

// Add a document
async function addDocument() {
  const response = await fetch(`${BASE_URL}/collections/my-collection/documents`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      collection_name: 'my-collection',
      metadata: {
        name: 'Test Document',
        purpose: 'Testing',
        tags: ['test'],
        custom_metadata: {}
      },
      content: 'This is my test document content.'
    })
  });
  const data = await response.json();
  console.log('Task ID:', data.task_id);
  return data.task_id;
}

// Check task status
async function checkTaskStatus(taskId) {
  const response = await fetch(`${BASE_URL}/tasks/${taskId}/status`);
  const data = await response.json();
  console.log(data);
  return data;
}

// List documents
async function listDocuments() {
  const response = await fetch(`${BASE_URL}/collections/my-collection/documents?skip=0&limit=100`);
  const data = await response.json();
  console.log('Total documents:', data.total);
  return data.documents;
}

// Search documents
async function searchDocuments(query) {
  const response = await fetch(
    `${BASE_URL}/collections/my-collection/search?query=${encodeURIComponent(query)}&n_results=5`,
    { method: 'POST' }
  );
  const data = await response.json();
  console.log('Found', data.count, 'results');
  return data.results;
}
```

## Error Handling

All endpoints return appropriate HTTP status codes:

- `200 OK`: Request successful
- `400 Bad Request`: Invalid request data
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

Error response format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

## Rate Limiting

Currently, there is no rate limiting implemented. Consider adding rate limiting for production use.

## Authentication

Currently, there is no authentication implemented. For production use, consider adding:
- JWT tokens
- API keys
- OAuth2

## Best Practices

1. **Always check task status** when creating or updating documents
2. **Use appropriate chunk sizes** for your use case
3. **Add meaningful metadata** to make documents searchable
4. **Use tags** for organization
5. **Monitor task status** for failed operations
6. **Handle errors gracefully** in your application
7. **Use connection pooling** for high-volume applications

## Pagination

For large document collections, use skip and limit parameters:
```bash
# Get documents 0-99
curl "http://localhost:8000/collections/my-collection/documents?skip=0&limit=100"

# Get documents 100-199
curl "http://localhost:8000/collections/my-collection/documents?skip=100&limit=100"
```

## Bulk Operations

For bulk document operations, consider creating a script that:
1. Creates documents in batches
2. Tracks task IDs
3. Polls for completion
4. Handles failures with retry logic

Example Python script for bulk upload:
```python
import requests
import time

BASE_URL = "http://localhost:8000"

def bulk_upload_documents(collection_name, documents):
    task_ids = []
    
    # Upload all documents
    for doc in documents:
        response = requests.post(
            f"{BASE_URL}/collections/{collection_name}/documents",
            json=doc
        )
        task = response.json()
        task_ids.append(task['task_id'])
        print(f"Uploaded: {doc['metadata']['name']} (Task: {task['task_id']})")
    
    # Wait for all to complete
    while task_ids:
        for task_id in task_ids[:]:
            response = requests.get(f"{BASE_URL}/tasks/{task_id}/status")
            status = response.json()
            
            if status['status'] in ['completed', 'failed']:
                print(f"Task {task_id}: {status['status']}")
                task_ids.remove(task_id)
        
        if task_ids:
            time.sleep(1)
    
    print("All documents processed!")

# Usage
documents = [
    {
        "collection_name": "my-collection",
        "metadata": {
            "name": f"Document {i}",
            "purpose": "Bulk upload test",
            "tags": ["bulk", "test"]
        },
        "content": f"Content for document {i}"
    }
    for i in range(10)
]

bulk_upload_documents("my-collection", documents)
```

