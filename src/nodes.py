import os
import asyncio
import json
# email/smtp handled by tools.gmail_tool
from langchain_core.messages import HumanMessage
from langgraph.types import interrupt, Command
from src.agents import categorize_ticket, TicketRAGAgent, FeedbackSentimentAgent
from src.state import GraphState
from src.prompts import GENERATE_RAG_ANSWER_PROMPT
from tool.toolgmail import send_email

# --- Charger la base de connaissances ---
with open("agentia.txt", "r", encoding="utf-8") as f:
    AGENTIA_CONTENT = f.read()

rag_agent = TicketRAGAgent()
sentiment_agent = FeedbackSentimentAgent()


# Helper to call interrupt() robustly. Some runtimes raise an exception
# that contains an Interrupt object; this helper will try to extract a
# usable resume payload from exception args so nodes can continue in dev.
def _call_interrupt(payload):
    try:
        return interrupt(payload)
    except Exception as e:
        for a in getattr(e, "args", ()):  # iterate possible payloads
            if isinstance(a, dict) or isinstance(a, str):
                return a
            if isinstance(a, tuple) and a:
                inner = a[0]
                if hasattr(inner, "value"):
                    return getattr(inner, "value")
            if hasattr(a, "value"):
                return getattr(a, "value")
        return None


# --------------------------
# 1️⃣ Charger les tickets
# --------------------------
async def load_tickets(state: GraphState) -> GraphState:
    print("📥 Chargement des tickets...")
    return {
        "categorized_tickets": [],
        "information_search_tickets": [],
        "sentiment_tickets": [],
        "product_complaint_tickets": [],
        "rag_queries": {},
        "rag_answers": {},
    }


# --------------------------
# 2️⃣ Catégorisation
# --------------------------
async def process_ticket(state: GraphState) -> GraphState:
    print("🔄 Début de la catégorisation des tickets...")
    categorized_tickets = []
    tickets = state.get("tickets", [])
    for ticket in tickets:
        try:
            # categorize_ticket may call an LLM synchronously; run it in a thread
            category = (await asyncio.to_thread(categorize_ticket, ticket)).strip().lower()
            new_ticket = dict(ticket)
            new_ticket["category"] = category
            categorized_tickets.append(new_ticket)
            print(f"✅ Ticket {ticket.get('id', '?')} catégorisé comme : {category}")
        except Exception as e:
            print(f"❌ Erreur ticket {ticket.get('id', '?')}: {e}")
    # Return only the categorized tickets; routing is handled by a dedicated node.
    return {"categorized_tickets": categorized_tickets}


# --------------------------
# 3️⃣ Filtrer tickets info
# --------------------------
async def filter_information_search(state: GraphState) -> GraphState:
    # Read the list produced by the router so only tickets routed to the
    # information-search branch are processed here.
    info_tickets = state.get("information_search_tickets", [])
    print(f"🔎 {len(info_tickets)} tickets d'information retenus.")
    return {"information_search_tickets": info_tickets}


# --------------------------
# 4️⃣ Construire requêtes RAG
# --------------------------
async def construct_rag_queries(state: GraphState) -> GraphState:
    info_tickets = state.get("information_search_tickets", [])
    rag_queries = {t["id"]: [t["body"]] for t in info_tickets}
    for t in info_tickets:
        print(f"🧠 Requête RAG construite pour Ticket {t['id']}")
    return {"rag_queries": rag_queries}


# --------------------------
# 5️⃣ Récupérer réponse RAG
# --------------------------
async def retrieve_from_rag(state: GraphState) -> GraphState:
    answers = {}
    for ticket_id, queries in state.get("rag_queries", {}).items():
        final_answer = ""
        for q in queries:
            message = HumanMessage(
                content=GENERATE_RAG_ANSWER_PROMPT.format(
                    context=AGENTIA_CONTENT, question=q
                )
            )
            # The underlying LLM client may block (time.sleep in retries).
            # Call it in a thread to avoid blocking the event loop.
            response = await asyncio.to_thread(rag_agent.llm.invoke, [message])
            final_answer += response.content.strip() + "\n\n"
        answers[ticket_id] = final_answer.strip()
        print(f"✅ Réponse RAG générée pour Ticket {ticket_id}")
    return {"rag_answers": answers}


