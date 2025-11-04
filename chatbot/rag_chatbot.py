"""
Production-Grade RAG Chatbot with Multi-Collection Support
Built with Chainlit and Python 3.12

This chatbot uses the RAG module to interact with the Vector Database
via the backend API, supporting queries across multiple collections.
"""

import chainlit as cl
import os
import logging
from typing import Optional, List
from datetime import datetime

# Import RAG module
from rag_module import (
    VectorDBClient,
    RAGEngine,
    RAGSessionManager,
    RAGResponse
)

# Import LLM providers
try:
    from langchain_groq import ChatGroq
except ImportError:
    ChatGroq = None
    logging.warning("Groq not available. Install with: pip install langchain-groq")

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None
    logging.warning("Google Gemini not available. Install with: pip install langchain-google-genai")

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None
    logging.warning("OpenAI not available. Install with: pip install langchain-openai")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Backend API Configuration
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
BACKEND_API_TIMEOUT = int(os.getenv("BACKEND_API_TIMEOUT", "30"))

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
MODEL_NAME = os.getenv("MODEL_NAME", "mixtral-8x7b-32768")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))

# RAG Configuration
MAX_RESULTS_PER_COLLECTION = int(os.getenv("MAX_RESULTS_PER_COLLECTION", "8"))  # Reduced from 10 to 8
MAX_TOTAL_RESULTS = int(os.getenv("MAX_TOTAL_RESULTS", "30"))  # Reduced from 50 to 30
MIN_SIMILARITY_SCORE = float(os.getenv("MIN_SIMILARITY_SCORE", "0.3"))
ENABLE_RERANKING = os.getenv("ENABLE_RERANKING", "true").lower() == "true"
ENABLE_QUERY_REWRITING = os.getenv("ENABLE_QUERY_REWRITING", "true").lower() == "true"
ENABLE_MULTI_QUERY = os.getenv("ENABLE_MULTI_QUERY", "true").lower() == "true"

# Default collections (comma-separated, empty = all collections)
DEFAULT_COLLECTIONS = os.getenv("DEFAULT_COLLECTIONS", "").split(",")
DEFAULT_COLLECTIONS = [c.strip() for c in DEFAULT_COLLECTIONS if c.strip()]


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
            timeout=30.0
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
# CHAINLIT HANDLERS
# ============================================================================

