"""
VectorDB Chatbot - Standalone Chainlit Application
A RAG chatbot that queries documents stored in ChromaDB
"""

import chainlit as cl
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_community.embeddings import HuggingFaceEmbeddings
import os
from typing import Optional
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
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


# Configuration
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "../backend/chroma_db")
DEFAULT_COLLECTION = os.getenv("DEFAULT_COLLECTION", None)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # groq, gemini, openai
MODEL_NAME = os.getenv("MODEL_NAME", "mixtral-8x7b-32768")  # Default Groq model
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))

# Cache configuration
CACHE_AUTO_REFRESH_ENABLED = os.getenv("CACHE_AUTO_REFRESH", "false").lower() == "true"
CACHE_REFRESH_INTERVAL = int(os.getenv("CACHE_REFRESH_SECONDS", "120"))  # 2 minutes default (only used if auto-refresh enabled)


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
            max_tokens=MAX_TOKENS
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
        model = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
        return ChatOpenAI(
            openai_api_key=api_key,
            model_name=model,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def get_vectorstore(collection_name: Optional[str] = None, force_fresh: bool = True):
    """
    Initialize ChromaDB vector store with fresh connection
    
    Args:
        collection_name: Name of collection to load
        force_fresh: If True, creates a fresh ChromaDB client connection (default: True)
    """
    try:
        import chromadb
        
        # Use HuggingFace embeddings (same as ChromaDB default)
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        if force_fresh:
            # Create a fresh ChromaDB client to avoid caching issues
            # This ensures we get the latest data from disk
            client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
            
            if collection_name:
                # Get specific collection
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
            # Use LangChain's default connection (may cache)
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
        
        logger.info(f"Loaded vector store from {CHROMA_DB_PATH} (collection: {collection_name or 'default'}, fresh_client: {force_fresh})")
        return vectorstore
    except Exception as e:
        logger.error(f"Error loading vector store: {str(e)}")
        raise


def should_refresh_cache() -> bool:
    """Check if the vector store cache should be refreshed (only if auto-refresh enabled)"""
    if not CACHE_AUTO_REFRESH_ENABLED:
        return False  # Auto-refresh is disabled
    
    last_refresh = cl.user_session.get("last_cache_refresh")
    
    if last_refresh is None:
        return False  # Don't auto-refresh on first load
    
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
        
        # Get old document count for comparison
        old_vectorstore = cl.user_session.get("vectorstore")
        try:
            old_count = old_vectorstore._collection.count() if old_vectorstore else 0
        except:
            old_count = 0
        
        # Reload vector store with fresh data (force_fresh=True ensures new client connection)
        vectorstore = get_vectorstore(
            current_collection if current_collection != "default" else None,
            force_fresh=True
        )
        qa_chain, retriever = create_qa_chain(vectorstore, llm)
        
        # Get new document count
        try:
            new_count = vectorstore._collection.count()
        except:
            new_count = 0
        
        # Update session with refreshed components
        cl.user_session.set("qa_chain", qa_chain)
        cl.user_session.set("retriever", retriever)
        cl.user_session.set("vectorstore", vectorstore)
        cl.user_session.set("last_cache_refresh", datetime.now())
        
        if new_count != old_count:
            logger.info(f"Vector store cache refreshed successfully - Document count changed: {old_count} → {new_count}")
        else:
            logger.info(f"Vector store cache refreshed successfully - Document count unchanged: {new_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error refreshing vector store cache: {str(e)}")
        return False


def create_qa_chain(vectorstore, llm):
    """Create RAG chain using modern LangChain LCEL"""
    
    # Custom prompt template optimized for better answers
    prompt = ChatPromptTemplate.from_template("""You are an expert assistant that provides accurate, detailed answers based on the given context from documents.

CONTEXT FROM DOCUMENTS:
{context}

QUESTION: {question}

INSTRUCTIONS:
1. Carefully analyze the context provided above
2. Answer the question using ONLY information from the context
3. If the context contains the answer, provide a complete, detailed response
4. Quote relevant sections from the context to support your answer
5. If the context doesn't fully answer the question, explain what information is missing
6. Be specific and cite details - don't give vague or generic answers
7. If you're unsure, say so rather than guessing

ANSWER:""")
    
    # Get retriever with better search parameters
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 8  # Return top 8 relevant chunks for better context
        }
    )
    
    # Format retrieved documents with safety checks
    def format_docs(docs):
        if not docs:
            return "No documents available."
        
        # Filter out None or invalid documents
        valid_docs = [doc for doc in docs if doc and hasattr(doc, 'page_content') and doc.page_content]
        
        if not valid_docs:
            return "No valid documents found."
        
        return "\n\n".join(doc.page_content for doc in valid_docs)
    
    # Create chain using LCEL
    qa_chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough()
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    
    return qa_chain, retriever