# --------------------------
# 6️⃣ Analyse de sentiment
# --------------------------
async def analyze_ticket_sentiment(state: GraphState) -> GraphState:
    # Only analyze sentiments for tickets routed to the feedback branch.
    tickets = state.get("sentiment_tickets", [])
    print(f"[debug] analyze_ticket_sentiment called with {len(tickets)} tickets")
    if tickets:
        print(f"[debug] sentiment ticket ids: {[t.get('id') for t in tickets]}")
    sentiments = {}
    for i, ticket in enumerate(tickets):
        text = ticket.get("body", "") if isinstance(ticket, dict) else str(ticket)
        # sentiment_agent may perform blocking work; run in thread
        sentiment = await asyncio.to_thread(sentiment_agent.analyze_sentiment, text)
        tid = ticket.get("id") if isinstance(ticket, dict) else str(i)
        sentiments[tid] = sentiment
        print(f"🧩 Ticket {tid} sentiment: {sentiment}")
    return {"ticket_sentiments": sentiments}


# --------------------------
# 7️⃣ Classification feedback
# --------------------------
async def classify_feedback_type(state: GraphState) -> GraphState:
    # Work only on tickets routed to the feedback branch
    tickets = state.get("sentiment_tickets", [])
    sent_map = state.get("ticket_sentiments", {})
    print(f"[debug] classify_feedback_type called with {len(tickets)} tickets and sentiments: {sent_map}")
    fb_map = {}
    for ticket in tickets:
        tid = ticket.get("id") if isinstance(ticket, dict) else str(ticket)
        sentiment = sent_map.get(tid, "neutral")
        if sentiment not in ("positive", "negative", "neutral"):
            sentiment = "neutral"
        fb_map[tid] = sentiment
        print(f"💬 Ticket {tid} feedback_type: {sentiment}")
    return {"ticket_feedback_types": fb_map}


## --------------------------
# 8️⃣ Human-in-the-loop
# --------------------------
async def human_validation_loop(state: GraphState) -> GraphState:
    # Validate only tickets from the feedback branch
    tickets = state.get("sentiment_tickets", [])
    sent_map = state.get("ticket_sentiments", {})
    print(f"[debug] human_validation_loop called with {len(tickets)} tickets and sentiments: {sent_map}")
    negative_tickets = [t for t in tickets if sent_map.get(t.get("id")) == "negative"]

    if not negative_tickets:
        print("✅ Aucun ticket nécessitant validation humaine. Bypass outils.")
        # No negative tickets: skip the tool call and continue to send_ticket_email
        return Command(goto="send_ticket_email")

    # Use LangGraph interrupt to request human validation via the Studio UI
    print("🧍 Interruption du graphe : validation humaine requise...")
    validation_data = _call_interrupt({
        "action": "review_required",
        "tickets_to_validate": negative_tickets,
    })

    # interrupt() may return a dict or a raw string (if user pasted JSON).
    validation_data_parsed = None
    if isinstance(validation_data, str):
        raw = validation_data.strip()
        print(f"[human-validation-debug] interrupt returned raw string: {raw}")
        if raw == "":
            # No response from the Studio UI — give the operator an example and
            # optionally auto-validate negative tickets in dev via env var.
            print("[human-validation] No resume payload received from interrupt.")
            print("To resume the run, paste JSON like:\n{\"validated_tickets\": [{\"id\":3, \"validated\": true}]} into the Studio resume input.")
            if os.getenv("AUTO_VALIDATE_NEGATIVE", "false").lower() in ("1", "true", "yes"):
                print("[human-validation] AUTO_VALIDATE_NEGATIVE is set — auto-validating negative tickets.")
                validation_data_parsed = {"validated_tickets": negative_tickets}
            else:
                validation_data_parsed = {"validated_tickets": []}
        else:
            # Try JSON first
            try:
                validation_data_parsed = json.loads(raw)
            except Exception:
                # Accept a simple comma-separated list of ids like "3,5,6" or the word "all"
                if raw.lower() == "all":
                    validation_data_parsed = {"validated_tickets": negative_tickets}
                else:
                    parts = [p.strip() for p in raw.split(",") if p.strip()]
                    ids = []
                    for p in parts:
                        try:
                            ids.append(int(p))
                        except Exception:
                            continue
                    validated = [t for t in negative_tickets if t.get("id") in ids]
                    validation_data_parsed = {"validated_tickets": validated}
    elif isinstance(validation_data, dict):
        validation_data_parsed = validation_data
    else:
        validation_data_parsed = {"validated_tickets": []}

    validated_tickets = validation_data_parsed.get("validated_tickets", []) if isinstance(validation_data_parsed, dict) else []
    # Ensure we return a list of ticket dicts and remove them from sentiment_tickets
    validated_copies = []
    validated_ids = set()
    for t in validated_tickets:
        try:
            tc = dict(t)
            if "validated" not in tc:
                tc["validated"] = True
            validated_copies.append(tc)
            if isinstance(tc.get("id"), int):
                validated_ids.add(tc["id"])
        except Exception:
            # skip invalid entries
            continue

    # Remove validated tickets from the sentiment_tickets collection so they are not re-reviewed
    remaining_sentiment = []
    for t in state.get("sentiment_tickets", []):
        try:
            if t.get("id") not in validated_ids:
                remaining_sentiment.append(t)
        except Exception:
            remaining_sentiment.append(t)

    print(f"[human-validation] Validated ids: {validated_ids}; remaining sentiment tickets: {[t.get('id') for t in remaining_sentiment]}")

    # Return validated tickets and route to the tool node to perform sending.
    # Use a Command so the runtime will navigate to `call_gmail_tool` only when
    # there are validated tickets (preventing the tool node from running
    # unconditionally).
    if validated_copies:
        return Command(goto="call_gmail_tool", update={"human_validated_tickets": validated_copies, "sentiment_tickets": remaining_sentiment})
    return Command(goto="send_ticket_email", update={"human_validated_tickets": validated_copies, "sentiment_tickets": remaining_sentiment})