@cl.on_chat_start
async def start():
    """Initialize chatbot on start"""
    
    welcome_message = """# 🤖 Production-Grade RAG Chatbot

Welcome! I'm an advanced RAG chatbot that can query documents across multiple collections in your knowledge base.

## Features:
- **Multi-Collection Support**: Query across one or multiple collections simultaneously
- **Advanced Accuracy**: Query rewriting, multi-query retrieval, advanced reranking
- **Conversation Memory**: Remembers context across questions for intelligent follow-ups
- **Cross-Document Synthesis**: Connects concepts across multiple documents intelligently
- **Follow-Up Detection**: Automatically understands follow-up questions using conversation context
- **Result Diversification**: Ensures balanced representation from different documents
- **Large-Scale**: Optimized for 100s of documents per collection
- **Smart Retrieval**: Semantic search with multi-factor reranking
- **Source Citations**: Shows which documents and collections were used

## Commands:
- `/info` - Show current configuration
- `/collections` - List available collections
- `/use <collection1> [collection2] ...` - Set collections to query (leave empty to query all)
- `/clear` - Clear collection selection and conversation history
- `/history` - Show conversation history

## Examples:
- **Multi-document query**: "What do Atomic Habits and Clean Code say about building good habits?"
- **Follow-up question**: After asking about Atomic Habits, ask "How about Clean Code?" - I'll understand the context!
- **Compare concepts**: "Compare the approach to habits in both books"

Ask me anything about your documents!"""
    
    await cl.Message(content=welcome_message).send()
    
    try:
        # Initialize LLM
        await cl.Message(content=f"🔄 Initializing {LLM_PROVIDER.upper()} LLM...").send()
        llm = get_llm()
        
        # Initialize VectorDB client
        await cl.Message(content=f"🔄 Connecting to Vector Database API ({BACKEND_API_URL})...").send()
        vector_db_client = VectorDBClient(
            api_base_url=BACKEND_API_URL,
            timeout=BACKEND_API_TIMEOUT
        )
        
        # Initialize RAG Engine
        rag_engine = RAGEngine(
            vector_db_client=vector_db_client,
            llm=llm,
            max_results_per_collection=MAX_RESULTS_PER_COLLECTION,
            max_total_results=MAX_TOTAL_RESULTS,
            min_similarity_score=MIN_SIMILARITY_SCORE,
            enable_reranking=ENABLE_RERANKING,
            enable_conversation=True,
            enable_query_rewriting=ENABLE_QUERY_REWRITING,
            enable_multi_query=ENABLE_MULTI_QUERY
        )
        
        # Initialize Session Manager
        session_manager = RAGSessionManager(rag_engine)
        
        # Set default collections if specified
        if DEFAULT_COLLECTIONS:
            session_manager.set_default_collections(DEFAULT_COLLECTIONS)
            await cl.Message(
                content=f"📚 Default collections set to: {', '.join(DEFAULT_COLLECTIONS)}"
            ).send()
        
        # Store in user session
        cl.user_session.set("vector_db_client", vector_db_client)
        cl.user_session.set("rag_engine", rag_engine)
        cl.user_session.set("session_manager", session_manager)
        cl.user_session.set("llm", llm)
        cl.user_session.set("selected_collections", DEFAULT_COLLECTIONS if DEFAULT_COLLECTIONS else None)
        
        # Get collection info
        try:
            collections = await vector_db_client.list_collections()
            collection_count = len(collections)
            total_docs = sum(col.get("count", 0) for col in collections)
        except Exception as e:
            logger.warning(f"Could not fetch collection info: {str(e)}")
            collection_count = 0
            total_docs = 0
        
        # Ready message
        ready_message = f"""✅ **Ready!**

**Configuration:**
- **LLM Provider:** {LLM_PROVIDER.upper()}
- **Model:** {MODEL_NAME}
- **Backend API:** {BACKEND_API_URL}
- **Temperature:** {TEMPERATURE} (optimized for accuracy)
- **Retrieval:** Max {MAX_RESULTS_PER_COLLECTION} per collection, {MAX_TOTAL_RESULTS} total
- **Collections Available:** {collection_count}
- **Total Documents:** {total_docs}
- **Selected Collections:** {', '.join(DEFAULT_COLLECTIONS) if DEFAULT_COLLECTIONS else 'All collections'}

"""
        
        if collection_count == 0:
            ready_message += "⚠️ **No collections found!** Please upload documents using the main UI.\n\n"
        else:
            ready_message += "💬 Ask me anything about your documents! Use `/collections` to see available collections."
        
        await cl.Message(content=ready_message).send()
        
    except Exception as e:
        error_msg = f"""❌ **Error initializing chatbot**

**Error:** {str(e)}

**Troubleshooting:**
1. Verify backend API is running at: `{BACKEND_API_URL}`
2. Check API keys are set in environment variables
3. Verify backend has collections with documents
4. Check logs for detailed error information"""
        
        await cl.Message(content=error_msg).send()
        logger.error(f"Initialization error: {str(e)}", exc_info=True)


