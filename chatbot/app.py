"""
Production-Grade RAG Chatbot with Chainlit UI
Built with Python 3.12 and industry best practices for accurate retrieval
"""

import chainlit as cl
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
import os
from typing import Optional, List, Dict, Any, Tuple
import logging
from datetime import datetime

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import LLM providers
try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None
    logger.warning("Groq not available. Install with: pip install langchain-groq")

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None
    logger.warning("Google Gemini not available. Install with: pip install langchain-google-genai")

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None
    logger.warning("OpenAI not available. Install with: pip install langchain-openai")


# ============================================================================
# CONFIGURATION
# ============================================================================

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "../backend/chroma_db")
DEFAULT_COLLECTION = os.getenv("DEFAULT_COLLECTION", None)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
MODEL_NAME = os.getenv("MODEL_NAME", "mixtral-8x7b-32768")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))  # Lower temperature for more accurate, factual responses
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))

# RAG Configuration - Optimized for accuracy
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "10"))  # Number of chunks to retrieve
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "5"))  # Top K after re-ranking
MIN_SIMILARITY_SCORE = float(os.getenv("MIN_SIMILARITY_SCORE", "0.3"))  # Minimum similarity threshold
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "true").lower() == "true"
ENABLE_QUERY_REWRITE = os.getenv("ENABLE_QUERY_REWRITE", "true").lower() == "true"

# Cache configuration
CACHE_AUTO_REFRESH_ENABLED = os.getenv("CACHE_AUTO_REFRESH", "false").lower() == "true"
CACHE_REFRESH_INTERVAL = int(os.getenv("CACHE_REFRESH_SECONDS", "120"))


# ============================================================================
# EMBEDDING MODEL - Must match backend
# ============================================================================

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ============================================================================
# LLM INITIALIZATION
# ============================================================================

def get_llm(provider: str = None):
    """Get LLM instance based on provider"""
    provider = provider or LLM_PROVIDER
    
    if provider == "groq":
        if not ChatGroq:
            raise ValueError("Groq not installed. Run: pip install langchain-groq")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        return ChatGroq(
            groq_api_key=api_key,
            model_name=MODEL_NAME,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            timeout=30.0  # 30 second timeout
        )
    
    elif provider == "gemini":
        if not ChatGoogleGenerativeAI:
            raise ValueError("Google Gemini not installed. Run: pip install langchain-google-genai")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        model = os.getenv("MODEL_NAME", "gemini-pro")
        return ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=model,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS
        )
    
    elif provider == "openai":
        if not ChatOpenAI:
            raise ValueError("OpenAI not installed. Run: pip install langchain-openai")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        model = os.getenv("MODEL_NAME", "gpt-4-turbo-preview")
        return ChatOpenAI(
            openai_api_key=api_key,
            model_name=model,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            timeout=30.0
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


# ============================================================================
# VECTOR STORE INITIALIZATION
# ============================================================================

def get_vectorstore(collection_name: Optional[str] = None, force_fresh: bool = True):
    """
    Initialize ChromaDB vector store with fresh connection
    
    Args:
        collection_name: Name of collection to load
        force_fresh: If True, creates a fresh ChromaDB client connection
    """
    try:
        import chromadb
        
        # Use HuggingFace embeddings (must match backend)
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}  # Normalize for better cosine similarity
        )
        
        if force_fresh:
            # Create a fresh ChromaDB client to avoid caching issues
            client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            
            if collection_name:
                vectorstore = Chroma(
                    client=client,
                    collection_name=collection_name,
                    embedding_function=embeddings
                )
            else:
                # Use first available collection or default
                collections = client.list_collections()
                if collections:
                    first_collection_name = collections[0].name
                    vectorstore = Chroma(
                        client=client,
                        collection_name=first_collection_name,
                        embedding_function=embeddings
                    )
                    logger.info(f"Using first available collection: {first_collection_name}")
                else:
                    # Fallback to default
                    vectorstore = Chroma(
                        client=client,
                        embedding_function=embeddings
                    )
        else:
            # Use LangChain's default connection
            if collection_name:
                vectorstore = Chroma(
                    collection_name=collection_name,
                    embedding_function=embeddings,
                    persist_directory=CHROMA_DB_PATH
                )
            else:
                vectorstore = Chroma(
                    embedding_function=embeddings,
                    persist_directory=CHROMA_DB_PATH
                )
        
        logger.info(f"Loaded vector store from {CHROMA_DB_PATH} (collection: {collection_name or 'default'})")
        return vectorstore
    except Exception as e:
        logger.error(f"Error loading vector store: {str(e)}", exc_info=True)
        raise


