# agents.py

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_google_genai.embeddings import GoogleGenerativeAIEmbeddings

from src.prompts import (
    CATEGORIZATION_PROMPT,
    GENERATE_RAG_QUERIES_PROMPT,
    GENERATE_RAG_ANSWER_PROMPT
)


# --- Agent 1 : Catégorisation des tickets ---
def categorize_ticket(ticket):
    """Appelle le LLM Gemini pour catégoriser un ticket."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.2
    )

    prompt = CATEGORIZATION_PROMPT.format(
        subject=ticket["subject"],
        body=ticket["body"]
    )

    response = llm.invoke(prompt)
    return response.content.strip()


# --- Agent 2 : RAG (utilisé dans les nœuds) ---
class TicketRAGAgent:
    """Initialise les composants nécessaires au RAG pour les nœuds."""

    def __init__(self):
        # Embeddings et (optionnel) base vectorielle.
        # We attempt to initialize Chroma, but don't raise on failure so importing
        # this module won't crash when chromadb's native bindings are missing
        # (common on some Windows setups). In that case we set vectorstore/retriever
        # to None and continue; RAG retrieval will simply be disabled.
        self.embeddings = None
        self.vectorstore = None
        self.retriever = None
        try:
            # Import Chroma lazily to avoid import-time failures when chromadb
            # native bindings aren't available.
            from langchain_chroma import Chroma

            self.embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
            self.vectorstore = Chroma(
                persist_directory="db",
                embedding_function=self.embeddings
            )
            self.retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})
        except Exception as e:  # ImportError, OSError (DLL load), etc.
            import warnings

            warnings.warn(
                "Chroma vectorstore unavailable: %s. RAG retrieval disabled. "
                "To enable it, install a compatible chromadb build or set a "
                "different Chroma backend. See project docs." % (e,),
                RuntimeWarning,
            )

        # Prompts RAG pour les nœuds
        self.generate_query_prompt = PromptTemplate(
            template=GENERATE_RAG_QUERIES_PROMPT,
            input_variables=["ticket_body"]
        )
        self.qa_prompt = ChatPromptTemplate.from_template(GENERATE_RAG_ANSWER_PROMPT)

        # LLM pour la génération des réponses RAG
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.2
        )
class FeedbackSentimentAgent:
    """Analyse le sentiment des feedbacks ou tickets.

    This attempts to create a Hugging Face `pipeline` for sentiment-analysis.
    If `transformers`/`torch` aren't available (common in fresh venvs), we
    fall back to a lightweight heuristic that returns 'neutral'. The goal is
    to avoid import-time crashes so the graph can start in dev environments.
    """

    def __init__(self):
        self.sentiment_analyzer = None
        # LLM fallback (Gemini) for sentiment classification when HF pipeline is
        # unavailable or when you prefer LLM-based classification.
        try:
            self.llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.0)
        except Exception:
            self.llm = None
        try:
            # Lazy import to avoid hard dependency at import time
            from transformers import pipeline

            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sst-2-english"
            )
        except Exception as e:
            # Could be ImportError or NameError due to missing torch, etc.
            import warnings

            warnings.warn(
                f"Sentiment pipeline unavailable: {e}. Using lightweight fallback (neutral).",
                RuntimeWarning,
            )

    def analyze_sentiment(self, text) -> str:
        """Retourne 'positive', 'negative' ou 'neutral'.

        Accepts either a plain string or an object with a `.content` attribute
        (like `HumanMessage`). If the Hugging Face pipeline isn't available
        we use a small keyword-based heuristic as a fallback.
        """
        # Accept HumanMessage-like objects as well as strings
        try:
            # If it's an object with .content, extract it
            if not isinstance(text, str) and hasattr(text, "content"):
                txt = text.content
            else:
                txt = str(text)
        except Exception:
            txt = ""

        txt_l = txt.lower()

        # If HF pipeline isn't available, prefer using the Gemini LLM (if
        # configured) to classify sentiment. This usually gives better
        # results than a tiny keyword heuristic. If the LLM call fails, fall
        # back to the simple keyword heuristic.
        if self.sentiment_analyzer is None:
            # Try LLM-based classification first (Gemini)
            if getattr(self, "llm", None) is not None:
                try:
                    prompt = (
                        "Classify the sentiment of the following text as one of: "
                        "positive, negative, or neutral. Respond with only the single word.\n\n"
                        f"Text: '''{txt}'''"
                    )
                    resp = self.llm.invoke(prompt)
                    out = getattr(resp, "content", "").strip().lower()
                    # Extract the first token that looks like a label
                    for token in out.replace("\n", " ").split():
                        t = token.strip(".!,").lower()
                        if t in ("positive", "negative", "neutral"):
                            return t
                except Exception:
                    # fall through to keyword heuristic
                    pass

            # Keyword heuristic fallback
            positive_kw = ("good", "great", "love", "excellent", "happy", "thanks", "thank", "awesome")
            negative_kw = ("bad", "terrible", "hate", "awful", "poor", "not working", "fail", "error", "crash", "angry")

            pos = any(k in txt_l for k in positive_kw)
            neg = any(k in txt_l for k in negative_kw)

            if pos and not neg:
                return "positive"
            if neg and not pos:
                return "negative"
            return "neutral"

        # Otherwise use the HF pipeline
        try:
            result = self.sentiment_analyzer(txt)[0]
            label = result.get("label", "NEUTRAL").lower()
            if "positive" in label:
                return "positive"
            if "negative" in label:
                return "negative"
            return "neutral"
        except Exception:
            return "neutral"