# --------------------------
# 9️⃣ Envoi email
# --------------------------
async def send_ticket_email(state: GraphState) -> GraphState:
    """
    Nœud LangGraph qui construit le mail à partir du ticket
    et appelle la tool générique `send_email`.
    """
    sent_tickets = []

    # The gmail tool exposes an async send_email(subject, body, to) function
    # which reads sender credentials from environment variables itself.
    support_team_email = os.getenv("SUPPORT_TEAM_EMAIL", "tixaf71837@wivstore.com")

    show_as_tool = os.getenv("SHOW_EMAIL_AS_TOOL", "false").lower() in ("1", "true", "yes")

    for ticket in state.get("human_validated_tickets", []):
        if not ticket.get("validated", False):
            continue

        tid = ticket.get("id", "?")

        # Resolve fields: tickets passed to human validation may be minimal (id only)
        def _resolve(field, default="(unknown)"):
            v = ticket.get(field)
            if v:
                return v
            for coll in (state.get("categorized_tickets", []), state.get("tickets", [])):
                for t0 in coll:
                    if t0.get("id") == tid:
                        return t0.get(field) or default
            return default

        subject_val = _resolve("subject", "(no subject)")
        category_val = _resolve("category", "(unknown)")
        body_text = _resolve("body", "(no message body)")
        sentiment_val = state.get("ticket_sentiments", {}).get(tid, "Inconnu")
        feedback_val = state.get("ticket_feedback_types", {}).get(tid, "N/A")

        html_body = f"""
<html>
    <body>
        <p>Bonjour équipe support,</p>
        <p>Le système LangGraph a identifié un ticket validé pour prise en charge :</p>
        <h3>Ticket #{tid} — {subject_val}</h3>
        <ul>
            <li><strong>Catégorie :</strong> {category_val}</li>
            <li><strong>Sentiment :</strong> {sentiment_val}</li>
            <li><strong>Type de feedback :</strong> {feedback_val}</li>
        </ul>
        <h4>Contenu du message</h4>
        <blockquote style="border-left:4px solid #ddd;padding-left:12px;color:#333">{body_text}</blockquote>
        <p>Actions recommandées : vérifier et traiter le ticket dans l'outil support.</p>
        <hr />
        <p style="font-size:0.9em;color:#666">Envoyé par LangGraph AI Monitoring System — ne pas répondre à cet e-mail.</p>
    </body>
</html>
"""

        subject = f"[Ticket #{tid}] {subject_val}"

        try:
            if show_as_tool:
                # Render the email send as a Studio tools call via interrupt()
                payload = {
                    "type": "tool_call",
                    "tool": "gmail.send_email",
                    "args": {"subject": subject, "body": html_body, "to": support_team_email},
                    "description": f"Send ticket #{tid} via Gmail tool (studio view)"
                }

                resume = _call_interrupt(payload)
                # Normalize resume value
                ok = False
                if isinstance(resume, dict):
                    ok = bool(resume.get("ok", False))
                elif isinstance(resume, str):
                    raw = resume.strip().lower()
                    ok = raw in ("ok", "true", "success")
                else:
                    ok = False

                sent_ticket = dict(ticket)
                sent_ticket["sent"] = bool(ok)
                sent_tickets.append(sent_ticket)
                if ok:
                    print(f"✅ (tool) Email envoyé à {support_team_email} avec sujet '{subject}'.")
                else:
                    print(f"❌ (tool) Envoi échoué pour ticket {tid} (resume: {resume})")
            else:
                # The tool provides an async API; call it directly
                ok = await send_email(subject, html_body, to=support_team_email)
                sent_ticket = dict(ticket)
                sent_ticket["sent"] = bool(ok)
                sent_tickets.append(sent_ticket)
                if ok:
                    print(f"✅ Email envoyé à {support_team_email} avec sujet '{subject}'.")
                else:
                    print(f"❌ Envoi échoué pour ticket {tid} (outil renvoyé False)")
        except Exception as e:
            print(f"❌ Erreur envoi email pour ticket {tid}: {e}")

    return {"sent_tickets": sent_tickets}