@cl.on_message
async def main(message: cl.Message):
    """Handle user messages with RAG pipeline"""
    
    user_message = message.content.strip()
    user_message_lower = user_message.lower()
    
    # Handle special commands
    if user_message.startswith("/"):
        await handle_command(user_message)
        return
    
    # Handle natural language commands
    if user_message_lower in ["refresh", "reload", "clear"]:
        await handle_command("/clear")
        return
    
    # Get session components
    session_manager = cl.user_session.get("session_manager")
    if not session_manager:
        await cl.Message(
            content="❌ Chatbot not initialized. Please refresh the page."
        ).send()
        return
    
    # Show thinking message
    thinking_msg = cl.Message(content="🤔 Processing your question...")
    await thinking_msg.send()
    
    try:
        # Get selected collections
        selected_collections = cl.user_session.get("selected_collections")
        
        # Execute RAG query
        thinking_msg.content = "📚 Retrieving relevant documents from knowledge base..."
        await thinking_msg.update()
        
        rag_response: RAGResponse = await session_manager.query(
            query=user_message,
            collection_names=selected_collections,
            use_defaults=True
        )
        
        # Format response with sources
        response_text = ""
        
        # Add follow-up indicator if detected
        if rag_response.is_followup:
            response_text += "💬 *Detected follow-up question - using conversation context*\n\n"
        
        response_text += f"{rag_response.answer}\n\n"
        
        # Add sources section
        if rag_response.sources:
            response_text += "---\n\n**📚 Sources:**\n\n"
            
            # Group sources by collection
            sources_by_collection = {}
            for source in rag_response.sources:
                collection = source.collection
                if collection not in sources_by_collection:
                    sources_by_collection[collection] = []
                sources_by_collection[collection].append(source)
            
            # Display sources grouped by collection
            source_num = 1
            for collection, sources in sources_by_collection.items():
                response_text += f"**Collection: {collection}**\n\n"
                
                # Track unique documents to avoid duplicates
                seen_docs = set()
                for source in sources[:5]:  # Show top 5 per collection
                    doc_key = f"{source.document_name}_{source.collection}"
                    if doc_key in seen_docs:
                        continue
                    seen_docs.add(doc_key)
                    
                    version = source.metadata.get("version", "")
                    version_str = f" (v{version})" if version else ""
                    
                    response_text += f"{source_num}. **{source.document_name}**{version_str}"
                    if source.similarity_score > 0:
                        response_text += f" (Relevance: {source.similarity_score:.2f})"
                    response_text += "\n"
                    
                    # Add snippet
                    snippet = source.content[:200].strip()
                    if len(source.content) > 200:
                        snippet += "..."
                    response_text += f"   > {snippet}\n\n"
                    source_num += 1
                
                response_text += "\n"
        
        # Add collection info
        if rag_response.collections_searched:
            collections_text = ", ".join(rag_response.collections_searched)
            response_text += f"**Searched collections:** {collections_text}\n"
            response_text += f"**Total results found:** {rag_response.total_results}\n"
        
        # Update thinking message with response
        thinking_msg.content = response_text
        await thinking_msg.update()
        
    except Exception as e:
        error_msg = f"""❌ **Error processing your question**

**Error:** {str(e)}"""

        # Check for token limit errors specifically
        error_str = str(e).lower()
        if "length" in error_str or "token" in error_str or "400" in error_str:
            error_msg += """

**This error is likely due to too much context being sent to the LLM.**

**Solutions:**
- Use `/clear` to clear conversation history
- Try a more specific question (fewer documents will be retrieved)
- Break your question into smaller parts
- The system will automatically reduce context size in future queries"""
        else:
            error_msg += """

Please try:
- Rephrasing your question
- Checking if relevant documents are in the collections
- Verifying backend API is running
- Using `/collections` to see available collections"""

        error_msg += "\n\nCheck logs for detailed error information."
        
        thinking_msg.content = error_msg
        await thinking_msg.update()
        logger.error(f"Query error: {str(e)}", exc_info=True)