# ============================================================================
# QUERY OPTIMIZATION
# ============================================================================

async def rewrite_query_for_retrieval(original_query: str, llm) -> str:
    """
    Rewrite user query to be more effective for retrieval.
    Expands queries with synonyms and related terms.
    """
    if not ENABLE_QUERY_REWRITE:
        return original_query
    
    try:
        rewrite_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a query optimization expert. Rewrite the user's question to be more effective 
for semantic search in a document database. Make the query:
1. More specific and detailed
2. Include key terms and concepts
3. Preserve the original intent
4. Add relevant synonyms or related terms where helpful

Return ONLY the rewritten query, nothing else."""),
            ("human", "{query}")
        ])
        
        rewrite_chain = rewrite_prompt | llm | StrOutputParser()
        rewritten = await cl.make_async(rewrite_chain.invoke)({"query": original_query})
        
        logger.info(f"Query rewritten: '{original_query}' -> '{rewritten}'")
        return rewritten.strip()
    except Exception as e:
        logger.warning(f"Query rewrite failed: {str(e)}, using original query")
        return original_query


# ============================================================================
# ADVANCED RETRIEVAL
# ============================================================================

def filter_documents_by_score(documents: List[Document], min_score: float = MIN_SIMILARITY_SCORE) -> List[Document]:
    """Filter documents by similarity score"""
    filtered = []
    for doc in documents:
        # Check if document has a score in metadata
        score = doc.metadata.get("score", 1.0)
        if score >= min_score:
            filtered.append(doc)
    return filtered


def rerank_documents(documents: List[Document], query: str) -> List[Document]:
    """
    Simple re-ranking based on query term frequency and document metadata.
    In production, you might use a dedicated re-ranker model like Cohere Rerank.
    """
    if not ENABLE_RERANKING or not documents:
        return documents[:RERANK_TOP_K]
    
    # Score documents based on query term frequency and metadata relevance
    query_terms = set(query.lower().split())
    
    scored_docs = []
    for doc in documents:
        content_lower = doc.page_content.lower()
        score = doc.metadata.get("score", 0.5)
        
        # Boost score based on query term matches
        term_matches = sum(1 for term in query_terms if term in content_lower)
        term_score = term_matches / len(query_terms) if query_terms else 0
        
        # Combine similarity score with term match score
        final_score = (score * 0.7) + (term_score * 0.3)
        
        scored_docs.append((final_score, doc))
    
    # Sort by score and return top K
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    return [doc for score, doc in scored_docs[:RERANK_TOP_K]]


def format_context_with_metadata(docs: List[Document]) -> str:
    """Format retrieved documents with metadata for better context"""
    if not docs:
        return "No relevant documents found."
    
    formatted_parts = []
    for i, doc in enumerate(docs, 1):
        metadata = doc.metadata
        doc_name = metadata.get("name", "Unknown Document")
        version = metadata.get("version", "")
        version_str = f" (v{version})" if version else ""
        
        # Include document name in context for better citation
        context = f"[Document {i}: {doc_name}{version_str}]\n{doc.page_content}"
        formatted_parts.append(context)
    
    return "\n\n---\n\n".join(formatted_parts)


# ============================================================================
# RAG CHAIN CONSTRUCTION
# ============================================================================

def create_advanced_qa_chain(vectorstore, llm):
    """
    Create an advanced RAG chain with query rewriting, retrieval, and re-ranking
    """
    
    # Advanced prompt template optimized for accuracy and citation
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert assistant that provides accurate, detailed answers based on the given context from documents.

Your responses must:
1. Be based ONLY on the information provided in the context
2. Quote specific sections from the context to support your answers
3. Cite the document name when referencing information (e.g., "According to [Document 1: filename.pdf]...")
4. If the context doesn't fully answer the question, clearly state what information is missing
5. If you're uncertain, say so rather than guessing
6. Be specific and detailed - avoid vague or generic responses
7. If multiple documents contain relevant information, synthesize the information coherently

CONTEXT FROM DOCUMENTS:
{context}

QUESTION: {question}

Provide a comprehensive answer based on the context above. Include citations to document names where applicable."""),
        ("human", "{question}")
    ])
    
    # Create retriever with similarity search
    # Note: ChromaDB doesn't support score_threshold in search_kwargs
    # We'll filter by score after retrieval
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": RETRIEVAL_K  # Retrieve more chunks initially
        }
    )
    
    # Define retrieval and processing pipeline
    def retrieve_and_process(query: str) -> Dict[str, Any]:
        """Retrieve documents and process them"""
        # Use similarity_search_with_score to get actual similarity scores
        # ChromaDB uses distance (lower is better), convert to similarity score
        results_with_scores = vectorstore.similarity_search_with_score(query, k=RETRIEVAL_K)
        
        # Convert to Document objects with scores in metadata
        docs = []
        for doc, distance in results_with_scores:
            # Convert distance to similarity score (1 - distance for cosine similarity)
            # ChromaDB uses cosine distance, so similarity = 1 - distance
            similarity_score = max(0.0, 1.0 - distance)  # Ensure non-negative
            doc.metadata["score"] = similarity_score
            docs.append(doc)
        
        # Filter by score
        filtered_docs = filter_documents_by_score(docs, MIN_SIMILARITY_SCORE)
        
        # Re-rank for better relevance
        reranked_docs = rerank_documents(filtered_docs, query)
        
        # Format context
        formatted_context = format_context_with_metadata(reranked_docs)
        
        return {
            "context": formatted_context,
            "question": query,
            "source_documents": reranked_docs
        }
    
    # Create the chain
    qa_chain = (
        RunnablePassthrough()
        | retrieve_and_process
        | {
            "context": lambda x: x["context"],
            "question": lambda x: x["question"],
            "source_documents": lambda x: x["source_documents"]
        }
        | {
            "answer": prompt | llm | StrOutputParser(),
            "source_documents": lambda x: x["source_documents"]
        }
    )
    
    return qa_chain, retriever


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def should_refresh_cache() -> bool:
    """Check if the vector store cache should be refreshed"""
    if not CACHE_AUTO_REFRESH_ENABLED:
        return False
    
    last_refresh = cl.user_session.get("last_cache_refresh")
    if last_refresh is None:
        return False
    
    time_since_refresh = datetime.now() - last_refresh
    should_refresh = time_since_refresh.total_seconds() >= CACHE_REFRESH_INTERVAL
    
    if should_refresh:
        logger.info(f"Auto-refresh triggered (last refresh: {time_since_refresh.total_seconds():.0f}s ago)")
    
    return should_refresh