@cl.on_chat_start
async def start():
    """Initialize chatbot on start"""
    
    # Welcome message
    await cl.Message(
        content="# 🤖 VectorDB Chatbot\n\nWelcome! I can answer questions based on documents stored in your VectorDB.\n\n**Available Commands:**\n- Ask any question about your documents\n- Type `/collections` to see available collections\n- Type `/switch <collection_name>` to switch collections\n- Type `/info` to see current configuration\n\n**How it works:**\nI search your document collection for relevant information and use it to answer your questions."
    ).send()
    
    try:
        # Initialize LLM
        await cl.Message(content=f"🔄 Initializing {LLM_PROVIDER.upper()} LLM...").send()
        llm = get_llm()
        
        # Initialize vector store
        collection_msg = f" (Collection: {DEFAULT_COLLECTION})" if DEFAULT_COLLECTION else ""
        await cl.Message(content=f"🔄 Loading VectorDB{collection_msg}...").send()
        vectorstore = get_vectorstore(DEFAULT_COLLECTION)
        
        # Create QA chain
        qa_chain, retriever = create_qa_chain(vectorstore, llm)
        
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
        
        ready_message = f"✅ Ready! Using **{LLM_PROVIDER.upper()}** with collection **{cl.user_session.get('current_collection')}**\n\n"
        ready_message += f"📊 **{doc_count} documents** in collection\n"
        
        if CACHE_AUTO_REFRESH_ENABLED:
            refresh_interval_mins = CACHE_REFRESH_INTERVAL / 60
            ready_message += f"🔄 *Auto-refresh: Every {refresh_interval_mins:.0f} minutes*\n\n"
        else:
            ready_message += f"🔄 *Manual refresh mode* (say 'refresh' to reload documents)\n\n"
        
        if doc_count == 0:
            ready_message += "⚠️ **Collection is empty!** Please upload documents using the main UI before asking questions.\n\n"
            ready_message += "💡 Use `/collections` to see other collections with documents."
        else:
            ready_message += "Ask me anything!"
        
        await cl.Message(content=ready_message).send()
        
    except Exception as e:
        error_msg = f"❌ Error initializing chatbot: {str(e)}\n\n"
        error_msg += "**Troubleshooting:**\n"
        error_msg += "1. Make sure VectorDB is running and contains documents\n"
        error_msg += "2. Check that your API keys are set in environment variables\n"
        error_msg += f"3. Verify CHROMA_DB_PATH points to: {CHROMA_DB_PATH}"
        
        await cl.Message(content=error_msg).send()
        logger.error(f"Initialization error: {str(e)}")


