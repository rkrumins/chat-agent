"""
Production-Grade RAG Module for Multi-Collection Vector Database Queries
Built for Python 3.12 with Chainlit integration

This module provides RAG (Retrieval-Augmented Generation) capabilities
that interact with the Vector Database via the backend API, supporting:
- Querying across multiple collections simultaneously
- Handling 100s of documents per collection efficiently
- Production-ready error handling and logging
- Optimized retrieval for large-scale knowledge bases
"""

import os
import logging
import asyncio
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import httpx
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Container for retrieval results"""
    content: str
    metadata: Dict[str, Any]
    collection: str
    similarity_score: float
    document_id: str
    document_name: str


@dataclass
class ConversationMessage:
    """Container for conversation message"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    sources: List[RetrievalResult] = None
    query: str = None


@dataclass
class RAGResponse:
    """Container for RAG response"""
    answer: str
    sources: List[RetrievalResult]
    query: str
    collections_searched: List[str]
    total_results: int
    is_followup: bool = False
    expanded_query: str = None


class VectorDBClient:
    """Client for interacting with Vector Database backend API"""
    
    def __init__(self, api_base_url: str = None, timeout: int = 30):
        """
        Initialize VectorDB API client
        
        Args:
            api_base_url: Base URL for backend API (default: http://localhost:8000)
            timeout: Request timeout in seconds
        """
        self.api_base_url = api_base_url or os.getenv(
            "BACKEND_API_URL", 
            "http://localhost:8000"
        )
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=self.api_base_url,
            timeout=self.timeout,
            follow_redirects=True
        )
        logger.info(f"VectorDB client initialized with base URL: {self.api_base_url}")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def list_collections(self) -> List[Dict[str, Any]]:
        """List all available collections"""
        try:
            response = await self.client.get("/collections")
            response.raise_for_status()
            data = response.json()
            return data.get("collections", [])
        except Exception as e:
            logger.error(f"Error listing collections: {str(e)}")
            raise
    
    async def search_collection(
        self, 
        collection_name: str, 
        query: str, 
        n_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search a single collection
        
        Args:
            collection_name: Name of the collection to search
            query: Search query text
            n_results: Number of results to return
            
        Returns:
            List of search results with documents, metadata, and distances
        """
        try:
            response = await self.client.post(
                f"/collections/{collection_name}/search",
                params={"query": query, "n_results": n_results}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Collection '{collection_name}' not found")
                return []
            raise
        except Exception as e:
            logger.error(f"Error searching collection '{collection_name}': {str(e)}")
            raise
    
    async def search_multiple_collections(
        self,
        collection_names: List[str],
        query: str,
        n_results_per_collection: int = 10
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search multiple collections in parallel
        
        Args:
            collection_names: List of collection names to search
            query: Search query text
            n_results_per_collection: Number of results per collection
            
        Returns:
            Dictionary mapping collection names to their search results
        """
        if not collection_names:
            return {}
        
        # Search all collections in parallel
        tasks = [
            self.search_collection(col, query, n_results_per_collection)
            for col in collection_names
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results into dictionary
        collection_results = {}
        for collection_name, result in zip(collection_names, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Error searching collection '{collection_name}': {str(result)}"
                )
                collection_results[collection_name] = []
            else:
                collection_results[collection_name] = result
        
        return collection_results
    
    async def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics for a collection"""
        try:
            response = await self.client.get(f"/collections/{collection_name}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}")
            return {}


class ConversationMemory:
    """Manages conversation history and context"""
    
    def __init__(self, max_history: int = 10):
        """
        Initialize conversation memory
        
        Args:
            max_history: Maximum number of messages to keep in history
        """
        self.messages: List[ConversationMessage] = []
        self.max_history = max_history
        self.document_context: Dict[str, List[str]] = {}  # Track documents mentioned in conversation
    
    def add_message(self, message: ConversationMessage):
        """Add a message to conversation history"""
        self.messages.append(message)
        
        # Keep only recent history
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
        
        # Track document context
        if message.sources:
            for source in message.sources:
                doc_name = source.document_name
                if doc_name not in self.document_context:
                    self.document_context[doc_name] = []
                # Store key concepts from this document
                if message.content:
                    self.document_context[doc_name].append(message.content[:200])
    
    def get_recent_context(self, n_messages: int = 3) -> List[ConversationMessage]:
        """Get recent conversation context"""
        return self.messages[-n_messages:] if len(self.messages) > n_messages else self.messages
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation context"""
        if not self.messages:
            return ""
        
        summary_parts = []
        for msg in self.messages[-5:]:  # Last 5 messages
            summary_parts.append(f"{msg.role}: {msg.content[:150]}...")
        
        return "\n".join(summary_parts)
    
    def get_document_context_summary(self) -> str:
        """Get summary of documents mentioned in conversation"""
        if not self.document_context:
            return ""
        
        parts = []
        for doc_name, contexts in self.document_context.items():
            parts.append(f"- {doc_name}: {len(contexts)} references")
        
        return "\n".join(parts)
    
    def clear(self):
        """Clear conversation history"""
        self.messages = []
        self.document_context = {}


class RAGEngine:
    """Production-grade RAG engine for multi-collection queries with conversation support"""
    
    def __init__(
        self,
        vector_db_client: VectorDBClient,
        llm,
        max_results_per_collection: int = 10,
        max_total_results: int = 50,
        min_similarity_score: float = 0.0,
        enable_reranking: bool = True,
        enable_conversation: bool = True,
        enable_query_rewriting: bool = True,
        enable_multi_query: bool = True
    ):
        """
        Initialize RAG Engine
        
        Args:
            vector_db_client: VectorDBClient instance
            llm: LangChain LLM instance
            max_results_per_collection: Maximum results to retrieve per collection
            max_total_results: Maximum total results across all collections
            min_similarity_score: Minimum similarity score (0-1) to include results
            enable_reranking: Whether to rerank results by relevance
            enable_conversation: Whether to enable conversation memory and follow-up detection
            enable_query_rewriting: Whether to rewrite queries for better retrieval
            enable_multi_query: Whether to use multi-query retrieval
        """
        self.vector_db_client = vector_db_client
        self.llm = llm
        self.max_results_per_collection = max_results_per_collection
        self.max_total_results = max_total_results
        self.min_similarity_score = min_similarity_score
        self.enable_reranking = enable_reranking
        self.enable_conversation = enable_conversation
        self.enable_query_rewriting = enable_query_rewriting
        self.enable_multi_query = enable_multi_query
        self.conversation_memory = ConversationMemory(max_history=5) if enable_conversation else None  # Reduced from 10 to 5
        logger.info(
            f"RAG Engine initialized - Reranking: {enable_reranking}, "
            f"Query Rewriting: {enable_query_rewriting}, Multi-Query: {enable_multi_query}"
        )
    
    def _convert_distance_to_similarity(self, distance: float) -> float:
        """
        Convert ChromaDB distance to similarity score
        
        ChromaDB uses cosine distance (0 = identical, 1 = orthogonal)
        We convert to similarity (1 = identical, 0 = orthogonal)
        """
        # Clamp distance to [0, 1] and convert to similarity
        distance = max(0.0, min(1.0, distance))
        similarity = 1.0 - distance
        return similarity
    
    def _extract_retrieval_results(
        self,
        search_results: Dict[str, List[Dict[str, Any]]]
    ) -> List[RetrievalResult]:
        """
        Extract and normalize retrieval results from API responses
        
        Args:
            search_results: Dictionary mapping collection names to search results
            
        Returns:
            List of RetrievalResult objects
        """
        all_results = []
        
        for collection_name, results in search_results.items():
            if not results:
                continue
            
            for result in results:
                # Extract fields from API response
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                distance = result.get("distance", 1.0)
                
                # Convert distance to similarity score
                similarity = self._convert_distance_to_similarity(distance)
                
                # Filter by minimum similarity
                if similarity < self.min_similarity_score:
                    continue
                
                # Extract document information from metadata
                document_name = metadata.get("name", "Unknown Document")
                document_id = result.get("id", "")
                
                # Skip chunks, only use document-level results for main retrieval
                # (chunks are already embedded in the content)
                if metadata.get("is_chunk", False):
                    # For chunks, we still include them but mark them appropriately
                    parent_name = metadata.get("parent_name") or metadata.get("name", "Unknown")
                    document_name = f"{parent_name} (chunk {metadata.get('chunk_number', '?')})"
                
                retrieval_result = RetrievalResult(
                    content=content,
                    metadata=metadata,
                    collection=collection_name,
                    similarity_score=similarity,
                    document_id=document_id,
                    document_name=document_name
                )
                
                all_results.append(retrieval_result)
        
        return all_results
    
    def _rerank_results(
        self,
        results: List[RetrievalResult],
        query: str,
        top_k: int = None
    ) -> List[RetrievalResult]:
        """
        Advanced reranking by relevance to query with multiple factors
        
        Args:
            results: List of retrieval results
            query: Original query
            top_k: Number of top results to return
            
        Returns:
            Reranked list of results
        """
        if not self.enable_reranking or not results:
            # Just sort by similarity and return top_k
            sorted_results = sorted(
                results,
                key=lambda x: x.similarity_score,
                reverse=True
            )
            return sorted_results[:top_k] if top_k else sorted_results
        
        # Extract query terms (remove stopwords)
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'what', 'how', 'why', 'when', 'where', 'who'}
        query_words = query.lower().split()
        query_terms = set(w for w in query_words if len(w) > 2 and w not in stopwords)
        
        def calculate_advanced_rerank_score(result: RetrievalResult) -> float:
            base_score = result.similarity_score
            content_lower = result.content.lower()
            metadata = result.metadata
            
            # Factor 1: Query term frequency (30%)
            term_matches = sum(1 for term in query_terms if term in content_lower)
            term_frequency = term_matches / len(query_terms) if query_terms else 0
            
            # Factor 2: Exact phrase matches (20%)
            phrase_score = 0
            if len(query_words) > 1:
                # Check for 2-3 word phrases
                for i in range(len(query_words) - 1):
                    phrase = ' '.join(query_words[i:i+2])
                    if phrase in content_lower:
                        phrase_score += 0.1
                phrase_score = min(phrase_score, 1.0)
            
            # Factor 3: Document name relevance (10%)
            doc_name_score = 0
            doc_name_lower = result.document_name.lower()
            for term in query_terms:
                if term in doc_name_lower:
                    doc_name_score += 0.1
            doc_name_score = min(doc_name_score, 1.0)
            
            # Factor 4: Metadata relevance (10%)
            metadata_score = 0
            if metadata:
                # Check tags, purpose, document_type
                for key in ['tags', 'purpose', 'document_type']:
                    if key in metadata:
                        value = str(metadata[key]).lower()
                        for term in query_terms:
                            if term in value:
                                metadata_score += 0.05
            metadata_score = min(metadata_score, 1.0)
            
            # Factor 5: Content quality (10%)
            # Prefer longer, more complete chunks
            content_length = len(result.content)
            quality_score = min(content_length / 500, 1.0)  # Normalize to 500 chars
            
            # Factor 6: Position in document (10%) - prefer earlier chunks
            position_score = 1.0
            if 'chunk_number' in metadata and 'total_chunks' in metadata:
                chunk_num = metadata.get('chunk_number', 1)
                total_chunks = metadata.get('total_chunks', 1)
                if total_chunks > 1:
                    position_score = 1.0 - (chunk_num / total_chunks) * 0.5  # Earlier chunks get higher score
            
            # Combine all factors with weights
            final_score = (
                base_score * 0.30 +           # Base similarity (30%)
                term_frequency * 0.20 +       # Term frequency (20%)
                phrase_score * 0.15 +         # Phrase matches (15%)
                doc_name_score * 0.10 +       # Document name (10%)
                metadata_score * 0.10 +       # Metadata (10%)
                quality_score * 0.10 +        # Content quality (10%)
                position_score * 0.05         # Position (5%)
            )
            
            return final_score
        
        # Calculate rerank scores
        scored_results = [(calculate_advanced_rerank_score(r), r) for r in results]
        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        reranked = [r for score, r in scored_results]
        
        return reranked[:top_k] if top_k else reranked
    
    def _diversify_results(
        self,
        results: List[RetrievalResult],
        max_per_document: int = 3
    ) -> List[RetrievalResult]:
        """
        Diversify results to ensure representation from different documents
        Prevents over-representation from a single document
        
        Args:
            results: List of retrieval results
            max_per_document: Maximum results per document
            
        Returns:
            Diversified list of results
        """
        if not results:
            return results
        
        # Group by document
        doc_groups = defaultdict(list)
        for result in results:
            doc_key = f"{result.collection}::{result.document_name}"
            doc_groups[doc_key].append(result)
        
        # Select top results from each document
        diversified = []
        seen_docs = set()
        
        # First pass: take top results from each document
        for doc_key, doc_results in doc_groups.items():
            # Take top max_per_document from each document
            top_from_doc = doc_results[:max_per_document]
            diversified.extend(top_from_doc)
            seen_docs.add(doc_key)
        
        # Second pass: fill remaining slots with best remaining results
        remaining = [r for r in results if r not in diversified]
        remaining.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Add remaining results until we have enough diversity or run out
        max_total = len(results)
        while len(diversified) < max_total and remaining:
            for result in remaining[:]:
                doc_key = f"{result.collection}::{result.document_name}"
                doc_count = sum(1 for r in diversified if f"{r.collection}::{r.document_name}" == doc_key)
                
                if doc_count < max_per_document:
                    diversified.append(result)
                    remaining.remove(result)
                    break
            else:
                # If we can't add more diverse results, add the best remaining
                if remaining:
                    diversified.append(remaining.pop(0))
                else:
                    break
        
        return diversified
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count (rough approximation: 1 token ≈ 4 characters)
        This is a conservative estimate for English text
        """
        return len(text) // 4
    
    def _format_context(
        self,
        results: List[RetrievalResult],
        max_tokens: int = 4000,  # Reduced from 8000 chars to ~4000 tokens
        group_by_document: bool = True
    ) -> str:
        """
        Format retrieval results into context string for LLM
        
        Args:
            results: List of retrieval results
            max_tokens: Maximum tokens for formatted context (conservative limit)
            group_by_document: Whether to group chunks by document for better context
            
        Returns:
            Formatted context string
        """
        if not results:
            return "No relevant documents found."
        
        # Convert max_tokens to approximate character limit (conservative: 4 chars per token)
        max_length = max_tokens * 3  # Use 3 chars per token for safety margin
        
        if group_by_document:
            # Group results by document for better synthesis
            doc_groups = defaultdict(list)
            for result in results:
                doc_key = f"{result.collection}::{result.document_name}"
                doc_groups[doc_key].append(result)
            
            formatted_parts = []
            current_length = 0
            
            for doc_key, doc_results in doc_groups.items():
                collection, doc_name = doc_key.split("::", 1)
                
                # Format document header
                metadata = doc_results[0].metadata
                version = metadata.get("version", "")
                version_str = f" (v{version})" if version else ""
                doc_header = f"[Document: {doc_name}{version_str} | Collection: {collection}]\n"
                
                # Combine all chunks from this document
                doc_content_parts = []
                for result in doc_results:
                    # Remove contextual prefixes if present (they're already in the header)
                    content = result.content
                    # Remove [DOCUMENT_TYPE: ...] and [DOCUMENT_NAME: ...] prefixes if present
                    lines = content.split('\n')
                    filtered_lines = []
                    for line in lines:
                        if not (line.startswith('[DOCUMENT_TYPE:') or 
                                line.startswith('[DOCUMENT_NAME:') or
                                line.startswith('[CHUNK:') or
                                line.startswith('[PURPOSE:') or
                                line.startswith('[TAGS:') or
                                line.strip() == ''):
                            filtered_lines.append(line)
                            break
                    if filtered_lines:
                        # Include remaining lines
                        content = '\n'.join(lines[lines.index(filtered_lines[0]):])
                    doc_content_parts.append(content)
                
                doc_content = "\n\n--- [Next section from same document] ---\n\n".join(doc_content_parts)
                
                # Build complete document entry
                context_entry = f"{doc_header}\n{doc_content}"
                
                entry_length = len(context_entry)
                
                # Check if adding this entry would exceed max_length
                if current_length + entry_length > max_length and formatted_parts:
                    break
                
                formatted_parts.append(context_entry)
                current_length += entry_length
        else:
            # Original format (one entry per result)
            formatted_parts = []
            current_length = 0
            
            for i, result in enumerate(results, 1):
                metadata = result.metadata
                doc_name = result.document_name
                version = metadata.get("version", "")
                version_str = f" (v{version})" if version else ""
                collection_str = f" [Collection: {result.collection}]"
                
                context_entry = f"[Document {i}: {doc_name}{version_str}{collection_str}]\n"
                context_entry += result.content
                
                entry_length = len(context_entry)
                
                if current_length + entry_length > max_length and formatted_parts:
                    break
                
                formatted_parts.append(context_entry)
                current_length += entry_length
        
        # Use shorter separator to save tokens
        separator = "\n\n" + "="*50 + "\n\n"
        formatted_context = separator.join(formatted_parts)
        
        # Final safety check: if context is still too long, truncate
        estimated_tokens = self._estimate_tokens(formatted_context)
        if estimated_tokens > max_tokens:
            # Truncate to fit within token limit
            max_chars = max_tokens * 3  # Conservative: 3 chars per token
            if len(formatted_context) > max_chars:
                formatted_context = formatted_context[:max_chars] + "\n\n[Context truncated due to length limits...]"
                logger.warning(f"Context truncated from {estimated_tokens} to ~{max_tokens} tokens")
        
        return formatted_context
    
    async def _rewrite_query_for_retrieval(self, query: str) -> str:
        """
        Rewrite query to be more effective for retrieval using LLM
        Expands queries with synonyms, related terms, and key concepts
        """
        if not self.llm:
            return query
        
        try:
            rewrite_prompt = """Rewrite the following user question to be more effective for semantic search in a document database. 

Your goal is to:
1. Extract key concepts and terms
2. Add relevant synonyms and related terms
3. Make the query more specific and detailed
4. Preserve the original intent

Return ONLY the rewritten query, nothing else. Keep it concise (under 100 words).

User question: {query}

Rewritten query for better retrieval:"""
            
            # Try to use LLM for query rewriting
            try:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.output_parsers import StrOutputParser
                
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", "You are a query optimization expert. Rewrite queries to be more effective for semantic search."),
                    ("human", rewrite_prompt)
                ])
                
                chain = prompt_template | self.llm | StrOutputParser()
                
                if hasattr(chain, "ainvoke"):
                    rewritten = await chain.ainvoke({"query": query})
                else:
                    loop = asyncio.get_event_loop()
                    rewritten = await loop.run_in_executor(
                        None,
                        chain.invoke,
                        {"query": query}
                    )
                
                rewritten = rewritten.strip()
                if rewritten and len(rewritten) > 10:
                    logger.info(f"Query rewritten: '{query[:50]}...' -> '{rewritten[:50]}...'")
                    return rewritten
            except Exception as e:
                logger.warning(f"Query rewrite with LLM failed: {str(e)}, using simple expansion")
            
            # Fallback to simple expansion
            return self._simple_query_expansion(query)
            
        except Exception as e:
            logger.warning(f"Query rewrite failed: {str(e)}, using original")
            return query
    
    def _simple_query_expansion(self, query: str) -> str:
        """
        Simple query expansion without LLM - adds common synonyms and terms
        """
        # Extract key terms
        words = query.lower().split()
        
        # Common synonym expansions
        expansions = {
            "how": ["method", "approach", "way", "technique"],
            "what": ["concept", "idea", "principle", "definition"],
            "why": ["reason", "cause", "purpose", "rationale"],
            "when": ["time", "timing", "schedule", "duration"],
            "where": ["location", "place", "position", "context"],
            "compare": ["difference", "similarity", "contrast", "relation"],
            "explain": ["describe", "clarify", "detail", "define"],
        }
        
        # Add expansions for key words
        expanded_terms = []
        for word in words:
            expanded_terms.append(word)
            if word in expansions:
                expanded_terms.extend(expansions[word][:2])  # Add 2 synonyms
        
        # Reconstruct query with expansions
        expanded_query = query
        if len(expanded_terms) > len(words):
            expanded_query = f"{query} {' '.join(set(expanded_terms) - set(words))}"
        
        return expanded_query
    
    async def _generate_multiple_queries(self, query: str, n_queries: int = 3) -> List[str]:
        """
        Generate multiple query variations for better retrieval coverage
        """
        queries = [query]  # Always include original
        
        if n_queries <= 1:
            return queries
        
        try:
            # Generate query variations
            variation_prompt = """Generate {n} different ways to search for the same information as this question. 
Each variation should use different wording, synonyms, or focus on different aspects.
Return only the queries, one per line, no numbering.

Original question: {query}

Variations:"""
            
            try:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.output_parsers import StrOutputParser
                
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", "You are a search query generation expert. Create diverse query variations."),
                    ("human", variation_prompt)
                ])
                
                chain = prompt_template | self.llm | StrOutputParser()
                
                if hasattr(chain, "ainvoke"):
                    variations = await chain.ainvoke({"query": query, "n": n_queries - 1})
                else:
                    loop = asyncio.get_event_loop()
                    variations = await loop.run_in_executor(
                        None,
                        chain.invoke,
                        {"query": query, "n": n_queries - 1}
                    )
                
                # Parse variations
                variation_lines = [q.strip() for q in variations.split('\n') if q.strip()]
                variation_lines = [q for q in variation_lines if not q.startswith(('1.', '2.', '3.', '-', '*'))]
                
                # Add valid variations
                for var in variation_lines[:n_queries - 1]:
                    if var and len(var) > 10 and var.lower() != query.lower():
                        queries.append(var)
                
            except Exception as e:
                logger.warning(f"Multi-query generation failed: {str(e)}")
                # Fallback: simple variations
                queries.extend(self._simple_query_variations(query, n_queries - 1))
        
        except Exception as e:
            logger.warning(f"Error generating query variations: {str(e)}")
        
        return queries[:n_queries]
    
    def _simple_query_variations(self, query: str, n: int) -> List[str]:
        """Simple query variations without LLM"""
        variations = []
        
        # Question form variations
        if query.endswith('?'):
            variations.append(query.replace('?', '').strip())
            variations.append(f"explain {query.lower().replace('?', '')}")
        
        # Add "what is" prefix if not present
        if not query.lower().startswith(('what', 'how', 'why', 'when', 'where', 'who')):
            variations.append(f"what is {query.lower()}")
        
        return variations[:n]
    
    def _detect_followup_question(self, query: str) -> bool:
        """
        Detect if this is a follow-up question based on conversation history
        
        Args:
            query: Current query
            
        Returns:
            True if this appears to be a follow-up question
        """
        if not self.enable_conversation or not self.conversation_memory or not self.conversation_memory.messages:
            return False
        
        # Check for follow-up indicators
        followup_indicators = [
            "what about", "how about", "and", "also", "what if", "can you",
            "what's", "explain more", "tell me more", "another", "different",
            "similar", "compare", "difference", "similarity", "relate", "connect"
        ]
        
        query_lower = query.lower()
        has_followup_indicator = any(indicator in query_lower for indicator in followup_indicators)
        
        # Check if query references previous documents or topics
        recent_context = self.conversation_memory.get_recent_context(3)
        has_previous_context = len(recent_context) > 0
        
        return has_followup_indicator or (has_previous_context and len(query.split()) < 10)
    
    async def _expand_query_with_context(self, query: str) -> str:
        """
        Expand query with conversation context for better retrieval
        
        Args:
            query: Original query
            
        Returns:
            Expanded query with context
        """
        if not self.enable_conversation or not self.conversation_memory:
            return query
        
        # Get recent conversation context
        recent_messages = self.conversation_memory.get_recent_context(3)
        if not recent_messages:
            return query
        
        # Build context string
        context_parts = []
        for msg in recent_messages:
            if msg.role == "user":
                context_parts.append(f"Previous question: {msg.content[:200]}")
            elif msg.role == "assistant":
                # Extract key topics from previous answer
                context_parts.append(f"Previous answer mentioned: {msg.content[:200]}")
        
        if context_parts:
            context_str = "\n".join(context_parts)
            expanded_query = f"{query}\n\nContext from conversation:\n{context_str}"
            logger.info(f"Expanded query with conversation context: {expanded_query[:200]}...")
            return expanded_query
        
        return query
    
    async def retrieve(
        self,
        query: str,
        collection_names: List[str] = None,
        max_results: int = None,
        use_conversation_context: bool = True,
        use_multi_query: bool = True
    ) -> Tuple[List[RetrievalResult], List[str]]:
        """
        Retrieve relevant documents from vector database with advanced techniques
        
        Args:
            query: Search query
            collection_names: List of collection names to search (None = all collections)
            max_results: Maximum number of results to return
            use_conversation_context: Whether to use conversation context
            use_multi_query: Whether to use multi-query retrieval
            
        Returns:
            Tuple of (retrieval_results, collections_searched)
        """
        # Step 1: Rewrite query for better retrieval (if enabled)
        if not self.enable_query_rewriting:
            rewritten_query = query
        else:
            rewritten_query = await self._rewrite_query_for_retrieval(query)
        
        # Step 2: Expand query with conversation context if enabled
        if use_conversation_context and self.enable_conversation:
            expanded_query = await self._expand_query_with_context(rewritten_query)
        else:
            expanded_query = rewritten_query
        
        # If no collections specified, get all collections
        if collection_names is None:
            collections = await self.vector_db_client.list_collections()
            collection_names = [col["name"] for col in collections]
        
        if not collection_names:
            logger.warning("No collections available for search")
            return [], []
        
        logger.info(
            f"Searching {len(collection_names)} collection(s) with query: '{query[:100]}...'"
        )
        
        # Step 3: Multi-query retrieval (if enabled)
        all_results = []
        if use_multi_query and self.enable_multi_query:
            # Generate multiple query variations
            queries = await self._generate_multiple_queries(expanded_query, n_queries=3)
            logger.info(f"Using {len(queries)} query variations for retrieval")
            
            # Search with each query variation
            all_search_results = []
            for q in queries:
                search_results = await self.vector_db_client.search_multiple_collections(
                    collection_names=collection_names,
                    query=q,
                    n_results_per_collection=self.max_results_per_collection // 2  # Reduce per query to account for multiple queries
                )
                all_search_results.append(search_results)
            
            # Combine results from all queries
            combined_results = {}
            for search_results in all_search_results:
                for collection, results in search_results.items():
                    if collection not in combined_results:
                        combined_results[collection] = []
                    combined_results[collection].extend(results)
            
            # Extract and normalize
            all_results = self._extract_retrieval_results(combined_results)
            
            # Deduplicate by document ID
            seen_ids = set()
            deduplicated_results = []
            for result in all_results:
                result_id = f"{result.collection}::{result.document_id}::{result.content[:50]}"
                if result_id not in seen_ids:
                    seen_ids.add(result_id)
                    deduplicated_results.append(result)
            all_results = deduplicated_results
        else:
            # Single query retrieval
            search_results = await self.vector_db_client.search_multiple_collections(
                collection_names=collection_names,
                query=expanded_query,
                n_results_per_collection=self.max_results_per_collection
            )
            all_results = self._extract_retrieval_results(search_results)
        
        # Step 4: Filter by minimum similarity
        filtered_results = [
            r for r in all_results 
            if r.similarity_score >= self.min_similarity_score
        ]
        
        # Step 5: Diversify results (ensure representation from different documents)
        max_total = max_results or self.max_total_results
        diversified_results = self._diversify_results(
            filtered_results,
            max_per_document=3
        )
        
        # Step 6: Rerank results with advanced scoring
        reranked_results = self._rerank_results(
            diversified_results,
            query,
            top_k=max_total
        )
        
        logger.info(
            f"Retrieved {len(reranked_results)} results from {len(collection_names)} collection(s) "
            f"(from {len(all_results)} initial results)"
        )
        
        return reranked_results, collection_names
    
    async def generate_answer(
        self,
        query: str,
        context: str,
        system_prompt: str = None
    ) -> str:
        """
        Generate answer using LLM with retrieved context
        
        Args:
            query: User query
            context: Formatted context from retrieval
            system_prompt: Optional custom system prompt
            
        Returns:
            Generated answer string
        """
        try:
            # Try to use LangChain's ChatPromptTemplate if available
            try:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.output_parsers import StrOutputParser
                
                if system_prompt is None:
                    system_prompt = """You are an expert assistant that provides accurate, detailed answers based on the given context from documents.

Your responses must:
1. Be based ONLY on the information provided in the context
2. Quote specific sections from the context to support your answers
3. Cite the document name and collection when referencing information (e.g., "According to [Document 1: filename.pdf] in the [collection] collection...")
4. If the context doesn't fully answer the question, clearly state what information is missing
5. If you're uncertain, say so rather than guessing
6. Be specific and detailed - avoid vague or generic responses
7. If multiple documents contain relevant information, synthesize the information coherently
8. When information comes from multiple collections, note which collection each piece of information comes from

CONTEXT FROM DOCUMENTS:
{context}

QUESTION: {question}

Provide a comprehensive answer based on the context above. Include citations to document names and collections where applicable."""
                
                # Get conversation context if available (truncated more aggressively)
                conversation_context_str = ""
                if self.enable_conversation and self.conversation_memory:
                    recent_context = self.conversation_memory.get_recent_context(2)  # Reduced from 3 to 2
                    if recent_context:
                        conv_parts = []
                        for msg in recent_context:
                            if msg.role == "user":
                                conv_parts.append(f"User: {msg.content[:100]}")  # Reduced from 200 to 100
                            elif msg.role == "assistant":
                                conv_parts.append(f"Assistant: {msg.content[:100]}")  # Reduced from 200 to 100
                        if conv_parts:
                            conversation_context_str = "CONVERSATION CONTEXT:\n" + "\n".join(conv_parts) + "\n\n"
                
                # Create prompt template
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("human", "{question}")
                ])
                
                # Create chain
                chain = prompt_template | self.llm | StrOutputParser()
                
                # Prepare prompt variables
                prompt_vars = {
                    "context": context,
                    "question": query,
                    "conversation_context": conversation_context_str
                }
                
                # Invoke chain
                if hasattr(chain, "ainvoke"):
                    response = await chain.ainvoke(prompt_vars)
                else:
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None, 
                        chain.invoke,
                        prompt_vars
                    )
                
                return response
                
            except ImportError:
                # Fallback to simple string prompt if ChatPromptTemplate not available
                logger.warning("ChatPromptTemplate not available, using simple prompt")
                
                # Get conversation context if available (truncated more aggressively)
                conversation_context_str = ""
                if self.enable_conversation and self.conversation_memory:
                    recent_context = self.conversation_memory.get_recent_context(2)  # Reduced from 3 to 2
                    if recent_context:
                        conv_parts = []
                        for msg in recent_context:
                            if msg.role == "user":
                                conv_parts.append(f"User: {msg.content[:100]}")  # Reduced from 200 to 100
                            elif msg.role == "assistant":
                                conv_parts.append(f"Assistant: {msg.content[:100]}")  # Reduced from 200 to 100
                        if conv_parts:
                            conversation_context_str = "\n\nCONVERSATION CONTEXT:\n" + "\n".join(conv_parts) + "\n"
                
                if system_prompt is None:
                    system_prompt = """You are an expert research assistant with exceptional ability to analyze, synthesize, and connect information across multiple documents. Your expertise lies in:

1. **Accurate Information Extraction**: Extract precise, factual information from the provided context
2. **Cross-Document Synthesis**: Identify relationships, patterns, and connections between concepts from different documents
3. **Critical Analysis**: Compare and contrast different perspectives, methodologies, and approaches
4. **Clear Communication**: Present complex information in a structured, easy-to-understand manner

**Answer Guidelines:**

**Accuracy & Evidence:**
- Base your answer ONLY on the information provided in the context
- Quote specific sections verbatim when making key points (use quotation marks)
- Cite the exact document name and collection when referencing information
- If information is missing or unclear, explicitly state what is missing
- If you're uncertain, say so rather than guessing or making assumptions

**Synthesis & Analysis:**
- When multiple documents are mentioned, actively identify:
  * Common themes and shared concepts
  * Differences in approach, perspective, or methodology
  * Relationships and connections between ideas
  * Patterns that emerge across documents
- For questions about multiple documents (e.g., "Atomic Habits and Clean Code"), provide:
  * A comprehensive comparison
  * Both documents' perspectives side-by-side
  * Clear identification of which document each concept comes from
  * Analysis of how concepts relate or differ

**Structure & Clarity:**
- Organize your answer logically (use headings, bullet points, or numbered lists when helpful)
- Start with a brief summary if the answer is complex
- Use specific examples and quotes from the context
- Be detailed and specific - avoid vague or generic statements
- Connect ideas coherently to show understanding

**Context Awareness:**
- Use conversation context to understand follow-up questions
- Reference previous points naturally when relevant
- Maintain consistency with earlier answers in the conversation

**Cross-Document Examples:**
- If asked "What do both books say about X?", structure your answer:
  * Document 1's perspective on X
  * Document 2's perspective on X
  * Comparison and synthesis
- If asked "Compare X and Y", provide:
  * What X is (from context)
  * What Y is (from context)
  * How they relate, differ, or complement each other

CONTEXT FROM DOCUMENTS:
{context}{conversation_context}

QUESTION: {question}

Provide a comprehensive, well-structured answer that synthesizes information across documents when applicable. Use specific quotes and citations. Be thorough, accurate, and insightful."""
                
                # Format prompt with conversation context
                prompt = system_prompt.format(
                    context=context, 
                    question=query,
                    conversation_context=conversation_context_str
                )
                
                # Use LangChain's async invoke if available, otherwise use sync
                if hasattr(self.llm, "ainvoke"):
                    response = await self.llm.ainvoke(prompt)
                elif hasattr(self.llm, "invoke"):
                    # Run sync invoke in thread pool for async compatibility
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(None, self.llm.invoke, prompt)
                else:
                    raise ValueError("LLM does not support invoke or ainvoke methods")
                
                # Extract text from response
                if hasattr(response, "content"):
                    return response.content
                elif isinstance(response, str):
                    return response
                else:
                    return str(response)
                
        except Exception as e:
            logger.error(f"Error generating answer: {str(e)}")
            raise
    
    async def query(
        self,
        query: str,
        collection_names: List[str] = None,
        max_results: int = None,
        system_prompt: str = None
    ) -> RAGResponse:
        """
        Complete RAG pipeline: retrieve and generate with conversation awareness
        
        Args:
            query: User query
            collection_names: List of collection names to search (None = all collections)
            max_results: Maximum number of results to retrieve
            system_prompt: Optional custom system prompt
            
        Returns:
            RAGResponse with answer, sources, and metadata
        """
        # Step 0: Detect if this is a follow-up question
        is_followup = self._detect_followup_question(query) if self.enable_conversation else False
        
        # Step 1: Retrieve relevant documents (with conversation context expansion)
        results, collections_searched = await self.retrieve(
            query=query,
            collection_names=collection_names,
            max_results=max_results,
            use_conversation_context=True
        )
        
        # Step 2: Format context (grouped by document for better synthesis)
        # Use conservative token limit to avoid exceeding LLM limits
        # Account for: system prompt (~500 tokens) + conversation context (~200 tokens) + query (~50 tokens) + response (~500 tokens)
        # Leave ~4000 tokens for document context (conservative limit)
        context = self._format_context(results, max_tokens=4000, group_by_document=True)
        
        # Step 3: Generate answer with conversation context
        answer = await self.generate_answer(
            query=query,
            context=context,
            system_prompt=system_prompt
        )
        
        # Step 4: Store in conversation memory
        if self.enable_conversation and self.conversation_memory:
            # Add user message
            user_msg = ConversationMessage(
                role="user",
                content=query,
                timestamp=datetime.now(),
                query=query
            )
            self.conversation_memory.add_message(user_msg)
            
            # Add assistant message
            assistant_msg = ConversationMessage(
                role="assistant",
                content=answer,
                timestamp=datetime.now(),
                sources=results
            )
            self.conversation_memory.add_message(assistant_msg)
        
        # Step 5: Build response
        return RAGResponse(
            answer=answer,
            sources=results,
            query=query,
            collections_searched=collections_searched,
            total_results=len(results),
            is_followup=is_followup
        )


class RAGSessionManager:
    """Manages RAG sessions for Chainlit integration"""
    
    def __init__(self, rag_engine: RAGEngine):
        """
        Initialize session manager
        
        Args:
            rag_engine: RAGEngine instance
        """
        self.rag_engine = rag_engine
        self.default_collections: List[str] = []
        logger.info("RAG Session Manager initialized")
    
    def clear_conversation(self):
        """Clear conversation history"""
        if self.rag_engine.conversation_memory:
            self.rag_engine.conversation_memory.clear()
            logger.info("Conversation history cleared")
    
    def get_conversation_summary(self) -> str:
        """Get summary of current conversation"""
        if self.rag_engine.conversation_memory:
            return self.rag_engine.conversation_memory.get_conversation_summary()
        return ""
    
    def set_default_collections(self, collection_names: List[str]):
        """Set default collections for queries"""
        self.default_collections = collection_names
        logger.info(f"Default collections set to: {collection_names}")
    
    async def query(
        self,
        query: str,
        collection_names: List[str] = None,
        use_defaults: bool = True
    ) -> RAGResponse:
        """
        Execute RAG query with session defaults
        
        Args:
            query: User query
            collection_names: Specific collections to search (overrides defaults)
            use_defaults: Whether to use default collections if none specified
            
        Returns:
            RAGResponse
        """
        # Determine which collections to search
        if collection_names is not None:
            collections_to_search = collection_names
        elif use_defaults and self.default_collections:
            collections_to_search = self.default_collections
        else:
            collections_to_search = None  # Search all collections
        
        return await self.rag_engine.query(
            query=query,
            collection_names=collections_to_search
        )

