"""
Answer generation utilities using LLM
"""

import logging
from typing import List, Dict, Optional, AsyncGenerator

logger = logging.getLogger(__name__)


def generate_conversational_answer(
    question: str,
    filtered_docs: List[Dict],
    filters: Dict,
    filter_descriptions: List[str] = None,
    show_all: bool = False,
    llm_instance = None
) -> str:
    """Generate conversational answer using LLM for natural responses"""

    if not filtered_docs:
        return "No transactions found matching your query. Please try adjusting your search criteria or filters."

    # Calculate statistics
    amounts = [float(d.get("amount", 0)) for d in filtered_docs]
    total_amount = sum(amounts)
    avg_amount = total_amount / len(amounts) if amounts else 0
    max_amount = max(amounts) if amounts else 0
    min_amount = min(amounts) if amounts else 0

    # Prepare transaction summary for LLM
    filter_context = ", ".join(filter_descriptions) if filter_descriptions else "No filters"

    # If LLM is available, use it for natural response
    if llm_instance:
        # Sample transactions for context (max 10 for preview)
        sample_txns = filtered_docs[:10]
        txn_details = []
        for i, txn in enumerate(sample_txns, 1):
            txn_details.append(
                f"Transaction {i}: "
                f"₹{float(txn.get('amount', 0)):,.2f} ({txn.get('pk_GSI_1', 'N/A').replace('TYPE#', '')}), "
                f"{txn.get('mode', txn.get('txnMode', 'N/A'))}, "
                f"{txn.get('createdAt', 'N/A')[:10]}, "
                f"Narration: {txn.get('narration', 'N/A')[:50]}"
            )

        context_info = f"""
TRANSACTION QUERY RESULTS:
Total Matching Transactions: {len(filtered_docs)}
Filters Applied: {filter_context}

STATISTICS:
- Total Amount: ₹{total_amount:,.2f}
- Average Amount: ₹{avg_amount:,.2f}
- Highest: ₹{max_amount:,.2f}
- Lowest: ₹{min_amount:,.2f}

SAMPLE TRANSACTIONS (showing {len(sample_txns)} of {len(filtered_docs)}):
{chr(10).join(txn_details)}
"""

        prompt = f"""SYSTEM INSTRUCTION - MANDATORY - DO NOT IGNORE:
You MUST respond in English language ONLY. 
Do NOT respond in Hindi, Hinglish, or any other language.
IGNORE the language of the user's question.
ONLY respond in a different language if the user EXPLICITLY says "answer in [language]" or "translate to [language]".

Examples where you MUST still use English:
- User asks in Hindi: "मुझे दिखाओ" → Answer in ENGLISH
- User asks in Hinglish: "kitne transactions hain" → Answer in ENGLISH  
- User mixes languages: "Show me मेरे transactions" → Answer in ENGLISH

Examples where you can use other languages:
- User says: "answer in Hindi - show transactions" → Answer in Hindi
- User says: "हिंदी में जवाब दो" → Answer in Hindi

USER QUESTION: {question}

{context_info}

RESPONSE FORMAT:
1. Use tables (with | symbols) for data presentation
2. Use bullet points for statistics
3. Be detailed and professional
4. Structure: Summary → Tables → Insights

Example table:
| Date       | Description | Amount   | Mode |
|------------|-------------|----------|------|
| 2024-01-15 | Grocery     | ₹500.00  | UPI  |

REMEMBER: Respond in ENGLISH ONLY unless explicitly asked for translation.

YOUR DETAILED ENGLISH RESPONSE:"""

        try:
            response = llm_instance.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to template

    # Fallback: Template-based response (if LLM unavailable)
    is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in question)
    is_hinglish = any(word in question.lower() for word in ['mujhe', 'saari', 'dikhao', 'batao', 'kya', 'ki', 'se', 'ko'])

    if is_hindi:
        return f"नमस्ते! 😊 {len(filtered_docs)} ट्रांज़ैक्शन मिली हैं।\n\n📊 सारांश:\n   • कुल राशि: ₹{total_amount:,.2f}\n   • औसत: ₹{avg_amount:,.2f}"
    elif is_hinglish:
        return f"Namaste! 😊 Maine {len(filtered_docs)} transactions nikali hain.\n\n📊 Summary:\n   • Total: ₹{total_amount:,.2f}\n   • Average: ₹{avg_amount:,.2f}"
    else:
        return f"Hello! 😊 I found {len(filtered_docs)} transaction(s).\n\n📊 Summary:\n   • Total: ₹{total_amount:,.2f}\n   • Average: ₹{avg_amount:,.2f}"


