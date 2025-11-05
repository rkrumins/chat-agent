"""
Production-Grade RAG Chatbot with Multi-Collection Support
Built with Chainlit and Python 3.12

This chatbot uses the RAG module to interact with the Vector Database
via the backend API, supporting queries across multiple collections.
"""

import chainlit as cl
import os
import logging
import re
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

# Import configuration from config.py
from config import config

# Validate configuration on import
config_errors = config.validate()
if config_errors:
    logger.warning("Configuration validation errors:")
    for error in config_errors:
        logger.warning(f"  - {error}")
    logger.warning("Some features may not work correctly. Please fix the configuration errors.")


# ============================================================================
# LLM INITIALIZATION
# ============================================================================

def get_llm(provider: str = None):
    """Get LLM instance based on provider"""
    provider = provider or config.LLM_PROVIDER
    
    if provider == "groq":
        if not ChatGroq:
            raise ValueError("Groq not installed. Run: pip install langchain-groq")
        api_key = config.GROQ_API_KEY
        if not api_key:
            raise ValueError("GROQ_API_KEY not set. Please set it in your environment or config.py")
        return ChatGroq(
            groq_api_key=api_key,
            model_name=config.MODEL_NAME,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            timeout=30.0
        )
    
    elif provider == "gemini":
        if not ChatGoogleGenerativeAI:
            raise ValueError("Google Gemini not installed. Run: pip install langchain-google-genai")
        api_key = config.GOOGLE_API_KEY
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set. Please set it in your environment or config.py")
        model = config.MODEL_NAME
        return ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=model,
            temperature=config.TEMPERATURE,
            max_output_tokens=config.MAX_TOKENS
        )
    
    elif provider == "openai":
        if not ChatOpenAI:
            raise ValueError("OpenAI not installed. Run: pip install langchain-openai")
        api_key = config.OPENAI_API_KEY
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set. Please set it in your environment or config.py")
        model = config.MODEL_NAME
        return ChatOpenAI(
            openai_api_key=api_key,
            model_name=model,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
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
        await cl.Message(content=f"🔄 Initializing {config.LLM_PROVIDER.upper()} LLM...").send()
        llm = get_llm()
        
        # Initialize VectorDB client
        await cl.Message(content=f"🔄 Connecting to Vector Database API ({config.BACKEND_API_URL})...").send()
        vector_db_client = VectorDBClient(
            api_base_url=config.BACKEND_API_URL,
            timeout=config.BACKEND_API_TIMEOUT
        )
        
        # Initialize RAG Engine
        rag_engine = RAGEngine(
            vector_db_client=vector_db_client,
            llm=llm,
            max_results_per_collection=config.MAX_RESULTS_PER_COLLECTION,
            max_total_results=config.MAX_TOTAL_RESULTS,
            min_similarity_score=config.MIN_SIMILARITY_SCORE,
            enable_reranking=config.ENABLE_RERANKING,
            enable_conversation=True,
            enable_query_rewriting=config.ENABLE_QUERY_REWRITING,
            enable_multi_query=config.ENABLE_MULTI_QUERY
        )
        
        # Initialize Session Manager
        session_manager = RAGSessionManager(rag_engine)
        
        # Set default collections if specified
        if config.DEFAULT_COLLECTIONS:
            session_manager.set_default_collections(config.DEFAULT_COLLECTIONS)
            await cl.Message(
                content=f"📚 Default collections set to: {', '.join(config.DEFAULT_COLLECTIONS)}"
            ).send()
        
        # Store in user session
        cl.user_session.set("vector_db_client", vector_db_client)
        cl.user_session.set("rag_engine", rag_engine)
        cl.user_session.set("session_manager", session_manager)
        cl.user_session.set("llm", llm)
        cl.user_session.set("selected_collections", config.DEFAULT_COLLECTIONS if config.DEFAULT_COLLECTIONS else None)
        
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
- **LLM Provider:** {config.LLM_PROVIDER.upper()}
- **Model:** {config.MODEL_NAME}
- **Backend API:** {config.BACKEND_API_URL}
- **Temperature:** {config.TEMPERATURE} (optimized for accuracy)
- **Retrieval:** Max {config.MAX_RESULTS_PER_COLLECTION} per collection, {config.MAX_TOTAL_RESULTS} total
- **Collections Available:** {collection_count}
- **Total Documents:** {total_docs}
- **Selected Collections:** {', '.join(config.DEFAULT_COLLECTIONS) if config.DEFAULT_COLLECTIONS else 'All collections'}

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
1. Verify backend API is running at: `{config.BACKEND_API_URL}`
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
        
        # Add follow-up indicator if detected (subtle, friendly)
        if rag_response.is_followup:
            response_text += "💬 *I'm using context from our previous conversation to better understand your question.*\n\n"
        
        # Main answer
        response_text += f"{rag_response.answer}\n\n"
        
        # Add confidence indicator (subtle, at the end)
        if rag_response.confidence_score is not None:
            confidence_pct = int(rag_response.confidence_score * 100)
            if confidence_pct >= 80:
                confidence_note = "high confidence"
                confidence_emoji = "🟢"
            elif confidence_pct >= 60:
                confidence_note = "moderate confidence"
                confidence_emoji = "🟡"
            else:
                confidence_note = "lower confidence - some information may be incomplete"
                confidence_emoji = "🔴"
            response_text += f"---\n\n{confidence_emoji} *Confidence: {confidence_pct}%* ({confidence_note})\n\n"
        
        # Add sources section (cleaner, more user-friendly)
        if rag_response.sources:
            response_text += "**📚 Sources used:**\n\n"
            
            # Helper function to clean document name (remove chunk info if embedded)
            def clean_document_name(name):
                """Remove chunk information from document name if present"""
                # Remove patterns like " (chunk X)" or " (chunk X-Y)"
                import re
                cleaned = re.sub(r'\s*\(chunk\s+\d+[-\d]*\)', '', name, flags=re.IGNORECASE)
                return cleaned.strip()
            
            # Helper function to clean snippet text
            def clean_snippet_text(text):
                """Clean snippet text by removing artifacts and formatting"""
                if not text:
                    return ""
                
                # Remove excessive dots/periods (like "................................")
                text = re.sub(r'\.{4,}', '', text)
                
                # Remove page number patterns (like " 19" or " 23" at end of lines)
                lines = text.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Remove trailing page numbers (numbers at end of line with spaces)
                    line = re.sub(r'\s+\d{1,3}\s*$', '', line)
                    # Remove lines that are mostly dots, dashes, underscores, or whitespace
                    if line.strip() and not re.match(r'^[\s\.\-_=]+$', line):
                        # Clean up the line
                        cleaned_line = line.strip()
                        # Remove excessive spaces
                        cleaned_line = re.sub(r'\s+', ' ', cleaned_line)
                        if cleaned_line:
                            cleaned_lines.append(cleaned_line)
                
                # Take first meaningful lines (up to 2 lines)
                if cleaned_lines:
                    text = ' '.join(cleaned_lines[:2])  # Join lines with space
                else:
                    text = ""
                
                # Limit length and ensure it ends properly
                if len(text) > 180:
                    # Try to cut at word boundary
                    text = text[:177]
                    last_space = text.rfind(' ')
                    if last_space > 150:  # Only use word boundary if not too short
                        text = text[:last_space]
                    text = text.rstrip() + "..."
                
                return text.strip()
            
            # Group sources by document and collect chunk information
            doc_sources = {}
            for source in rag_response.sources:
                # Get clean document name from metadata (parent_name or name)
                # This avoids the chunk info that might be embedded in document_name
                clean_doc_name = source.metadata.get("parent_name") or source.metadata.get("name") or clean_document_name(source.document_name)
                doc_key = f"{clean_doc_name}_{source.collection}"
                
                # Collect chunk number if available
                chunk_num = source.metadata.get("chunk_number") or source.metadata.get("chunk_index")
                
                if doc_key not in doc_sources:
                    doc_sources[doc_key] = {
                        'document_name': clean_doc_name,
                        'collection': source.collection,
                        'version': source.metadata.get("version", ""),
                        'similarity': source.similarity_score,  # Will track best similarity
                        'chunks': [],  # List of chunk numbers
                        'best_snippet': source.content[:250].strip()  # Best snippet for preview
                    }
                
                # Update similarity if this source has higher relevance
                if source.similarity_score > doc_sources[doc_key]['similarity']:
                    doc_sources[doc_key]['similarity'] = source.similarity_score
                    doc_sources[doc_key]['best_snippet'] = source.content[:250].strip()
                
                # Collect chunk number if available
                if chunk_num is not None:
                    doc_sources[doc_key]['chunks'].append(int(chunk_num))
            
            # Format chunk ranges (e.g., [9, 10, 75, 76] -> "chunks 9-10, 75-76")
            def format_chunk_ranges(chunk_numbers):
                """Format chunk numbers into ranges for better readability"""
                if not chunk_numbers:
                    return ""
                
                sorted_chunks = sorted(set(chunk_numbers))
                ranges = []
                start = sorted_chunks[0]
                end = sorted_chunks[0]
                
                for chunk in sorted_chunks[1:]:
                    if chunk == end + 1:
                        # Consecutive chunk
                        end = chunk
                    else:
                        # Gap found, save current range
                        if start == end:
                            ranges.append(str(start))
                        else:
                            ranges.append(f"{start}-{end}")
                        start = chunk
                        end = chunk
                
                # Add last range
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                
                return ", ".join(ranges)
            
            # Display unique documents (sorted by relevance)
            sorted_docs = sorted(doc_sources.items(), key=lambda x: x[1]['similarity'], reverse=True)
            
            for i, (doc_key, doc_info) in enumerate(sorted_docs[:5], 1):  # Show top 5 documents
                # Format document name with version
                doc_name = doc_info['document_name']
                version_str = f" v{doc_info['version']}" if doc_info['version'] else ""
                collection_note = f" from *{doc_info['collection']}*" if len(rag_response.collections_searched) > 1 else ""
                
                # Format chunk information
                chunk_ranges = format_chunk_ranges(doc_info['chunks'])
                if chunk_ranges:
                    chunk_info = f" (chunks {chunk_ranges})"
                else:
                    chunk_info = ""
                
                # Build the source line
                response_text += f"{i}. **{doc_name}**{chunk_info}{version_str}{collection_note}\n"
                
                # Add snippet if meaningful
                raw_snippet = doc_info['best_snippet']
                if len(raw_snippet) > 30:  # Only show if substantial
                    # Clean snippet text
                    snippet = clean_snippet_text(raw_snippet)
                    
                    if snippet:
                        response_text += f"   *\"{snippet}\"*\n"
                
                response_text += "\n"
        
        # Add brief summary footer (only if multiple collections or sources)
        if len(rag_response.collections_searched) > 1 or rag_response.total_results > 5:
            response_text += "---\n"
            if len(rag_response.collections_searched) > 1:
                collections_text = ", ".join(rag_response.collections_searched[:3])
                if len(rag_response.collections_searched) > 3:
                    collections_text += f", and {len(rag_response.collections_searched) - 3} more"
                response_text += f"\n*Searched {len(rag_response.collections_searched)} collection(s): {collections_text}*"
            if rag_response.total_results > 5:
                response_text += f"\n*Found {rag_response.total_results} relevant result(s) across your documents*"
        
        # Update thinking message with response
        thinking_msg.content = response_text
        await thinking_msg.update()
        
    except Exception as e:
        # Friendly error handling
        error_str = str(e).lower()
        
        # Check for token limit errors specifically
        if "length" in error_str or "token" in error_str or "400" in error_str:
            error_msg = """⚠️ **I encountered an issue with the response length**

It looks like there's too much information to process at once. Here's what you can try:

**Quick fixes:**
- Use `/clear` to clear our conversation history
- Ask a more specific question (this will retrieve fewer documents)
- Break your question into smaller parts

The system will automatically try to reduce context size in future queries."""
        elif "timeout" in error_str or "timed out" in error_str:
            error_msg = """⏱️ **The request took too long to process**

This might happen if:
- Your question is very complex
- There are many documents to search through
- The backend is temporarily busy

**What you can do:**
- Try asking a simpler or more specific question
- Wait a moment and try again
- Check if the backend service is running properly"""
        elif "not found" in error_str or "404" in error_str:
            error_msg = """🔍 **I couldn't find the information you're looking for**

**Possible reasons:**
- The documents might not contain information about this topic
- Your question might need to be rephrased
- The relevant documents might be in a different collection

**Try:**
- Rephrasing your question using different keywords
- Using `/collections` to see available collections
- Being more specific about what you're looking for"""
        else:
            error_msg = f"""😕 **I encountered an error while processing your question**

**Error details:** {str(e)[:200]}

**What you can try:**
- Rephrasing your question
- Checking if relevant documents are in the collections
- Using `/collections` to see available collections
- Verifying the backend API is running

If the problem persists, check the logs for more detailed information."""
        
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
- Provider: {config.LLM_PROVIDER.upper()}
- Model: {config.MODEL_NAME}
- Temperature: {config.TEMPERATURE} (low for accuracy)
- Max Tokens: {config.MAX_TOKENS}

**Retrieval Settings:**
- Max Results per Collection: {config.MAX_RESULTS_PER_COLLECTION}
- Max Total Results: {config.MAX_TOTAL_RESULTS}
- Min Similarity Score: {config.MIN_SIMILARITY_SCORE}
- Reranking: {'✅ Enabled' if config.ENABLE_RERANKING else '❌ Disabled'}
- Query Rewriting: {'✅ Enabled' if config.ENABLE_QUERY_REWRITING else '❌ Disabled'}
- Multi-Query Retrieval: {'✅ Enabled' if config.ENABLE_MULTI_QUERY else '❌ Disabled'}

**Accuracy Features:**
- ✅ Advanced Reranking (multi-factor scoring)
- ✅ Result Diversification (balanced document representation)
- ✅ Enhanced Prompt Engineering (cross-document synthesis)
- ✅ Conversation Memory (context-aware follow-ups)

**Backend API:**
- URL: {config.BACKEND_API_URL}
- Timeout: {config.BACKEND_API_TIMEOUT}s

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

