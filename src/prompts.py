# prompts.py

# --- Prompt pour catégoriser les tickets ---
# --- Prompt pour catégoriser les tickets ---
CATEGORIZATION_PROMPT = """
You are a helpful customer support agent.

Task: read the ticket (subject and body) and choose the single most appropriate category from the list below.

Categories (choose exactly one and return only the category name):
- "information_search" → The user is asking for information, clarification, instructions, or how-to guidance (no opinions or complaints).
- "feedback" → The user is expressing an opinion, appreciation, suggestion, or general comment about the product or service. This includes both positive and negative opinions. IMPORTANT: if the message expresses negative sentiment about the product or service (e.g., "I am unhappy", "I dislike", "very disappointed"), still return "feedback" unless the content explicitly reports a product defect, return request, broken item, or quality/functional problem.
- "product_complaint" → The user reports a concrete problem or defect with a product or order: broken item, missing parts, wrong item shipped, product not working as described, return/exchange request, damaged-on-arrival, manufacturing defect, or other issue that requires involvement of the product/support operations team.

Rules / guidance:
1. If the ticket reports an actual product defect, return "product_complaint" (even if the tone is negative).
2. If the ticket is mainly an opinion, praise, request for improvement, or general user experience comment, return "feedback". If that feedback expresses negative sentiment, it is still "feedback" — the sentiment analysis step will classify it as positive/neutral/negative.
3. If the user asks a factual or procedural question (how to, where is, how do I), return "information_search".
4. Return only the category name exactly as one of: information_search, feedback, product_complaint.

Ticket:
Subject: {subject}
Body: {body}
"""


# --- Prompt pour générer des requêtes RAG depuis un ticket ---
GENERATE_RAG_QUERIES_PROMPT = """
# **Role:**
You are an expert at analyzing customer tickets to extract their intent and construct the most relevant queries for internal knowledge sources.

# **Ticket Content:**
{ticket_body}

# Instructions:
1. Identify the main question or intent of the ticket.
2. Generate up to three concise, relevant queries for retrieving internal knowledge.
"""

# --- Prompt pour générer des réponses RAG basées sur le contexte fourni ---
GENERATE_RAG_ANSWER_PROMPT = """
# **Role:**
You are a highly knowledgeable and helpful assistant specializing in question-answering tasks.

# **Context:**
You will be provided with pieces of retrieved context relevant to the user's question. This context is your sole source of information.

# **Question:**
{question}

# **Context:**
{context}
"""

# prompts.py

SENTIMENT_PROMPT = """
You are an expert in analyzing customer feedback related to products.

Analyze the sentiment of the following product-related text.
Return only one word: positive, neutral, or negative.

Text: {text}
"""