async def refresh_vectorstore_if_needed():
    """Refresh the vector store cache if needed"""
    if not should_refresh_cache():
        return False
    
    try:
        current_collection = cl.user_session.get("current_collection")
        llm = cl.user_session.get("llm")
        
        logger.info(f"Refreshing vector store cache for collection: {current_collection}")
        
        # Reload vector store with fresh data
        vectorstore = get_vectorstore(
            current_collection if current_collection != "default" else None,
            force_fresh=True
        )
        qa_chain, retriever = create_advanced_qa_chain(vectorstore, llm)
        
        # Update session
        cl.user_session.set("qa_chain", qa_chain)
        cl.user_session.set("retriever", retriever)
        cl.user_session.set("vectorstore", vectorstore)
        cl.user_session.set("last_cache_refresh", datetime.now())
        
        logger.info("Vector store cache refreshed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error refreshing vector store cache: {str(e)}", exc_info=True)
        return False


# ============================================================================
# CHAINLIT HANDLERS
# ============================================================================

@cl.on_chat_start
async def start():
    """Initialize chatbot on start"""
    
    # Welcome message
    welcome_message = """# 🤖 Production-Grade RAG Chatbot

Welcome! I'm an advanced RAG chatbot that provides accurate answers based on your documents.

## Features:
- **Advanced Retrieval**: Semantic search with query optimization and re-ranking
- **Accurate Answers**: Low-temperature responses with source citations
- **Smart Caching**: Automatic cache refresh for latest documents
- **Multi-Collection Support**: Switch between document collections

## Commands:
- `/info` - Show current configuration
- `/collections` - List available collections
- `/switch <name>` - Switch to a different collection
- `/refresh` - Manually refresh document cache

Ask me anything about your documents!"""
    
    await cl.Message(content=welcome_message).send()
    
    try:
        # Initialize LLM
        await cl.Message(content=f"🔄 Initializing {LLM_PROVIDER.upper()} LLM...").send()
        llm = get_llm()
        
        # Initialize vector store
        collection_msg = f" (Collection: {DEFAULT_COLLECTION})" if DEFAULT_COLLECTION else ""
        await cl.Message(content=f"🔄 Loading VectorDB{collection_msg}...").send()
        vectorstore = get_vectorstore(DEFAULT_COLLECTION)
        
        # Create QA chain
        qa_chain, retriever = create_advanced_qa_chain(vectorstore, llm)
        
        # Store in user session
        cl.user_session.set("qa_chain", qa_chain)
        cl.user_session.set("retriever", retriever)
        cl.user_session.set("vectorstore", vectorstore)
        cl.user_session.set("llm", llm)
        cl.user_session.set("current_collection", DEFAULT_COLLECTION or "default")
        cl.user_session.set("last_cache_refresh", datetime.now())
        
        # Check document count
        try:
            doc_count = vectorstore._collection.count()
        except:
            doc_count = 0
        
        # Configuration info
        ready_message = f"""✅ **Ready!**

**Configuration:**
- **LLM Provider:** {LLM_PROVIDER.upper()}
- **Model:** {MODEL_NAME}
- **Collection:** {cl.user_session.get('current_collection')}
- **Temperature:** {TEMPERATURE} (optimized for accuracy)
- **Retrieval:** Top {RETRIEVAL_K} chunks, re-ranked to {RERANK_TOP_K}
- **Documents:** {doc_count} in collection

"""
        
        if CACHE_AUTO_REFRESH_ENABLED:
            refresh_interval_mins = CACHE_REFRESH_INTERVAL / 60
            ready_message += f"🔄 *Auto-refresh: Every {refresh_interval_mins:.0f} minutes*\n\n"
        else:
            ready_message += f"🔄 *Manual refresh mode* (say 'refresh' to reload)\n\n"
        
        if doc_count == 0:
            ready_message += "⚠️ **Collection is empty!** Please upload documents using the main UI.\n\n"
            ready_message += "💡 Use `/collections` to see other collections."
        else:
            ready_message += "💬 Ask me anything about your documents!"
        
        await cl.Message(content=ready_message).send()
        
    except Exception as e:
        error_msg = f"""❌ **Error initializing chatbot**

**Error:** {str(e)}

**Troubleshooting:**
1. Verify VectorDB is running and contains documents
2. Check API keys are set in environment variables
3. Verify CHROMA_DB_PATH: `{CHROMA_DB_PATH}`
4. Check logs for detailed error information"""
        
        await cl.Message(content=error_msg).send()
        logger.error(f"Initialization error: {str(e)}", exc_info=True)


