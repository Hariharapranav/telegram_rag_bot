import re
from typing import List, Dict, Any
from dataclasses import dataclass
from app.config import settings


@dataclass
class RoutingDecision:
    selected_model: str
    model_tier: str  # "simple" | "complex"
    complexity_score: float  # 0.0 to 1.0
    reasons: List[str]
    explanation: str


class QueryComplexityRouter:
    """
    Explainable Query Complexity Router.
    Routes queries between Gemini Flash-Lite (low latency & low cost for simple lookups)
    and Gemini Flash (higher capacity for multi-hop, comparative, or reasoning-heavy questions).
    """

    COMPARATIVE_PATTERNS = [
        r"\bcompare\b",
        r"\bcontrast\b",
        r"\bdifference\s+(between|in)\b",
        r"\bversus\b",
        r"\bvs\.?\b",
        r"\bwhich\s+is\s+better\b",
        r"\bpros\s+and\s+cons\b",
        r"\bdistinguish\b"
    ]

    REASONING_PATTERNS = [
        r"\bexplain\s+why\b",
        r"\bhow\s+does\b",
        r"\bstep[-\s]by[-\s]step\b",
        r"\banalyze\b",
        r"\bevaluate\b",
        r"\bwhat\s+happens\s+if\b",
        r"\bunder\s+what\s+circumstances\b",
        r"\brationale\b",
        r"\bimpact\s+of\b",
        r"\bpolicy\s+implications\b",
        r"\bsummarize\s+(all|the\s+entire|each)\b"
    ]

    MULTI_PART_PATTERNS = [
        r"\band\s+(also|what|how|why|when|where)\b",
        r"\bas\s+well\s+as\b",
        r"\bfirstly.*secondly\b",
        r"\b1[\.\)].*2[\.\)]\b",
        r"\?.*\?"  # Multiple questions in one prompt
    ]

    def __init__(
        self,
        simple_model: str = settings.GEMINI_MODEL_SIMPLE,
        complex_model: str = settings.GEMINI_MODEL_COMPLEX,
        length_threshold_words: int = 30,
        complexity_threshold: float = 0.35
    ):
        self.simple_model = simple_model
        self.complex_model = complex_model
        self.length_threshold_words = length_threshold_words
        self.complexity_threshold = complexity_threshold

    def analyze(self, query: str) -> RoutingDecision:
        query_clean = query.strip()
        words = query_clean.split()
        word_count = len(words)
        reasons: List[str] = []
        score = 0.0

        # 1. Length Factor
        if word_count > self.length_threshold_words:
            reasons.append(f"high_word_count ({word_count} words > {self.length_threshold_words})")
            score += min(0.35, 0.20 + (word_count - self.length_threshold_words) * 0.01)

        # 2. Comparative Analysis Factor
        for pattern in self.COMPARATIVE_PATTERNS:
            if re.search(pattern, query_clean, re.IGNORECASE):
                reasons.append("comparative_analysis_request")
                score += 0.45
                break

        # 3. Multi-Part Question Factor
        for pattern in self.MULTI_PART_PATTERNS:
            if re.search(pattern, query_clean, re.IGNORECASE):
                reasons.append("multi_part_query")
                score += 0.40
                break

        # 4. Deep Reasoning / Synthesis Factor
        for pattern in self.REASONING_PATTERNS:
            if re.search(pattern, query_clean, re.IGNORECASE):
                reasons.append("deep_reasoning_or_synthesis")
                score += 0.45
                break

        # 5. Clause complexity (many commas or semicolons)
        clause_breaks = len(re.findall(r"[,;]", query_clean))
        if clause_breaks >= 3:
            reasons.append(f"multi_clause_structure ({clause_breaks} clauses)")
            score += 0.15

        # Normalize score
        final_score = min(1.0, round(score, 2))

        # Decision
        if final_score >= self.complexity_threshold:
            selected_model = self.complex_model
            tier = "complex"
            explanation = f"Routed to {selected_model} (Complex) due to: {', '.join(reasons)}."
        else:
            selected_model = self.simple_model
            tier = "simple"
            reasons_text = f"low complexity score {final_score:.2f} (concise factual query)"
            explanation = f"Routed to {selected_model} (Flash-Lite) for fast factual retrieval."

        return RoutingDecision(
            selected_model=selected_model,
            model_tier=tier,
            complexity_score=final_score,
            reasons=reasons if reasons else ["direct_factual_lookup"],
            explanation=explanation
        )


# Global router singleton
model_router = QueryComplexityRouter()
