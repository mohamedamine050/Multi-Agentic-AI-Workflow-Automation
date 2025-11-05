from langgraph.graph import StateGraph, END
from src.nodes import (
    load_tickets,
    process_ticket,
    route_ticket,
    filter_information_search,
    construct_rag_queries,
    retrieve_from_rag,
    analyze_ticket_sentiment,
    classify_feedback_type,
    human_validation_loop,
    send_ticket_email,
    call_gmail_tool,
    handle_product_complaint,
)
from src.state import GraphState


def create_graph():
    graph = StateGraph(GraphState)

    # --- Nœuds principaux ---
    graph.add_node("load_tickets", load_tickets)
    graph.add_node("process_ticket", process_ticket)
    graph.add_node("route_ticket", route_ticket)

    # --- Branche RAG ---
    graph.add_node("filter_information_search", filter_information_search)
    graph.add_node("construct_rag_queries", construct_rag_queries)
    graph.add_node("retrieve_from_rag", retrieve_from_rag)

    # --- Branche Feedback ---
    graph.add_node("analyze_ticket_sentiment", analyze_ticket_sentiment)
    graph.add_node("classify_feedback_type", classify_feedback_type)
    graph.add_node("human_validation_loop", human_validation_loop)
    # The `call_gmail_tool` node represents a tools-style step. Provide
    # `destinations` mapping so LangGraph Studio can render labeled edges
    # (for example: 'done' -> send_ticket_email). This helps Studio show the
    # node as a tools step with a named outgoing path.
    graph.add_node(
        "call_gmail_tool",
        call_gmail_tool,
        destinations={"send_ticket_email": "done"},
    )

    graph.add_node("send_ticket_email", send_ticket_email, destinations={END: "done"})

    # --- Branche Product Complaint ---
    graph.add_node("handle_product_complaint", handle_product_complaint, destinations={END: "done"})

    # --- Point d'entrée ---
    graph.set_entry_point("load_tickets")

    # --- Liens principaux ---
    graph.add_edge("load_tickets", "process_ticket")
    graph.add_edge("process_ticket", "route_ticket")

    # --- Branches depuis le router ---
    graph.add_edge("route_ticket", "filter_information_search")      # RAG
    graph.add_edge("route_ticket", "analyze_ticket_sentiment")       # Feedback
    graph.add_edge("route_ticket", "handle_product_complaint")       # Product complaint

    # --- Suite RAG ---
    graph.add_edge("filter_information_search", "construct_rag_queries")
    graph.add_edge("construct_rag_queries", "retrieve_from_rag")
    graph.add_edge("retrieve_from_rag", END)

    # --- Suite Feedback ---
    graph.add_edge("analyze_ticket_sentiment", "classify_feedback_type")
    graph.add_edge("classify_feedback_type", "human_validation_loop")
    # Add a static edge so Studio renders the possible tool step.
    # Navigation is still controlled by Command(goto=...) returned from
    # `human_validation_loop`, but adding this edge makes the node visible
    # in the static graph and shows the tools path.
    graph.add_edge("human_validation_loop", "call_gmail_tool")
    # La tool `call_gmail_tool` est appelée conditionnellement depuis le nœud
    graph.add_edge("call_gmail_tool", "send_ticket_email")
    graph.add_edge("send_ticket_email", END)

    # --- Product Complaint ---
    graph.add_edge("handle_product_complaint", END)

    return graph.compile()


# --- Initialisation ---
app = create_graph()