@cl.on_message
async def main(message: cl.Message):
    """Handle user messages with advanced RAG pipeline"""
    
    user_message = message.content.strip()
    user_message_lower = user_message.lower()
    
    # Handle special commands
    if user_message.startswith("/"):
        await handle_command(user_message)
        return
    
    # Handle natural language refresh command
    if user_message_lower in ["refresh", "reload", "refresh cache", "reload cache", "update"]:
        await handle_command("/refresh")
        return
    
    # Get QA chain from session
    qa_chain = cl.user_session.get("qa_chain")
    retriever = cl.user_session.get("retriever")
    llm = cl.user_session.get("llm")
    
    if not qa_chain or not llm:
        await cl.Message(
            content="❌ Chatbot not initialized. Please refresh the page."
        ).send()
        return
    
    # Show thinking message
    thinking_msg = cl.Message(content="🤔 Processing your question...")
    await thinking_msg.send()
    
    try:
        # Check if we need to refresh the cache
        cache_refreshed = await refresh_vectorstore_if_needed()
        
        # Get updated components if cache was refreshed
        if cache_refreshed:
            qa_chain = cl.user_session.get("qa_chain")
            retriever = cl.user_session.get("retriever")
            thinking_msg.content = "🔄 Cache refreshed! Processing your question..."
            await thinking_msg.update()
        
        # Check if collection is empty
        vectorstore = cl.user_session.get("vectorstore")
        try:
            doc_count = vectorstore._collection.count() if vectorstore else 0
        except:
            doc_count = 0
        
        if doc_count == 0:
            thinking_msg.content = """📭 **No documents found in the current collection.**

Please upload documents using the main UI, then try again.

💡 Use `/collections` to see other available collections."""
            await thinking_msg.update()
            return
        
        # Step 1: Query rewriting for better retrieval
        if ENABLE_QUERY_REWRITE:
            thinking_msg.content = "🔍 Optimizing query for better retrieval..."
            await thinking_msg.update()
            optimized_query = await rewrite_query_for_retrieval(user_message, llm)
        else:
            optimized_query = user_message
        
        # Step 2: Retrieve and process
        thinking_msg.content = "📚 Retrieving relevant documents..."
        await thinking_msg.update()
        
        # Use the QA chain to get answer
        result = await cl.make_async(qa_chain.invoke)(optimized_query)
        
        answer = result.get("answer", "I couldn't generate an answer.")
        source_documents = result.get("source_documents", [])
        
        # Format response with sources
        response_text = f"{answer}\n\n"
        
        # Add sources section
        if source_documents:
            response_text += "---\n\n**📚 Sources:**\n\n"
            seen_docs = set()
            for i, doc in enumerate(source_documents[:5], 1):  # Show top 5 sources
                metadata = doc.metadata
                doc_name = metadata.get("name", "Unknown")
                version = metadata.get("version", "")
                doc_id = f"{doc_name}_{version}"
                
                # Avoid duplicate source entries
                if doc_id in seen_docs:
                    continue
                seen_docs.add(doc_id)
                
                version_str = f" (v{version})" if version else ""
                score = metadata.get("score", 0.0)
                
                response_text += f"{i}. **{doc_name}**{version_str}"
                if score > 0:
                    response_text += f" (Relevance: {score:.2f})"
                response_text += "\n"
                
                # Add snippet
                snippet = doc.page_content[:200].strip()
                if len(doc.page_content) > 200:
                    snippet += "..."
                response_text += f"   > {snippet}\n\n"
        
        # Update the thinking message with the response
        thinking_msg.content = response_text
        await thinking_msg.update()
        
    except Exception as e:
        error_msg = f"""❌ **Error processing your question**

**Error:** {str(e)}

Please try:
- Rephrasing your question
- Checking if relevant documents are in the collection
- Using `/refresh` to reload documents

Check logs for detailed error information."""
        
        thinking_msg.content = error_msg
        await thinking_msg.update()
        logger.error(f"Query error: {str(e)}", exc_info=True)


