"""
Migration script to migrate all collections from old embedding model to new one.
This script will:
1. Detect collections with old embedding model (384 dimensions)
2. Read all documents and chunks
3. Re-embed with new model (768 dimensions)
4. Create new collections or replace old ones
"""

import chromadb
from chromadb.utils import embedding_functions
import logging
from typing import Dict, List, Any
import uuid
from datetime import datetime
import sys
import os

# Add parent directory to path to import utils if needed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Old embedding model (384 dimensions)
OLD_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
OLD_EMBEDDING_DIM = 384

# New embedding model (768 dimensions)
NEW_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
NEW_EMBEDDING_DIM = 768

def get_collection_embedding_dimension(collection) -> int:
    """Get the embedding dimension of a collection"""
    try:
        sample = collection.get(limit=1, include=["embeddings"])
        if sample["ids"] and sample["embeddings"]:
            return len(sample["embeddings"][0])
        return 0
    except Exception as e:
        logger.warning(f"Could not determine embedding dimension: {str(e)}")
        return 0

def migrate_collection(
    old_collection,
    new_collection_name: str,
    old_embedding_func,
    new_embedding_func,
    chroma_client,
    backup_suffix: str = "_old"
) -> Dict[str, Any]:
    """
    Migrate a collection from old to new embedding model
    
    Returns:
        Migration result with statistics
    """
    logger.info(f"Starting migration of collection: {old_collection.name}")
    
    # Get all items from old collection
    all_items = old_collection.get(include=["documents", "metadatas", "ids"])
    
    if not all_items["ids"]:
        logger.warning(f"Collection '{old_collection.name}' is empty, skipping")
        return {
            "collection_name": old_collection.name,
            "status": "skipped",
            "reason": "empty collection"
        }
    
    total_items = len(all_items["ids"])
    logger.info(f"Found {total_items} items to migrate")
    
    # Create new collection with new embedding function
    try:
        # Check if target collection already exists with correct dimension
        existing_col = chroma_client.get_collection(name=new_collection_name)
        sample = existing_col.get(limit=1, include=["embeddings"])
        if sample["ids"] and sample["embeddings"]:
            existing_dim = len(sample["embeddings"][0])
            if existing_dim == NEW_EMBEDDING_DIM:
                logger.info(f"Collection '{new_collection_name}' already exists with new model, appending to it")
                new_collection = existing_col
            else:
                # Wrong dimension, create with different name
                raise ValueError(f"Collection exists but has wrong dimension: {existing_dim}")
        else:
            # Empty collection, use it
            new_collection = existing_col
            logger.info(f"Using existing empty collection: {new_collection_name}")
    except Exception:
        # Collection doesn't exist, create new one
        new_collection = chroma_client.create_collection(
            name=new_collection_name,
            metadata={
                **old_collection.metadata,
                "migrated_from": old_collection.name,
                "migration_date": datetime.utcnow().isoformat(),
                "embedding_model": NEW_EMBEDDING_MODEL,
                "embedding_dimension": NEW_EMBEDDING_DIM
            },
            embedding_function=new_embedding_func
        )
        logger.info(f"Created new collection: {new_collection_name}")
    
    # Separate documents and chunks
    documents = []
    chunks = []
    
    for i, item_id in enumerate(all_items["ids"]):
        metadata = all_items["metadatas"][i] if all_items["metadatas"] else {}
        document = all_items["documents"][i] if all_items["documents"] else ""
        is_chunk = metadata.get("is_chunk", False)
        
        if is_chunk:
            chunks.append({
                "id": item_id,
                "content": document,
                "metadata": metadata
            })
        else:
            documents.append({
                "id": item_id,
                "content": document,
                "metadata": metadata
            })
    
    logger.info(f"Found {len(documents)} documents and {len(chunks)} chunks")
    
    # Migrate documents
    migrated_docs = 0
    migrated_chunks = 0
    errors = []
    
    # Migrate documents in batches
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        try:
            ids = [item["id"] for item in batch]
            contents = [item["content"] for item in batch]
            metadatas = [item["metadata"] for item in batch]
            
            # Add to new collection (will use new embedding function automatically)
            new_collection.add(
                ids=ids,
                documents=contents,
                metadatas=metadatas
            )
            migrated_docs += len(batch)
            logger.info(f"Migrated {migrated_docs}/{len(documents)} documents")
        except Exception as e:
            error_msg = f"Error migrating documents batch {i//batch_size + 1}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
    
    # Migrate chunks in batches
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        try:
            ids = [item["id"] for item in batch]
            contents = [item["content"] for item in batch]
            metadatas = [item["metadata"] for item in batch]
            
            # Add to new collection
            new_collection.add(
                ids=ids,
                documents=contents,
                metadatas=metadatas
            )
            migrated_chunks += len(batch)
            logger.info(f"Migrated {migrated_chunks}/{len(chunks)} chunks")
        except Exception as e:
            error_msg = f"Error migrating chunks batch {i//batch_size + 1}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)
    
    result = {
        "collection_name": old_collection.name,
        "new_collection_name": new_collection_name,
        "status": "completed" if not errors else "completed_with_errors",
        "total_items": total_items,
        "migrated_documents": migrated_docs,
        "migrated_chunks": migrated_chunks,
        "errors": errors
    }
    
    logger.info(f"Migration completed for {old_collection.name}: {migrated_docs} docs, {migrated_chunks} chunks")
    
    result["new_collection_name"] = new_collection.name
    result["note"] = f"Migrated to '{new_collection.name}'. Original collection '{old_collection.name}' still exists and can be deleted after verification."
    
    return result

