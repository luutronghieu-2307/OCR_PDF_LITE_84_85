"""Search-Augmented Refinement Module (OCR + Fast Web Search + Offline Context Engine).
Uses online biological / chemical / academic knowledge bases to cross-verify
and correct OCR errors (e.g., misread slashes '/', digits '1', roman numerals 'I', units).
"""

import json
import re
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Set

import numpy as np


class SearchAugmentedRefiner:
    """Refines OCR texts by verifying technical and scientific terms against online knowledge."""

    def __init__(self, enable_web: bool = True) -> None:
        self.enable_web = enable_web
        self._cache: Dict[str, str] = {}
        from src.visual_hypothesis_matcher import VisualHypothesisMatcher
        self.matcher = VisualHypothesisMatcher()

    def search_canonical_name(self, term: str) -> Optional[str]:
        """Search Wikipedia / Wikidata / NCBI for canonical scientific nomenclature or unit phrase."""
        if not self.enable_web or not term or len(term) < 2:
            return None

        if term in self._cache:
            return self._cache[term]

        encoded = urllib.parse.quote(term)
        # 1. Try Opensearch for exact title match
        url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit=3&namespace=0&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AcademicOCRRefiner/1.0)"})
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                titles = data[1] if len(data) > 1 else []
                if titles:
                    canonical = titles[0]
                    self._cache[term] = canonical
                    return canonical
        except Exception:
            pass

        # 2. Try Wikipedia Query Search (snippet & title) for phrases with preceding context (e.g., "37 °C", "10 µl")
        query_url = (
            f"https://en.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={encoded}&srlimit=3&format=json"
        )
        req_q = urllib.request.Request(query_url, headers={"User-Agent": "Mozilla/5.0 (AcademicOCRRefiner/1.0)"})
        try:
            with urllib.request.urlopen(req_q, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("query", {}).get("search", [])
                if results:
                    # Combine top titles and snippets to check which candidate phrase actually appears
                    combined = " ".join(
                        f"{r.get('title', '')} {re.sub(r'<[^>]+>', '', r.get('snippet', ''))}"
                        for r in results
                    )
                    self._cache[term] = combined
                    return combined
        except Exception:
            pass

        self._cache[term] = ""
        return None

    def score_phrase_search(self, prev_context: str, candidate_token: str) -> float:
        """Query the full phrase (preceding context + candidate token) via search
        and return a confidence bonus if the candidate appears in canonical search results.
        Preceding context is strictly read-only.
        """
        if not self.enable_web:
            return 0.0

        # Use the immediate preceding token (e.g., number or scientific noun) + candidate to form a focused phrase
        prev_words = prev_context.split() if prev_context else []
        last_prev = prev_words[-1] if prev_words else ""
        phrase = f"{last_prev} {candidate_token}".strip()

        search_res = self.search_canonical_name(phrase)
        if not search_res:
            return 0.0

        # Check if the candidate token (with its special symbol like °C, µl, etc.) appears in the search results
        if candidate_token in search_res:
            return 0.35
        if candidate_token.lower() in search_res.lower():
            return 0.20
        return 0.0

    def refine_text(
        self,
        text: str,
        crop_img: Optional[np.ndarray] = None,
        initial_conf: Optional[float] = None,
    ) -> str:
        """Apply hybrid refinement using Context-Aware LLM Prompt Resolution + Phrase Search + Visual Hypothesis Permutations
        without any hardcoded regex replacement rules.
        """
        if not text:
            return ""

        text = self.matcher.process_text_tokens(
            text,
            crop_img=crop_img,
            initial_conf=initial_conf,
            search_scorer=self.score_phrase_search,
            search_fn=self.search_canonical_name,
        )
        return text