@cl.on_message
async def main(message: cl.Message):
    """Handle user messages"""
    
    user_message = message.content.strip()
    user_message_lower = user_message.lower()
    
    # Handle special commands
    if user_message.startswith("/"):
        await handle_command(user_message)
        return
    
    # Handle natural language "refresh" command
    if user_message_lower in ["refresh", "reload", "refresh cache", "reload cache", "update", "refresh documents"]:
        await handle_command("/refresh")
        return
    
    # Get QA chain from session
    qa_chain = cl.user_session.get("qa_chain")
    retriever = cl.user_session.get("retriever")
    
    if not qa_chain:
        await cl.Message(
            content="❌ Chatbot not initialized. Please refresh the page."
        ).send()
        return
    
    # Show thinking message
    thinking_msg = cl.Message(content="🤔 Searching documents and generating answer...")
    await thinking_msg.send()
    
    try:
        # Check if we need to refresh the cache
        cache_refreshed = await refresh_vectorstore_if_needed()
        
        # Get updated components if cache was refreshed
        if cache_refreshed:
            qa_chain = cl.user_session.get("qa_chain")
            retriever = cl.user_session.get("retriever")
            thinking_msg.content = "🔄 Cache refreshed! Searching latest documents..."
            await thinking_msg.update()
        
        # Check if collection is empty
        vectorstore = cl.user_session.get("vectorstore")
        try:
            doc_count = vectorstore._collection.count() if vectorstore else 0
        except:
            doc_count = 0
        
        if doc_count == 0:
            thinking_msg.content = "📭 **No documents found in the current collection.**\n\nPlease upload some documents first using the main UI, then try asking your question again.\n\n💡 Use `/collections` to see other available collections, or `/switch <name>` to switch to one with documents."
            await thinking_msg.update()
            return
        
        # Get source documents first (using modern API)
        source_documents = await cl.make_async(retriever.invoke)(user_message)
        
        # Check if retrieval returned any results
        if not source_documents or len(source_documents) == 0:
            thinking_msg.content = "🔍 **No relevant documents found for your question.**\n\nThe collection has documents, but none matched your query. Try:\n- Rephrasing your question\n- Using different keywords\n- Checking if the right documents are uploaded"
            await thinking_msg.update()
            return
        
        # Query the chain
        answer = await cl.make_async(qa_chain.invoke)(user_message)
        
        # Format response
        response_text = f"{answer}\n\n"
        
        # Add sources if available
        if source_documents:
            response_text += "---\n**📚 Sources:**\n"
            for i, doc in enumerate(source_documents[:3], 1):  # Show top 3 sources
                metadata = doc.metadata
                doc_name = metadata.get("name", "Unknown")
                version = metadata.get("version", "")
                version_str = f" (v{version})" if version else ""
                
                response_text += f"{i}. **{doc_name}**{version_str}\n"
                
                # Add snippet
                snippet = doc.page_content[:150]
                if len(doc.page_content) > 150:
                    snippet += "..."
                response_text += f"   > {snippet}\n\n"
        
        # Update the thinking message with the response
        thinking_msg.content = response_text
        await thinking_msg.update()
        
    except Exception as e:
        error_msg = f"❌ Error processing your question: {str(e)}\n\n"
        error_msg += "Please try rephrasing your question or check the logs."
        
        thinking_msg.content = error_msg
        await thinking_msg.update()
        
        logger.error(f"Query error: {str(e)}")


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
                refresh_status = f"Auto-refresh enabled | Every {CACHE_REFRESH_INTERVAL}s ({CACHE_REFRESH_INTERVAL/60:.0f} min)"
        else:
            if last_refresh:
                time_since_refresh = datetime.now() - last_refresh
                seconds_ago = int(time_since_refresh.total_seconds())
                refresh_status = f"Manual mode | Last refresh: {seconds_ago}s ago"
            else:
                refresh_status = "Manual mode | Say 'refresh' to reload documents"
        
        info_text = f"""**⚙️ Current Configuration:**

- **LLM Provider:** {LLM_PROVIDER.upper()}
- **Model:** {MODEL_NAME}
- **Collection:** {current_collection}
- **Database Path:** {CHROMA_DB_PATH}
- **Temperature:** {TEMPERATURE}
- **Max Tokens:** {MAX_TOKENS}
- **Refresh Mode:** {refresh_status}
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
                collections_text += f"- **{col.name}** ({doc_count} items)\n"
            
            collections_text += f"\n💡 Use `/switch <collection_name>` to switch collections"
            
            await cl.Message(content=collections_text).send()
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error listing collections: {str(e)}"
            ).send()
    
    elif command.startswith("/switch "):
        collection_name = command.replace("/switch ", "").strip()
        
        try:
            # Reload vector store with new collection (force fresh connection)
            vectorstore = get_vectorstore(collection_name, force_fresh=True)
            llm = cl.user_session.get("llm")
            qa_chain, retriever = create_qa_chain(vectorstore, llm)
            
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
            cl.user_session.set("last_cache_refresh", datetime.now())  # Reset refresh timer
            
            await cl.Message(
                content=f"✅ Switched to collection: **{collection_name}**\n\n📊 {doc_count} documents loaded\n🔄 Cache refreshed with latest data"
            ).send()
            
            logger.info(f"Switched to collection '{collection_name}' with {doc_count} documents")
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error switching collection: {str(e)}"
            ).send()
            logger.error(f"Error switching to collection '{collection_name}': {str(e)}")
    
    elif command == "/refresh":
        # Manual refresh command
        try:
            current_collection = cl.user_session.get("current_collection")
            llm = cl.user_session.get("llm")
            
            msg = await cl.Message(content="🔄 Manually refreshing cache...").send()
            
            # Get old count
            old_vectorstore = cl.user_session.get("vectorstore")
            try:
                old_count = old_vectorstore._collection.count() if old_vectorstore else 0
            except:
                old_count = 0
            
            # Force fresh connection to get latest data
            vectorstore = get_vectorstore(
                current_collection if current_collection != "default" else None,
                force_fresh=True
            )
            qa_chain, retriever = create_qa_chain(vectorstore, llm)
            
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
                await cl.Message(
                    content=f"✅ Cache manually refreshed!\n\n📊 Documents: {old_count} → **{new_count}** ({new_count - old_count:+d} change)\n\nNow querying latest documents."
                ).send()
                logger.info(f"Manual refresh: Document count changed {old_count} → {new_count}")
            else:
                await cl.Message(
                    content=f"✅ Cache manually refreshed! ({new_count} documents)\n\nNow querying latest documents."
                ).send()
                logger.info(f"Manual refresh: Document count unchanged at {new_count}")
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error refreshing cache: {str(e)}"
            ).send()
            logger.error(f"Manual refresh error: {str(e)}")
    
    else:
        refresh_info = ""
        if CACHE_AUTO_REFRESH_ENABLED:
            refresh_info = f"\n🔄 Cache auto-refreshes every {CACHE_REFRESH_INTERVAL/60:.0f} minutes to get latest documents."
        else:
            refresh_info = "\n🔄 Say 'refresh' anytime to reload documents from VectorDB."
        
        help_text = f"""**Available Commands:**

- `/info` - Show current configuration and cache status
- `/collections` - List available collections
- `/switch <name>` - Switch to a different collection
- `/refresh` or just say **'refresh'** - Reload latest documents from VectorDB

💡 Just type your question to chat with the documents!{refresh_info}"""
        
        await cl.Message(content=help_text).send()


if __name__ == "__main__":
    # This is for running with: chainlit run app.py
    pass