async def handle_command(command: str):
    """Handle special commands"""
    
    if command == "/info":
        session_manager = cl.user_session.get("session_manager")
        selected_collections = cl.user_session.get("selected_collections")
        
        info_text = f"""**⚙️ Current Configuration:**

**LLM Settings:**
- Provider: {LLM_PROVIDER.upper()}
- Model: {MODEL_NAME}
- Temperature: {TEMPERATURE} (low for accuracy)
- Max Tokens: {MAX_TOKENS}

**Retrieval Settings:**
- Max Results per Collection: {MAX_RESULTS_PER_COLLECTION}
- Max Total Results: {MAX_TOTAL_RESULTS}
- Min Similarity Score: {MIN_SIMILARITY_SCORE}
- Reranking: {'✅ Enabled' if ENABLE_RERANKING else '❌ Disabled'}
- Query Rewriting: {'✅ Enabled' if ENABLE_QUERY_REWRITING else '❌ Disabled'}
- Multi-Query Retrieval: {'✅ Enabled' if ENABLE_MULTI_QUERY else '❌ Disabled'}

**Accuracy Features:**
- ✅ Advanced Reranking (multi-factor scoring)
- ✅ Result Diversification (balanced document representation)
- ✅ Enhanced Prompt Engineering (cross-document synthesis)
- ✅ Conversation Memory (context-aware follow-ups)

**Backend API:**
- URL: {BACKEND_API_URL}
- Timeout: {BACKEND_API_TIMEOUT}s

**Selected Collections:**
- {', '.join(selected_collections) if selected_collections else 'All collections (none selected)'}

💡 Use `/use <collection1> [collection2] ...` to select specific collections"""
        
        await cl.Message(content=info_text).send()
    
    elif command == "/collections":
        try:
            vector_db_client = cl.user_session.get("vector_db_client")
            if not vector_db_client:
                await cl.Message(content="❌ VectorDB client not initialized.").send()
                return
            
            collections = await vector_db_client.list_collections()
            
            if not collections:
                await cl.Message(content="📭 No collections found in VectorDB.").send()
                return
            
            collections_text = "**📚 Available Collections:**\n\n"
            for col in collections:
                doc_count = col.get("count", 0)
                collections_text += f"- **{col['name']}** ({doc_count} documents)\n"
            
            selected = cl.user_session.get("selected_collections")
            if selected:
                collections_text += f"\n💡 Currently selected: {', '.join(selected)}"
            else:
                collections_text += f"\n💡 Currently querying: All collections"
            
            collections_text += f"\n\nUse `/use <collection1> [collection2] ...` to select specific collections"
            
            await cl.Message(content=collections_text).send()
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error listing collections: {str(e)}"
            ).send()
            logger.error(f"Error listing collections: {str(e)}", exc_info=True)
    
    elif command.startswith("/use "):
        collection_names = command.replace("/use ", "").strip().split()
        
        if not collection_names:
            # Clear selection (query all)
            cl.user_session.set("selected_collections", None)
            await cl.Message(
                content="✅ Collection selection cleared. Will query all collections."
            ).send()
            return
        
        try:
            vector_db_client = cl.user_session.get("vector_db_client")
            if not vector_db_client:
                await cl.Message(content="❌ VectorDB client not initialized.").send()
                return
            
            # Verify collections exist
            all_collections = await vector_db_client.list_collections()
            all_collection_names = [col["name"] for col in all_collections]
            
            invalid_collections = [c for c in collection_names if c not in all_collection_names]
            if invalid_collections:
                await cl.Message(
                    content=f"❌ Invalid collections: {', '.join(invalid_collections)}\n\n"
                    f"Available collections: {', '.join(all_collection_names)}"
                ).send()
                return
            
            # Update session
            cl.user_session.set("selected_collections", collection_names)
            session_manager = cl.user_session.get("session_manager")
            if session_manager:
                session_manager.set_default_collections(collection_names)
            
            await cl.Message(
                content=f"✅ **Selected collections:** {', '.join(collection_names)}\n\n"
                f"All queries will now search these collections only."
            ).send()
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error setting collections: {str(e)}"
            ).send()
            logger.error(f"Error setting collections: {str(e)}", exc_info=True)
    
    elif command == "/clear":
        # Clear both collection selection and conversation history
        cl.user_session.set("selected_collections", None)
        session_manager = cl.user_session.get("session_manager")
        if session_manager:
            session_manager.set_default_collections([])
            session_manager.clear_conversation()
        
        await cl.Message(
            content="✅ **Cleared!**\n\n- Collection selection cleared (will query all collections)\n- Conversation history cleared"
        ).send()
    
    elif command == "/history":
        session_manager = cl.user_session.get("session_manager")
        if not session_manager:
            await cl.Message(content="❌ Session manager not initialized.").send()
            return
        
        summary = session_manager.get_conversation_summary()
        if summary:
            await cl.Message(
                content=f"**📜 Conversation History:**\n\n{summary}\n\n💡 Use `/clear` to clear history"
            ).send()
        else:
            await cl.Message(
                content="📜 **No conversation history yet.**\n\nStart asking questions to build conversation context!"
            ).send()
    
    else:
        help_text = """**Available Commands:**

- `/info` - Show current configuration and settings
- `/collections` - List all available collections
- `/use <collection1> [collection2] ...` - Select specific collections to query
- `/clear` - Clear selection and conversation history (query all collections)
- `/history` - Show conversation history

💡 **Multi-Document Queries:**
- Ask about multiple documents: "What do Atomic Habits and Clean Code say about habits?"
- Follow-up questions: "How about Clean Code?" (automatically uses context)
- Compare concepts: "Compare the approach in both books"

💡 Just type your question to chat with the documents!"""
        
        await cl.Message(content=help_text).send()


if __name__ == "__main__":
    # This is for running with: chainlit run rag_chatbot.py
    pass