def migrate_all_collections(
    chroma_db_path: str = "./chroma_db",
    backup_old: bool = True,
    delete_old: bool = False
) -> Dict[str, Any]:
    """
    Migrate all collections from old to new embedding model
    
    Args:
        chroma_db_path: Path to ChromaDB database
        backup_old: Whether to rename old collections with _old suffix
        delete_old: Whether to delete old collections after migration (only if backup_old is True)
    
    Returns:
        Migration results for all collections
    """
    logger.info("Starting migration of all collections")
    
    # Initialize ChromaDB client
    chroma_client = chromadb.PersistentClient(path=chroma_db_path)
    
    # Initialize embedding functions
    old_embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=OLD_EMBEDDING_MODEL
    )
    new_embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=NEW_EMBEDDING_MODEL
    )
    
    # Get all collections
    all_collections = chroma_client.list_collections()
    logger.info(f"Found {len(all_collections)} collections")
    
    # Identify collections that need migration
    collections_to_migrate = []
    collections_ok = []
    
    for collection in all_collections:
        try:
            # Try to get collection with old embedding function first
            old_col = chroma_client.get_collection(
                name=collection.name,
                embedding_function=old_embedding_func
            )
            dim = get_collection_embedding_dimension(old_col)
            
            if dim == OLD_EMBEDDING_DIM:
                collections_to_migrate.append(old_col)
                logger.info(f"Collection '{collection.name}' needs migration (dimension: {dim})")
            elif dim == NEW_EMBEDDING_DIM:
                collections_ok.append(collection.name)
                logger.info(f"Collection '{collection.name}' already uses new model (dimension: {dim})")
            else:
                logger.warning(f"Collection '{collection.name}' has unknown dimension: {dim}")
        except Exception as e:
            # Try without embedding function
            try:
                col = chroma_client.get_collection(name=collection.name)
                dim = get_collection_embedding_dimension(col)
                
                if dim == OLD_EMBEDDING_DIM:
                    collections_to_migrate.append(col)
                    logger.info(f"Collection '{collection.name}' needs migration (dimension: {dim})")
                elif dim == NEW_EMBEDDING_DIM:
                    collections_ok.append(collection.name)
                    logger.info(f"Collection '{collection.name}' already uses new model (dimension: {dim})")
                else:
                    logger.warning(f"Collection '{collection.name}' has unknown dimension: {dim}")
            except Exception as e2:
                logger.error(f"Could not access collection '{collection.name}': {str(e2)}")
    
    logger.info(f"Collections to migrate: {len(collections_to_migrate)}")
    logger.info(f"Collections already migrated: {len(collections_ok)}")
    
    # Migrate each collection
    migration_results = []
    
    for old_collection in collections_to_migrate:
        try:
            # Determine new collection name
            # Strategy: Create new collection with _v2 suffix, then user can delete old one
            new_collection_name = f"{old_collection.name}_v2"
            
            # Check if _v2 collection already exists
            version = 2
            while True:
                try:
                    chroma_client.get_collection(name=new_collection_name)
                    # Exists, try next version
                    version += 1
                    new_collection_name = f"{old_collection.name}_v{version}"
                except:
                    # Name is available
                    break
            
            logger.info(f"Migrating '{old_collection.name}' to '{new_collection_name}'")
            
            # Perform migration
            result = migrate_collection(
                old_collection=old_collection,
                new_collection_name=new_collection_name,
                old_embedding_func=old_embedding_func,
                new_embedding_func=new_embedding_func,
                chroma_client=chroma_client,
                backup_suffix="_old"
            )
            
            migration_results.append(result)
            
            # If not backing up, delete old collection after successful migration
            if delete_old and result.get("status") == "completed":
                try:
                    chroma_client.delete_collection(name=old_collection.name)
                    logger.info(f"Deleted old collection: {old_collection.name}")
                    result["old_collection_deleted"] = True
                except Exception as e:
                    logger.error(f"Could not delete old collection '{old_collection.name}': {str(e)}")
                    result["old_collection_deleted"] = False
                    result["delete_error"] = str(e)
                    
        except Exception as e:
            logger.error(f"Error migrating collection '{old_collection.name}': {str(e)}", exc_info=True)
            migration_results.append({
                "collection_name": old_collection.name,
                "status": "failed",
                "error": str(e)
            })
    
    summary = {
        "total_collections": len(all_collections),
        "collections_to_migrate": len(collections_to_migrate),
        "collections_already_migrated": len(collections_ok),
        "migration_results": migration_results,
        "collections_ok": collections_ok
    }
    
    logger.info("Migration summary:")
    logger.info(f"  Total collections: {summary['total_collections']}")
    logger.info(f"  Migrated: {len([r for r in migration_results if r.get('status') == 'completed'])}")
    logger.info(f"  Failed: {len([r for r in migration_results if r.get('status') == 'failed'])}")
    logger.info(f"  Already migrated: {len(collections_ok)}")
    
    return summary

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate collections to new embedding model")
    parser.add_argument("--path", default="./chroma_db", help="Path to ChromaDB database")
    parser.add_argument("--backup", action="store_true", help="Backup old collections (rename with _old suffix)")
    parser.add_argument("--delete-old", action="store_true", help="Delete old collections after migration (requires --backup)")
    
    args = parser.parse_args()
    
    if args.delete_old and not args.backup:
        print("Error: --delete-old requires --backup")
        exit(1)
    
    results = migrate_all_collections(
        chroma_db_path=args.path,
        backup_old=args.backup,
        delete_old=args.delete_old
    )
    
    print("\n" + "="*60)
    print("MIGRATION COMPLETE")
    print("="*60)
    print(f"Total collections: {results['total_collections']}")
    print(f"Collections migrated: {len([r for r in results['migration_results'] if r.get('status') == 'completed'])}")
    print(f"Collections failed: {len([r for r in results['migration_results'] if r.get('status') == 'failed'])}")
    print(f"Collections already migrated: {len(results['collections_ok'])}")
    print("\nDetailed results:")
    for result in results['migration_results']:
        print(f"  - {result['collection_name']}: {result.get('status', 'unknown')}")