# --------------------------
# 🔔 Node de démonstration : appel direct à l'outil Gmail
# --------------------------
async def call_gmail_tool(state: GraphState) -> GraphState:
    """
    Nœud de démonstration pour appeler directement l'outil `send_email`
    et rendre le résultat visible dans la LangGraph Studio / Dev view.

    Retourne un petit état contenant le résultat (ok/error) pour inspection.
    """
    support_team_email = os.getenv("SUPPORT_TEAM_EMAIL", "tixaf71837@wivstore.com")
    subject = "[LangGraph Test] Vérification outil Gmail"
    html_body = "<p>Ceci est un test envoyé depuis le nœud `call_gmail_tool`.</p>"

    # Instead of calling send_email directly, use interrupt() to hand control
    # to the Studio / tool-runner. This will render the step as a 'tools' node
    # in LangGraph Studio (agent -> tools -> end) and allows the runner/operator
    # to return a resume payload indicating whether to continue the human loop
    # or proceed to sending the ticket.
    payload = {
        "type": "tool_call",
        "tool": "gmail.send_email",
        "args": {"subject": subject, "body": html_body, "to": support_team_email},
        "description": "Demo: appel outil Gmail depuis LangGraph Studio"
    }

    # Use the robust wrapper which may extract a resume payload from
    # runtime-wrapped exceptions (some runtimes raise an Interrupt object).
    resume = _call_interrupt(payload)
    if resume is None:
        err = {"ok": False, "error": "interrupt returned no resume payload"}
        print(f"[call_gmail_tool] Erreur interrupt: {err}")
        return {"gmail_tool_result": err}

    # Normalize resume payload
    result_parsed = None
    if isinstance(resume, dict):
        result_parsed = resume
    elif isinstance(resume, str):
        raw = resume.strip()
        if raw == "":
            result_parsed = {"ok": False, "info": "no resume payload"}
        else:
            try:
                result_parsed = json.loads(raw)
            except Exception:
                if raw.lower() in ("ok", "true", "success"):
                    result_parsed = {"ok": True, "info": raw}
                else:
                    result_parsed = {"ok": False, "info": raw}
    else:
        result_parsed = {"ok": False, "info": "unknown resume type"}

    print(f"[call_gmail_tool] Résultat après interrupt: {result_parsed}")

    # Decide next node based on resume payload
    # Expectation: resume may be {'action': 'continue'} or {'action': 'done'}
    action = None
    if isinstance(result_parsed, dict):
        action = result_parsed.get("action") or (
            "done" if result_parsed.get("ok") else "continue"
        )
    else:
        action = "done"

    # Always proceed to send_ticket_email to avoid looping back to human validation.
    # If you later want an explicit retry path, implement it with a conditional
    # branch that is carefully controlled (and removes validated tickets).
    return Command(goto="send_ticket_email", update={"gmail_tool_result": result_parsed})