async def handle_command(command: str):
    """Handle special commands"""
    
    if command == "/info":
        current_collection = cl.user_session.get("current_collection", "Unknown")
        last_refresh = cl.user_session.get("last_cache_refresh")
        
        if CACHE_AUTO_REFRESH_ENABLED:
            if last_refresh:
                time_since_refresh = datetime.now() - last_refresh
                seconds_ago = int(time_since_refresh.total_seconds())
                time_until_next = CACHE_REFRESH_INTERVAL - seconds_ago
                refresh_status = f"Auto-refresh enabled | Last: {seconds_ago}s ago | Next: {time_until_next}s"
            else:
                refresh_status = f"Auto-refresh enabled | Every {CACHE_REFRESH_INTERVAL}s"
        else:
            if last_refresh:
                time_since_refresh = datetime.now() - last_refresh
                seconds_ago = int(time_since_refresh.total_seconds())
                refresh_status = f"Manual mode | Last refresh: {seconds_ago}s ago"
            else:
                refresh_status = "Manual mode | Say 'refresh' to reload"
        
        info_text = f"""**⚙️ Current Configuration:**

**LLM Settings:**
- Provider: {LLM_PROVIDER.upper()}
- Model: {MODEL_NAME}
- Temperature: {TEMPERATURE} (low for accuracy)
- Max Tokens: {MAX_TOKENS}

**Retrieval Settings:**
- Collection: {current_collection}
- Retrieval K: {RETRIEVAL_K} chunks
- Re-ranked to: {RERANK_TOP_K} chunks
- Min Similarity: {MIN_SIMILARITY_SCORE}
- Query Rewriting: {'Enabled' if ENABLE_QUERY_REWRITE else 'Disabled'}
- Re-ranking: {'Enabled' if ENABLE_RERANKING else 'Disabled'}

**Database:**
- Path: {CHROMA_DB_PATH}
- Embedding Model: {EMBEDDING_MODEL}

**Cache:**
- Status: {refresh_status}
"""
        await cl.Message(content=info_text).send()
    
    elif command == "/collections":
        try:
            import chromadb
            client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            collections = client.list_collections()
            
            if not collections:
                await cl.Message(content="📭 No collections found in VectorDB.").send()
                return
            
            collections_text = "**📚 Available Collections:**\n\n"
            for col in collections:
                doc_count = col.count()
                collections_text += f"- **{col.name}** ({doc_count} documents)\n"
            
            collections_text += f"\n💡 Use `/switch <collection_name>` to switch collections"
            
            await cl.Message(content=collections_text).send()
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error listing collections: {str(e)}"
            ).send()
            logger.error(f"Error listing collections: {str(e)}", exc_info=True)
    
    elif command.startswith("/switch "):
        collection_name = command.replace("/switch ", "").strip()
        
        try:
            llm = cl.user_session.get("llm")
            if not llm:
                await cl.Message(content="❌ LLM not initialized. Please refresh the page.").send()
                return
            
            # Reload vector store with new collection
            vectorstore = get_vectorstore(collection_name, force_fresh=True)
            qa_chain, retriever = create_advanced_qa_chain(vectorstore, llm)
            
            # Get document count
            try:
                doc_count = vectorstore._collection.count()
            except:
                doc_count = 0
            
            # Update session
            cl.user_session.set("qa_chain", qa_chain)
            cl.user_session.set("retriever", retriever)
            cl.user_session.set("vectorstore", vectorstore)
            cl.user_session.set("current_collection", collection_name)
            cl.user_session.set("last_cache_refresh", datetime.now())
            
            await cl.Message(
                content=f"✅ **Switched to collection:** `{collection_name}`\n\n📊 {doc_count} documents loaded\n🔄 Cache refreshed with latest data"
            ).send()
            
            logger.info(f"Switched to collection '{collection_name}' with {doc_count} documents")
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error switching collection: {str(e)}"
            ).send()
            logger.error(f"Error switching to collection '{collection_name}': {str(e)}", exc_info=True)
    
    elif command == "/refresh":
        try:
            current_collection = cl.user_session.get("current_collection")
            llm = cl.user_session.get("llm")
            
            if not llm:
                await cl.Message(content="❌ LLM not initialized. Please refresh the page.").send()
                return
            
            msg = await cl.Message(content="🔄 Manually refreshing cache...").send()
            
            # Get old count
            old_vectorstore = cl.user_session.get("vectorstore")
            try:
                old_count = old_vectorstore._collection.count() if old_vectorstore else 0
            except:
                old_count = 0
            
            # Force fresh connection
            vectorstore = get_vectorstore(
                current_collection if current_collection != "default" else None,
                force_fresh=True
            )
            qa_chain, retriever = create_advanced_qa_chain(vectorstore, llm)
            
            # Get new count
            try:
                new_count = vectorstore._collection.count()
            except:
                new_count = 0
            
            cl.user_session.set("qa_chain", qa_chain)
            cl.user_session.set("retriever", retriever)
            cl.user_session.set("vectorstore", vectorstore)
            cl.user_session.set("last_cache_refresh", datetime.now())
            
            if new_count != old_count:
                msg.content = f"✅ **Cache manually refreshed!**\n\n📊 Documents: {old_count} → **{new_count}** ({new_count - old_count:+d} change)\n\nNow querying latest documents."
                await msg.update()
                logger.info(f"Manual refresh: Document count changed {old_count} → {new_count}")
            else:
                msg.content = f"✅ **Cache manually refreshed!**\n\n📊 {new_count} documents loaded\n\nNow querying latest documents."
                await msg.update()
                logger.info(f"Manual refresh: Document count unchanged at {new_count}")
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error refreshing cache: {str(e)}"
            ).send()
            logger.error(f"Manual refresh error: {str(e)}", exc_info=True)
    
    else:
        help_text = """**Available Commands:**

- `/info` - Show current configuration and settings
- `/collections` - List available collections
- `/switch <name>` - Switch to a different collection
- `/refresh` - Manually refresh document cache

💡 Just type your question to chat with the documents!"""
        
        await cl.Message(content=help_text).send()


if __name__ == "__main__":
    # This is for running with: chainlit run app.py
    pass
