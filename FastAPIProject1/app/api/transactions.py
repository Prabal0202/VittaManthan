"""
Transaction query endpoints
"""

import re
import logging
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    RAGRequest,
    IngestRequest,
    IngestResponse,
    PromptRequest,
    RAGResponse
)
from app.services.rag_service import RAGService
from app.utils.data_store import get_ingested_data, set_ingested_data, has_ingested_data
from app.utils.formatters import format_transaction_for_api
from app.utils.filters import extract_filters_from_query, apply_filters
from app.utils.query_mode import detect_query_mode
from app.utils.cache import generate_query_id, get_cached_query, cache_query_results
from app.utils.chat_history import save_chat_interaction

logger = logging.getLogger(__name__)

router = APIRouter()

# Global references to models (will be set by main app)
embeddings_model = None
llm = None
llm_streaming = None


def set_models(emb_model, llm_model, llm_stream=None):
    """Set global model references"""
    global embeddings_model, llm, llm_streaming
    embeddings_model = emb_model
    llm = llm_model
    llm_streaming = llm_stream


@router.post("/query", response_model=RAGResponse)
async def query_transactions(request: RAGRequest):
    """
    Main endpoint: Accept context data and prompt, return LLM response

    This endpoint:
    1. Receives transaction data (context_data) and user question (prompt)
    2. Creates vector embeddings from the transaction data
    3. Applies filters based on the question
    4. Uses LLM to generate natural language response
    5. Returns paginated results with statistics
    """
    if not embeddings_model or not llm:
        raise HTTPException(status_code=503, detail="Models not initialized")

    try:
        logger.info(f"Processing query: {request.prompt}")
        logger.info(f"Context data: {len(request.context_data)} transactions")

        # Initialize RAG service
        rag_service = RAGService(embeddings_model, llm)

        # Prepare documents
        documents = request.context_data

        # Create vector store
        logger.info("Creating vector store...")
        vectorstore, langchain_docs = rag_service.create_vector_store(documents)

        # Extract filters
        filters = extract_filters_from_query(request.prompt)
        logger.info(f"Extracted filters: {filters}")

        # Detect query mode
        mode = detect_query_mode(request.prompt, documents)
        if request.use_full_data is not None:
            mode = "SMART_FULL" if request.use_full_data else "VECTOR_SEARCH"

        logger.info(f"Query mode: {mode}")

        # Generate unique query ID
        query_id = generate_query_id(request.prompt, filters)

        # Prepare response
        response_data = {
            "query_id": query_id,
            "mode": mode,
            "matching_transactions_count": 0,
            "filters_applied": None,
            "answer": "",
            "transactions": None,
            "pagination": None,
            "statistics": None
        }

        # Process based on mode
        if mode == "STATISTICAL":
            answer, stats, filter_desc, match_count = rag_service.process_statistical_query(
                documents, request.prompt
            )
            response_data["answer"] = answer
            response_data["statistics"] = stats
            response_data["filters_applied"] = filter_desc
            response_data["matching_transactions_count"] = match_count

        elif mode == "SMART_FULL" or request.use_full_data:
            answer, filtered_docs, filter_descriptions = rag_service.process_smart_full_query(
                documents, request.prompt, request.show_all
            )
            response_data["matching_transactions_count"] = len(filtered_docs)
            response_data["filters_applied"] = filter_descriptions
            response_data["answer"] = answer

            # Paginate results
            if request.show_all and filtered_docs:
                sorted_docs = sorted(filtered_docs, key=lambda x: float(x.get('amount', 0)), reverse=True)

                start_idx = (request.page - 1) * request.page_size
                end_idx = start_idx + request.page_size
                paginated_docs = sorted_docs[start_idx:end_idx]

                response_data["transactions"] = [
                    format_transaction_for_api(doc) for doc in paginated_docs
                ]
                response_data["pagination"] = {
                    "page": request.page,
                    "page_size": request.page_size,
                    "total_items": len(filtered_docs),
                    "total_pages": (len(filtered_docs) + request.page_size - 1) // request.page_size,
                    "has_next": end_idx < len(filtered_docs),
                    "has_prev": request.page > 1
                }

        else:
            # Vector search mode
            # Check if it's analytical or counting query
            is_analytical = any(kw in request.prompt.lower() for kw in [
                'summarize', 'summarise', 'summary', 'analyze', 'analyse',
                'overview', 'insights', 'patterns', 'trends'
            ])

            counting_patterns = [
                r'\b(how many|kitne|count|total)\s+.*?transaction',
                r'transaction.*?\b(how many|kitne|count|total)',
                r'\b(कितने|कितनी)\s+.*?(transaction|ट्रांज)',
                r'(transaction|ट्रांज).*?\b(कितने|कितनी)',
                r'\bnumber of\s+transaction',
            ]
            is_counting_query = any(re.search(pattern, request.prompt.lower()) for pattern in counting_patterns)
            is_analytical = is_analytical or is_counting_query

            if is_analytical:
                result = rag_service.process_analytical_query(documents, request.prompt)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = len(documents)
            else:
                # Specific query - use vector search
                k_value = min(50, len(documents))
                result = rag_service.process_vector_search_query(vectorstore, request.prompt, k_value)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = k_value

        # Save chat interaction to database (if user_id provided)
        if hasattr(request, 'user_id') and request.user_id:
            try:
                save_chat_interaction(
                    user_id=request.user_id,
                    query=request.prompt,
                    response=response_data["answer"],
                    query_id=None,
                    mode=response_data.get("mode"),
                    matching_transactions_count=response_data.get("matching_transactions_count"),
                    filters_applied=response_data.get("filters_applied")
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to save chat history: {e}")

        return RAGResponse(**response_data)

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def query_transactions_stream(request: PromptRequest):
    """
    Streaming endpoint: Accept only prompt and return LLM response as a stream using pre-ingested data (with multi-user support)

    This endpoint:
    1. Receives user question (prompt) and optional user_id
    2. Uses previously ingested context data and vectorstore for that user
    3. Applies filters based on the question
    4. Uses LLM to generate natural language response in streaming mode
    5. Returns Server-Sent Events (SSE) stream with chunks of the answer

    Multi-user support:
    - If user_id is provided: Streams only that user's data
    - If user_id is None: Streams global data (backward compatible)
    """
    if not embeddings_model or not llm_streaming:
        raise HTTPException(status_code=503, detail="Models not initialized")

    user_id = request.user_id
    user_info = f" for user_id={user_id}" if user_id else " (global)"

    # Check if data has been ingested for this user
    if not has_ingested_data(user_id=user_id):
        raise HTTPException(
            status_code=400,
            detail=f"No context data ingested{user_info}. Please call /ingest endpoint first."
        )

    async def generate_stream():
        try:
            logger.info(f"Processing streaming query{user_info}: {request.prompt}")

            # Get ingested data for this specific user
            ingested_data = get_ingested_data(user_id=user_id)
            documents = ingested_data["transactions"]
            vectorstore = ingested_data["vectorstore"]

            logger.info(f"Using ingested data: {len(documents)} transactions")

            # Initialize RAG service with streaming LLM
            rag_service = RAGService(embeddings_model, llm_streaming)


            # Extract filters
            filters = extract_filters_from_query(request.prompt)
            logger.info(f"Extracted filters: {filters}")

            # Detect query mode
            mode = detect_query_mode(request.prompt, documents)
            if request.use_full_data is not None:
                mode = "SMART_FULL" if request.use_full_data else "VECTOR_SEARCH"

            logger.info(f"Query mode: {mode}")

            # Generate unique query ID
            query_id = generate_query_id(request.prompt, filters)

            # Send metadata first
            metadata = {
                "type": "metadata",
                "query_id": query_id,
                "mode": mode,
                "matching_transactions_count": 0
            }
            yield f"data: {json.dumps(metadata)}\n\n"

            # Process based on mode and stream the answer
            if mode == "STATISTICAL":
                answer, stats, filter_desc, match_count = rag_service.process_statistical_query(
                    documents, request.prompt
                )
                # For statistical queries, send the complete answer at once (it's already formatted)
                chunk_data = {
                    "type": "chunk",
                    "content": answer
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
                
                # Send statistics
                stats_data = {
                    "type": "statistics",
                    "statistics": stats,
                    "filters_applied": filter_desc,
                    "matching_transactions_count": match_count
                }
                yield f"data: {json.dumps(stats_data)}\n\n"

            elif mode == "SMART_FULL" or request.use_full_data:
                filtered_docs_result, filter_descriptions = None, None
                
                # Stream the answer
                async for chunk in rag_service.process_smart_full_query_stream(
                    documents, request.prompt
                ):
                    chunk_data = {
                        "type": "chunk",
                        "content": chunk
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                
                # Get filter info for final metadata
                filters_extracted = extract_filters_from_query(request.prompt)
                filtered_docs_result, filter_descriptions = apply_filters(documents, filters_extracted, request.prompt)
                
                # Send final metadata
                final_metadata = {
                    "type": "metadata_final",
                    "matching_transactions_count": len(filtered_docs_result),
                    "filters_applied": filter_descriptions
                }
                yield f"data: {json.dumps(final_metadata)}\n\n"

            else:
                # Vector search mode
                is_analytical = any(kw in request.prompt.lower() for kw in [
                    'summarize', 'summarise', 'summary', 'analyze', 'analyse',
                    'overview', 'insights', 'patterns', 'trends'
                ])

                counting_patterns = [
                    r'\b(how many|kitne|count|total)\s+.*?transaction',
                    r'transaction.*?\b(how many|kitne|count|total)',
                    r'\b(कितने|कितनी)\s+.*?(transaction|ट्रांज)',
                    r'(transaction|ट्रांज).*?\b(कितने|कितनी)',
                    r'\bnumber of\s+transaction',
                ]
                is_counting_query = any(re.search(pattern, request.prompt.lower()) for pattern in counting_patterns)
                is_analytical = is_analytical or is_counting_query

                if is_analytical:
                    # Stream analytical query response
                    async for chunk in rag_service.process_analytical_query_stream(documents, request.prompt):
                        chunk_data = {
                            "type": "chunk",
                            "content": chunk
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"
                    
                    final_metadata = {
                        "type": "metadata_final",
                        "matching_transactions_count": len(documents)
                    }
                    yield f"data: {json.dumps(final_metadata)}\n\n"
                else:
                    # Specific query - use vector search with streaming
                    k_value = min(50, len(documents))
                    async for chunk in rag_service.process_vector_search_query_stream(vectorstore, request.prompt, k_value):
                        chunk_data = {
                            "type": "chunk",
                            "content": chunk
                        }
                        yield f"data: {json.dumps(chunk_data)}\n\n"
                    
                    final_metadata = {
                        "type": "metadata_final",
                        "matching_transactions_count": k_value
                    }
                    yield f"data: {json.dumps(final_metadata)}\n\n"

            # Send done signal
            done_data = {
                "type": "done"
            }
            yield f"data: {json.dumps(done_data)}\n\n"

        except Exception as e:
            logger.error(f"Error processing streaming query: {str(e)}")
            error_data = {
                "type": "error",
                "message": str(e)
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_context_data(request: IngestRequest):
    """
    Ingest endpoint: Accept and store context data for later querying (with multi-user support)

    This endpoint:
    1. Receives transaction data (context_data) and optional user_id
    2. Creates vector embeddings from the transaction data
    3. Stores the vectorstore and documents in memory for later use (isolated by user_id if provided)
    4. Returns confirmation with timestamp

    Multi-user support:
    - If user_id is provided: Data is stored separately for that user
    - If user_id is None: Data is stored globally (backward compatible)
    """
    import time
    request_start = time.time()

    if not embeddings_model or not llm:
        raise HTTPException(status_code=503, detail="Models not initialized")

    try:
        user_id = request.user_id
        user_info = f" for user_id={user_id}" if user_id else " (global)"

        if user_id:
            logger.info(f"🔵 MULTI-USER MODE: Ingesting {len(request.context_data)} transactions for user_id='{user_id}'")
        else:
            logger.info(f"🔴 LEGACY MODE: Ingesting {len(request.context_data)} transactions in global store")

        logger.info(f"Ingesting context data: {len(request.context_data)} transactions{user_info}")

        # Initialize RAG service
        rag_service = RAGService(embeddings_model, llm)

        # Create vector store
        vector_start = time.time()
        vectorstore, langchain_docs = rag_service.create_vector_store(request.context_data)
        vector_time = time.time() - vector_start
        logger.info(f"⏱️ Vector store creation took {vector_time:.2f}s")

        # Store in user-specific or global state
        store_start = time.time()
        set_ingested_data(request.context_data, vectorstore, langchain_docs, user_id=user_id)
        store_time = time.time() - store_start
        logger.info(f"⏱️ Data storage took {store_time:.2f}s")

        total_time = time.time() - request_start
        logger.info(f"⏱️ TOTAL ingest time: {total_time:.2f}s")

        ingested_data = get_ingested_data(user_id=user_id)

        return IngestResponse(
            status="success",
            message=f"Context data ingested successfully{user_info}",
            transactions_ingested=len(request.context_data),
            timestamp=ingested_data["last_updated"],
            user_id=user_id
        )

    except Exception as e:
        logger.error(f"Error ingesting context data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt", response_model=RAGResponse)
async def query_with_prompt(request: PromptRequest):
    """
    Prompt endpoint: Accept only prompt and query against pre-ingested data (with multi-user support)

    This endpoint:
    1. Receives user question (prompt) and optional user_id
    2. Uses previously ingested context data and vectorstore for that user
    3. Applies filters based on the question
    4. Uses LLM to generate natural language response (ONLY ONCE per query)
    5. Caches results for pagination
    6. Returns paginated results with statistics

    Multi-user support:
    - If user_id is provided: Queries only that user's data
    - If user_id is None: Queries global data (backward compatible)

    For pagination:
    - First request (page=1): Generates answer with LLM and caches results
    - Subsequent requests (page>1 with same query_id): Returns cached answer with next page of transactions
    """
    if not embeddings_model or not llm:
        raise HTTPException(status_code=503, detail="Models not initialized")

    user_id = request.user_id
    user_info = f" for user_id={user_id}" if user_id else " (global)"

    # Check if data has been ingested for this user
    if not has_ingested_data(user_id=user_id):
        raise HTTPException(
            status_code=400,
            detail=f"No context data ingested{user_info}. Please call /ingest endpoint first."
        )

    try:
        logger.info(f"Processing prompt query{user_info}: {request.prompt}, page: {request.page}")

        # Get ingested data for this specific user
        ingested_data = get_ingested_data(user_id=user_id)
        documents = ingested_data["transactions"]
        vectorstore = ingested_data["vectorstore"]

        logger.info(f"Using ingested data{user_info}: {len(documents)} transactions")

        # Extract filters to generate/validate query_id
        filters = extract_filters_from_query(request.prompt)
        logger.info(f"Extracted filters: {filters}")

        # Generate or use provided query_id
        if request.query_id:
            query_id = request.query_id
            logger.info(f"Using provided query_id: {query_id}")
        else:
            query_id = generate_query_id(request.prompt, filters)
            logger.info(f"Generated new query_id: {query_id}")

        # Check cache for this query
        cached_data = get_cached_query(query_id)

        if cached_data and request.page > 1:
            # Use cached data for pagination
            logger.info(f"Using cached results for pagination (page {request.page})")

            mode = cached_data["mode"]
            answer = cached_data["answer"]
            filtered_docs = cached_data["filtered_docs"]
            filters_applied = cached_data["filters_applied"]
            statistics = cached_data.get("statistics")

            # Prepare response with cached data
            response_data = {
                "query_id": query_id,
                "mode": mode,
                "matching_transactions_count": len(filtered_docs),
                "filters_applied": filters_applied,
                "answer": answer,
                "transactions": None,
                "pagination": None,
                "statistics": statistics
            }

            # Paginate the cached filtered_docs
            if request.show_all and filtered_docs:
                sorted_docs = sorted(filtered_docs, key=lambda x: float(x.get('amount', 0)), reverse=True)

                start_idx = (request.page - 1) * request.page_size
                end_idx = start_idx + request.page_size
                paginated_docs = sorted_docs[start_idx:end_idx]

                response_data["transactions"] = [
                    format_transaction_for_api(doc) for doc in paginated_docs
                ]
                response_data["pagination"] = {
                    "page": request.page,
                    "page_size": request.page_size,
                    "total_items": len(filtered_docs),
                    "total_pages": (len(filtered_docs) + request.page_size - 1) // request.page_size,
                    "has_next": end_idx < len(filtered_docs),
                    "has_prev": request.page > 1
                }

            return RAGResponse(**response_data)

        # No cache or page 1 - process normally and cache results
        logger.info("Processing new query or page 1 - will generate LLM response and cache")

        # Initialize RAG service
        rag_service = RAGService(embeddings_model, llm)

        # Detect query mode
        mode = detect_query_mode(request.prompt, documents)
        if request.use_full_data is not None:
            mode = "SMART_FULL" if request.use_full_data else "VECTOR_SEARCH"

        logger.info(f"Query mode: {mode}")

        # Prepare response
        response_data = {
            "query_id": query_id,
            "mode": mode,
            "matching_transactions_count": 0,
            "filters_applied": None,
            "answer": "",
            "transactions": None,
            "pagination": None,
            "statistics": None
        }

        # Process based on mode
        if mode == "STATISTICAL":
            answer, stats, filter_desc, match_count = rag_service.process_statistical_query(
                documents, request.prompt
            )

            response_data["answer"] = answer
            response_data["statistics"] = stats
            response_data["filters_applied"] = filter_desc
            response_data["matching_transactions_count"] = match_count

            # Cache results
            filtered_docs, _ = apply_filters(documents, filters, request.prompt)
            cache_query_results(query_id, answer, mode, filtered_docs, filter_desc, stats)

        elif mode == "SMART_FULL" or request.use_full_data:
            answer, filtered_docs, filter_descriptions = rag_service.process_smart_full_query(
                documents, request.prompt, request.show_all
            )

            response_data["answer"] = answer
            response_data["matching_transactions_count"] = len(filtered_docs)
            response_data["filters_applied"] = filter_descriptions

            # Cache results
            cache_query_results(query_id, answer, mode, filtered_docs, filter_descriptions, None)

            # Paginate results
            if request.show_all and filtered_docs:
                sorted_docs = sorted(filtered_docs, key=lambda x: float(x.get('amount', 0)), reverse=True)

                start_idx = (request.page - 1) * request.page_size
                end_idx = start_idx + request.page_size
                paginated_docs = sorted_docs[start_idx:end_idx]

                response_data["transactions"] = [
                    format_transaction_for_api(doc) for doc in paginated_docs
                ]
                response_data["pagination"] = {
                    "page": request.page,
                    "page_size": request.page_size,
                    "total_items": len(filtered_docs),
                    "total_pages": (len(filtered_docs) + request.page_size - 1) // request.page_size,
                    "has_next": end_idx < len(filtered_docs),
                    "has_prev": request.page > 1
                }

        else:
            # Vector search mode
            is_analytical = any(kw in request.prompt.lower() for kw in [
                'summarize', 'summarise', 'summary', 'analyze', 'analyse',
                'overview', 'insights', 'patterns', 'trends'
            ])

            counting_patterns = [
                r'\b(how many|kitne|count|total)\s+.*?transaction',
                r'transaction.*?\b(how many|kitne|count|total)',
                r'\b(कितने|कितनी)\s+.*?(transaction|ट्रांज)',
                r'(transaction|ट्रांज).*?\b(कितने|कितनी)',
                r'\bnumber of\s+transaction',
            ]
            is_counting_query = any(re.search(pattern, request.prompt.lower()) for pattern in counting_patterns)
            is_analytical = is_analytical or is_counting_query

            if is_analytical:
                result = rag_service.process_analytical_query(documents, request.prompt)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = len(documents)

                # Cache analytical result
                cache_query_results(query_id, result, mode, [], None, None)
            else:
                # Regular vector search
                k_value = min(50, len(documents))
                result = rag_service.process_vector_search_query(vectorstore, request.prompt, k_value)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = k_value

        # Save chat interaction to database
        if user_id:
            try:
                save_chat_interaction(
                    user_id=user_id,
                    query=request.prompt,
                    response=response_data["answer"],
                    query_id=query_id,
                    mode=response_data.get("mode"),
                    matching_transactions_count=response_data.get("matching_transactions_count"),
                    filters_applied=response_data.get("filters_applied")
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to save chat history: {e}")

        return RAGResponse(**response_data)

    except Exception as e:
        logger.error(f"Error processing prompt query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