async def handle_product_complaint(state: GraphState) -> GraphState:
    """
    Handle tickets routed to the product complaint branch.

    For each product complaint ticket, surface a tool call via interrupt so the
    Studio/tool-runner can send the email (visible as a tools node). We collect
    results in `product_sent_tickets` to track outcomes.
    """
    product_tickets = state.get("product_complaint_tickets", [])
    if not product_tickets:
        print("✅ Aucun ticket product complaint à traiter.")
        return {"product_sent_tickets": []}

    support_email = os.getenv("SUPPORT_PRODUCT_TEAM_EMAIL", "tixaf71837@wivstore.com")
    results = []

    for ticket in product_tickets:
        tid = ticket.get("id", "?")
        subject = f"[Product Complaint #{tid}] {ticket.get('subject', '(no subject)')}"
        body = ticket.get("body", "(no body)")
        html_body = f"<p>Ticket #{tid}</p><blockquote>{body}</blockquote>"

        try:
            # Optionally render the call as a Studio-visible tool (interrupt)
            show_as_tool = os.getenv("SHOW_EMAIL_AS_TOOL", "false").lower() in ("1", "true", "yes")
            if show_as_tool:
                payload = {
                    "type": "tool_call",
                    "tool": "gmail.send_email",
                    "args": {"subject": subject, "body": html_body, "to": support_email},
                    "description": f"Product complaint #{tid} - send via Gmail tool (studio view)"
                }
                resume = _call_interrupt(payload)
                ok = False
                if isinstance(resume, dict):
                    ok = bool(resume.get("ok", False))
                elif isinstance(resume, str):
                    raw = resume.strip().lower()
                    ok = raw in ("ok", "true", "success")
                results.append({"id": tid, "sent": bool(ok)})
                if ok:
                    print(f"✅ Product complaint email envoyé pour ticket {tid} à {support_email} (tool)")
                else:
                    print(f"❌ Échec envoi product complaint pour ticket {tid} (tool)")
            else:
                # Call the gmail tool directly (async). The tool reads credentials from env vars.
                ok = await send_email(subject, html_body, to=support_email)
                results.append({"id": tid, "sent": bool(ok)})
                if ok:
                    print(f"✅ Product complaint email envoyé pour ticket {tid} à {support_email}")
                else:
                    print(f"❌ Échec envoi product complaint pour ticket {tid}")
        except Exception as e:
            results.append({"id": tid, "error": str(e)})
            print(f"❌ Erreur envoi product complaint pour ticket {tid}: {e}")

    return {"product_sent_tickets": results}

# --------------------------
# 🔀 Routage (node séparé)
# --------------------------
async def route_ticket(state: GraphState) -> GraphState:
    categorized = state.get("categorized_tickets", [])
    feedback_tickets = [t for t in categorized if t.get("category") == "feedback"]
    product_tickets = [t for t in categorized if t.get("category") == "product_complaint"]
    info_tickets = [t for t in categorized if t.get("category") == "information_search"]

    print("🔀 Routage effectué :")
    print(f"   📚 {len(info_tickets)} tickets 'information_search'")
    print(f"   ids info: {[t.get('id') for t in info_tickets]}")
    print(f"   💬 {len(feedback_tickets)} tickets 'feedback'")
    print(f"   ids feedback: {[t.get('id') for t in feedback_tickets]}")

    return {
        "information_search_tickets": info_tickets,
        "sentiment_tickets": feedback_tickets,
        "product_complaint_tickets": product_tickets,
    }
