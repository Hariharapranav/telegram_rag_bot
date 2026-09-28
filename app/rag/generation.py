import asyncio
import logging
import time
from typing import List, Dict, Any, Tuple
import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = "I couldn't find this information in your organization's documents."

# Pricing per million tokens (USD)
MODEL_PRICING = {
    "gemini-2.0-flash-lite": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gemini-1.5-flash-8b": {"input": 0.0375 / 1_000_000, "output": 0.15 / 1_000_000},
    "gemini-2.0-flash": {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
    "gemini-1.5-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gemini-1.5-pro": {"input": 1.25 / 1_000_000, "output": 5.00 / 1_000_000},
}


class GroundedGenerator:
    def __init__(self, api_key: str = settings.GEMINI_API_KEY):
        self.api_key = api_key
        self._is_configured = False
        if self.api_key and self.api_key.strip():
            try:
                genai.configure(api_key=self.api_key.strip())
                self._is_configured = True
            except Exception as e:
                logger.warning("Failed to configure Generative AI for generator: %s", e)

    def calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> float:
        # Default pricing fallback if model not in dict
        rates = MODEL_PRICING.get(model_name, {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000})
        cost = (input_tokens * rates["input"]) + (output_tokens * rates["output"])
        return round(cost, 7)

    async def generate_answer(
        self,
        question: str,
        retrieved_chunks: List[Dict[str, Any]],
        model_name: str,
        organization_name: str = "your organization"
    ) -> Dict[str, Any]:
        """
        Generate grounded answer strictly using the provided context chunks.
        If no chunks or information missing, return exact NOT_FOUND_MESSAGE.
        """
        start_time = time.perf_counter()

        if not retrieved_chunks:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return {
                "answer": NOT_FOUND_MESSAGE,
                "model_used": model_name,
                "input_tokens": 0,
                "output_tokens": len(NOT_FOUND_MESSAGE.split()),
                "estimated_cost": 0.0,
                "latency_ms": round(latency_ms, 2),
                "citations": []
            }

        # Build context
        context_parts = []
        citations = []
        for i, chunk in enumerate(retrieved_chunks):
            doc_name = chunk.get("metadata", {}).get("filename", f"Doc {i+1}")
            page = chunk.get("metadata", {}).get("page_number", "")
            page_str = f" (Page {page})" if page else ""
            header = f"[Source {i+1}: {doc_name}{page_str}]"
            context_parts.append(f"{header}\n{chunk['content']}")
            citations.append({
                "source": doc_name,
                "snippet": chunk["content"][:140] + "..." if len(chunk["content"]) > 140 else chunk["content"],
                "similarity": chunk.get("similarity", 0.0)
            })

        combined_context = "\n\n---\n\n".join(context_parts)

        system_instruction = (
            f"You are the official Enterprise AI Assistant for {organization_name}.\n"
            f"Your role is to answer questions strictly and truthfully using ONLY the provided organization document context.\n\n"
            f"CRITICAL GROUNDING RULES:\n"
            f"1. You must base your answer completely on the provided context.\n"
            f"2. If the answer cannot be found in the context or cannot be directly inferred from it, respond with EXACTLY:\n"
            f"   '{NOT_FOUND_MESSAGE}'\n"
            f"3. Do NOT use outside world knowledge or make assumptions.\n"
            f"4. Do NOT hallucinate.\n"
            f"5. Keep the response professional, clear, and well-structured with bullet points where appropriate."
        )

        prompt = (
            f"DOCUMENT CONTEXT:\n{combined_context}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"GROUNDED ANSWER:"
        )

        # Approximate tokens
        input_token_count = int((len(system_instruction) + len(prompt)) / 3.8)

        if not self._is_configured:
            # Fallback mock generator for offline development / test fixtures
            await asyncio.sleep(0.08)  # simulate brief network call
            answer = self._generate_mock_grounded_answer(question, retrieved_chunks)
            output_token_count = int(len(answer) / 3.8)
            latency_ms = (time.perf_counter() - start_time) * 1000
            cost = self.calculate_cost(model_name, input_token_count, output_token_count)
            return {
                "answer": answer,
                "model_used": model_name,
                "input_tokens": input_token_count,
                "output_tokens": output_token_count,
                "estimated_cost": cost,
                "latency_ms": round(latency_ms, 2),
                "citations": citations
            }

        # Live Gemini API call
        loop = asyncio.get_running_loop()
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction
            )
            response = await loop.run_in_executor(
                None,
                lambda: model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=1024,
                    )
                )
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            answer_text = response.text.strip() if response and response.text else NOT_FOUND_MESSAGE

            # Extract actual token counts if available
            usage = getattr(response, "usage_metadata", None)
            if usage:
                in_tok = getattr(usage, "prompt_token_count", input_token_count)
                out_tok = getattr(usage, "candidates_token_count", int(len(answer_text) / 3.8))
            else:
                in_tok = input_token_count
                out_tok = int(len(answer_text) / 3.8)

            cost = self.calculate_cost(model_name, in_tok, out_tok)
            return {
                "answer": answer_text,
                "model_used": model_name,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "estimated_cost": cost,
                "latency_ms": round(latency_ms, 2),
                "citations": citations
            }
        except Exception as e:
            logger.error("Error during Gemini generation (%s). Using grounded fallback extract.", e)
            answer = self._generate_mock_grounded_answer(question, retrieved_chunks)
            latency_ms = (time.perf_counter() - start_time) * 1000
            return {
                "answer": answer,
                "model_used": f"{model_name}-fallback",
                "input_tokens": input_token_count,
                "output_tokens": int(len(answer) / 3.8),
                "estimated_cost": 0.0,
                "latency_ms": round(latency_ms, 2),
                "citations": citations
            }

    def _generate_mock_grounded_answer(self, question: str, chunks: List[Dict[str, Any]]) -> str:
        """
        Extractive grounded heuristic when running without live Gemini credentials.
        """
        q_lower = question.lower()
        matched_sentences = []

        for chunk in chunks:
            content = chunk.get("content", "")
            sentences = [s.strip() for s in content.replace("\n", ". ").split(". ") if s.strip()]
            for s in sentences:
                s_lower = s.lower()
                # Check keyword overlap
                q_words = [w for w in q_lower.split() if len(w) > 3]
                if any(w in s_lower for w in q_words):
                    matched_sentences.append(s)

        if not matched_sentences:
            return NOT_FOUND_MESSAGE

        # Deduplicate and format
        unique_matches = list(dict.fromkeys(matched_sentences))[:3]
        return ". ".join(unique_matches) + "."


grounded_generator = GroundedGenerator()
