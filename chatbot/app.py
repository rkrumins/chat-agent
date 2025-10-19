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


def get_vectorstore(collection_name: Optional[str] = None):
    """Initialize ChromaDB vector store"""
    try:
        # Use HuggingFace embeddings (same as ChromaDB default)
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        if collection_name:
            vectorstore = Chroma(
                collection_name=collection_name,
                embedding_function=embeddings,
                persist_directory=CHROMA_DB_PATH
            )
        else:
            # Load default collection or first available
            vectorstore = Chroma(
                embedding_function=embeddings,
                persist_directory=CHROMA_DB_PATH
            )
        
        logger.info(f"Loaded vector store from {CHROMA_DB_PATH}")
        return vectorstore
    except Exception as e:
        logger.error(f"Error loading vector store: {str(e)}")
        raise


def create_qa_chain(vectorstore, llm):
    """Create RAG chain using modern LangChain LCEL"""
    
    # Custom prompt template
    prompt = ChatPromptTemplate.from_template("""You are a helpful AI assistant that answers questions based on the provided context from documents.

Context from documents:
{context}

Question: {question}

Instructions:
- Answer based primarily on the provided context
- If the context doesn't contain enough information, say so
- Be concise but comprehensive
- Cite specific details from the context when relevant
- If asked about something not in the context, acknowledge the limitation

Answer:""")
    
    # Get retriever
    retriever = vectorstore.as_retriever(
        search_kwargs={"k": 5}  # Return top 5 relevant chunks
    )
    
    # Format retrieved documents
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)
    
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
        
        await cl.Message(
            content=f"✅ Ready! Using **{LLM_PROVIDER.upper()}** with collection **{cl.user_session.get('current_collection')}**\n\nAsk me anything!"
        ).send()
        
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
    
    # Handle special commands
    if user_message.startswith("/"):
        await handle_command(user_message)
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
        # Get source documents first (using modern API)
        source_documents = await cl.make_async(retriever.invoke)(user_message)
        
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
        info_text = f"""**⚙️ Current Configuration:**

- **LLM Provider:** {LLM_PROVIDER.upper()}
- **Model:** {MODEL_NAME}
- **Collection:** {current_collection}
- **Database Path:** {CHROMA_DB_PATH}
- **Temperature:** {TEMPERATURE}
- **Max Tokens:** {MAX_TOKENS}
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
            # Reload vector store with new collection
            vectorstore = get_vectorstore(collection_name)
            llm = cl.user_session.get("llm")
            qa_chain, retriever = create_qa_chain(vectorstore, llm)
            
            # Update session
            cl.user_session.set("qa_chain", qa_chain)
            cl.user_session.set("retriever", retriever)
            cl.user_session.set("vectorstore", vectorstore)
            cl.user_session.set("current_collection", collection_name)
            
            await cl.Message(
                content=f"✅ Switched to collection: **{collection_name}**"
            ).send()
            
        except Exception as e:
            await cl.Message(
                content=f"❌ Error switching collection: {str(e)}"
            ).send()
    
    else:
        help_text = """**Available Commands:**

- `/info` - Show current configuration
- `/collections` - List available collections
- `/switch <name>` - Switch to a different collection

💡 Just type your question to chat with the documents!"""
        
        await cl.Message(content=help_text).send()


if __name__ == "__main__":
    # This is for running with: chainlit run app.py
    pass