async def generate_conversational_answer_stream(
    question: str,
    filtered_docs: List[Dict],
    filters: Dict,
    filter_descriptions: List[str] = None,
    llm_instance = None
) -> AsyncGenerator[str, None]:
    """Generate conversational answer with streaming using LLM"""

    if not filtered_docs:
        is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in question)
        is_hinglish = any(word in question.lower() for word in ['mujhe', 'saari', 'dikhao', 'batao', 'kya'])

        if is_hindi:
            yield "मुझे आपके सवाल से मेल खाने वाली कोई ट्रांज़ैक्शन नहीं मिली। 😊"
        elif is_hinglish:
            yield "Sorry! 😊 Aapke filters ke hisaab se koi transaction nahi mili."
        else:
            yield "No transactions found matching your query."
        return

    # Calculate statistics
    amounts = [float(d.get("amount", 0)) for d in filtered_docs]
    total_amount = sum(amounts)
    avg_amount = total_amount / len(amounts) if amounts else 0
    max_amount = max(amounts) if amounts else 0
    min_amount = min(amounts) if amounts else 0

    # Prepare transaction summary for LLM
    filter_context = ", ".join(filter_descriptions) if filter_descriptions else "No filters"

    # If LLM is available, use it for natural streaming response
    if llm_instance:
        # Sample transactions for context (max 10 for preview)
        sample_txns = filtered_docs[:10]
        txn_details = []
        for i, txn in enumerate(sample_txns, 1):
            txn_details.append(
                f"Transaction {i}: "
                f"₹{float(txn.get('amount', 0)):,.2f} ({txn.get('pk_GSI_1', 'N/A').replace('TYPE#', '')}), "
                f"{txn.get('mode', txn.get('txnMode', 'N/A'))}, "
                f"{txn.get('createdAt', 'N/A')[:10]}, "
                f"Narration: {txn.get('narration', 'N/A')[:50]}"
            )

        context_info = f"""
TRANSACTION QUERY RESULTS:
Total Matching Transactions: {len(filtered_docs)}
Filters Applied: {filter_context}

STATISTICS:
- Total Amount: ₹{total_amount:,.2f}
- Average Amount: ₹{avg_amount:,.2f}
- Highest: ₹{max_amount:,.2f}
- Lowest: ₹{min_amount:,.2f}

SAMPLE TRANSACTIONS (showing {len(sample_txns)} of {len(filtered_docs)}):
{chr(10).join(txn_details)}
"""

        prompt = f"""You are an intelligent financial assistant. Understand the user's question deeply, then provide a natural, helpful response.

USER QUESTION: {question}

{context_info}

INSTRUCTIONS:
1. First, understand what the user is asking (list, summary, analysis, specific details, etc.) by default answer in English language untill user explicitly ask in other language
2. Detect the language: Hindi (Devanagari), Hinglish (Roman script with Hindi words), or English
3. Respond in the SAME language style as the question
4. Be conversational, warm, and helpful - don't use robotic templates
5. Provide the information they need naturally
6. If they ask for "all" transactions, mention that detailed list is provided separately
7. Give insights, patterns, or helpful observations when relevant
8. Use emojis moderately for friendliness

YOUR NATURAL RESPONSE:"""

        try:
            # Stream the response
            async for chunk in llm_instance.astream(prompt):
                if hasattr(chunk, 'content'):
                    yield chunk.content
                else:
                    yield str(chunk)
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            # Fallback to template
            yield f"Hello! 😊 I found {len(filtered_docs)} transaction(s).\n\n📊 Summary:\n   • Total: ₹{total_amount:,.2f}\n   • Average: ₹{avg_amount:,.2f}"
    else:
        # Fallback: Template-based response (if LLM unavailable)
        is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in question)
        is_hinglish = any(word in question.lower() for word in ['mujhe', 'saari', 'dikhao', 'batao', 'kya', 'ki', 'se', 'ko'])

        if is_hindi:
            yield f"नमस्ते! 😊 {len(filtered_docs)} ट्रांज़ैक्शन मिली हैं।\n\n📊 सारांश:\n   • कुल राशि: ₹{total_amount:,.2f}\n   • औसत: ₹{avg_amount:,.2f}"
        elif is_hinglish:
            yield f"Namaste! 😊 Maine {len(filtered_docs)} transactions nikali hain.\n\n📊 Summary:\n   • Total: ₹{total_amount:,.2f}\n   • Average: ₹{avg_amount:,.2f}"
        else:
            yield f"Hello! 😊 I found {len(filtered_docs)} transaction(s).\n\n📊 Summary:\n   • Total: ₹{total_amount:,.2f}\n   • Average: ₹{avg_amount:,.2f}"
