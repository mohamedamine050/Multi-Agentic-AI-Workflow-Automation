from typing import List, Dict, TypedDict, Optional
# ❌ Ne pas importer add_messages, inutile ici pour des objets de type Ticket

class Ticket(TypedDict):
    id: int
    subject: str
    body: str
    category: Optional[str]
    sentiment: Optional[str]
    feedback_type: Optional[str]
    validated: Optional[bool]
    sent: Optional[bool]


class GraphState(TypedDict):
    # --- Données principales ---
    tickets: List[Ticket]                      # ✅ liste simple, pas add_messages
    current_ticket: Optional[Ticket]
    ticket_category: Optional[str]

    # --- Catégorisation ---
    categorized_tickets: List[Ticket]

    # --- RAG ---
    information_search_tickets: List[Ticket]
    # Tickets routed to the feedback/sentiment branch
    sentiment_tickets: List[Ticket]
    # Tickets routed to the product complaint branch
    product_complaint_tickets: List[Ticket]
    rag_queries: Dict[int, List[str]]
    rag_answers: Dict[int, str]

    # --- Analyse avancée ---
    ticket_sentiments: Dict[int, str]
    ticket_feedback_types: Dict[int, str]

    # --- Human-in-the-loop ---
    tickets_for_review: List[Ticket]
    human_validated_tickets: List[Ticket]

    # --- Mail tracking ---
    sent_tickets: List[Ticket]
    # product branch sent tracking
    product_sent_tickets: List[Ticket]
