"""LLM-Assisted Difficulty Filter Module (Offline Ultra-lightweight LLM).
Classifies words into:
- EASY_NORMAL: Common words, regular dictionary words, standard sentences -> STRICTLY DO NOT TOUCH!
- HARD_SPECIAL: Highly anomalous scientific nomenclature, plasmids, gene codes, math symbols,
  confusing slashes/digits ('1', '/', 'I', 'l') -> SENT TO VISUAL HYPOTHESIS & SO KHỚP.
"""

import json
import os
import re
from typing import Dict, List, Optional, Set, Tuple

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError:
    torch = None


class LLMDifficultyFilter:
    """Uses the offline lightweight Qwen2.5-0.5B model to strictly filter
    only truly difficult/special scientific words before permitting any modification.
    """

    MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

    def __init__(self, enable_llm: bool = True) -> None:
        self.enable_llm = enable_llm
        self.model = None
        self.tokenizer = None
        self._llm_loaded = False
        self._cache_hard: Set[str] = set()
        self._cache_easy: Set[str] = set()

    def _lazy_load_model(self) -> None:
        """Lazy load the offline 0.5B model only when needed to save startup time & RAM."""
        if self._llm_loaded or not self.enable_llm or torch is None:
            return

        try:
            print("[LLM Filter] Loading offline ultra-lightweight Qwen2.5-0.5B-Instruct model...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID, local_files_only=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.MODEL_ID,
                local_files_only=True,
                dtype=torch.float32,
            )
            self._llm_loaded = True
            print("[LLM Filter] Offline LLM Difficulty Filter ready.")
        except Exception as e:
            print(f"[LLM Filter] Warning: Could not load offline LLM ({e}), falling back to heuristic filter.")
            self._llm_loaded = False

    def is_easy_word(self, token: str) -> bool:
        """Fast check for standard normal words that must NEVER be touched."""
        clean = token.strip(".,;:()[]{}'\"")
        if not clean:
            return True

        # Pure alphabetic common words in Vietnamese or English (lowercase words without scientific notation)
        if clean.isalpha():
            # Keep single-letter uppercase or short uppercase tokens for context inspection (e.g., C, V, M, W, HF, PCR)
            if clean.isupper() and len(clean) <= 4:
                return False
            # Keep tokens that look like Greek/micro prefix + unit or Roman numeral suffix
            if re.search(r"^[µuUα-ωΑ-Ω][A-Za-z]{1,4}$", clean):
                return False
            if re.search(r"[A-Z][a-z]+[IVXLCDM]{1,4}$", clean):
                return False
            return True

        # Simple single punctuation or standard pure numbers like 2024, 15, 3
        if clean.isdigit() and len(clean) <= 4:
            return True

        return False

    def classify_tokens_with_context(
        self,
        tokens: List[str],
        context_window: int = 2,
    ) -> Dict[int, str]:
        """Classify tokens by inspecting each candidate junto with its preceding words (read-only context).
        Returns a mapping {token_index: preceding_context_phrase} for tokens deemed 'HARD_SPECIAL'.
        Preceding words are NEVER modified; they are only used to understand context and form search queries.
        """
        hard_indices: Dict[int, str] = {}
        candidate_items: List[Dict[str, object]] = []

        for idx, tok in enumerate(tokens):
            clean = tok.strip(".,;:()[]{}")
            if not clean:
                continue

            # Extract up to `context_window` preceding tokens for read-only context
            start_ctx = max(0, idx - context_window)
            prev_tokens = [t.strip(".,;:()[]{}") for t in tokens[start_ctx:idx] if t.strip(".,;:()[]{}")]
            prev_context = " ".join(prev_tokens)

            if clean in self._cache_hard:
                hard_indices[idx] = prev_context
                continue
            if clean in self._cache_easy or self.is_easy_word(tok):
                self._cache_easy.add(clean)
                continue

            # Check if token or (preceding number + token) is a candidate for scientific / symbol / unit ambiguity
            is_hard_candidate = False
            prev_is_number = bool(prev_tokens and re.search(r"\d", prev_tokens[-1]))

            # 1. Mixed alphanumeric tokens (digits + letters/symbols)
            if re.search(r"\d+[A-Za-zµα-ωΑ-Ω°\'\"%*]+|[A-Za-zµα-ωΑ-Ω°\'\"%*]+\d+", clean):
                is_hard_candidate = True

            # 2. Preceded by a number/quantity and looks like a unit, degree, or symbol (e.g., "37 'C", "80 %C", "10 uM")
            elif prev_is_number and (
                re.search(r"^[\'\"%*\^°]?[A-Za-zµα-ωΑ-Ω]{1,5}$", clean)
                or any(ch in clean for ch in ["'", "\"", "%", "*", "^", "°", "/", "µ"])
            ):
                is_hard_candidate = True

            # 3. Greek characters or micro-like unit prefixes
            elif re.search(r"[µα-ωΑ-Ω°]", clean) or re.search(r"^[uU][A-Za-z]{1,4}$", clean):
                is_hard_candidate = True

            # 4. Roman numerals or scientific nomenclature with uppercase/symbol mix
            elif re.search(r"[A-Z][a-z]+[IVXLCDM]{1,4}\b", clean) or re.search(r"\b[IVXLCDM]{2,}\b", clean):
                is_hard_candidate = True

            # 5. Ambiguous characters (1, /, I, l, |, ', *, %) or scientific operators
            elif any(ch in clean for ch in ["1", "/", "I", "l", "|", "-", "_", "*", "'", "^", "%"]):
                if "-" in clean and not any(c.isupper() or c.isdigit() for c in clean):
                    is_hard_candidate = False
                else:
                    is_hard_candidate = True

            if is_hard_candidate:
                candidate_items.append({
                    "index": idx,
                    "target_token": clean,
                    "preceding_context": prev_context,
                    "full_phrase": f"{prev_context} {clean}".strip(),
                })

        if not candidate_items:
            return hard_indices

        # If LLM is enabled and loaded, ask LLM to evaluate target tokens using their preceding context
        self._lazy_load_model()
        if self._llm_loaded and self.tokenizer and self.model:
            try:
                batch = candidate_items[:25]
                prompt_payload = [
                    {
                        "target": item["target_token"],
                        "preceding_context": item["preceding_context"],
                        "phrase": item["full_phrase"],
                    }
                    for item in batch
                ]
                prompt = (
                    "You are an academic OCR difficulty and context analyzer. "
                    "For each item, examine the 'target' token insieme with its 'preceding_context' words. "
                    "IMPORTANT: Do NOT mark the preceding context words for modification — use the preceding words ONLY to recognize the context "
                    "(for example, whether a preceding number or scientific term indicates that the target token is a measurement unit, temperature degree symbol, concentration, "
                    "Greek letter / micro prefix, or mathematical/scientific notation). "
                    "Identify ONLY the 'target' tokens that have HIGH OCR difficulty ('HARD_SPECIAL'): "
                    "scientific measurement units, tokens resembling or related to Greek characters, temperature/degree symbols, "
                    "or general scientific symbols and nomenclature that should be verified as a full phrase via search. "
                    "Do NOT include normal dictionary words or plain text. "
                    f"Return ONLY a JSON array of the selected 'target' strings.\nItems: {json.dumps(prompt_payload, ensure_ascii=False)}"
                )

                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You analyze preceding context words (read-only) to identify high-difficulty scientific target tokens "
                            "and output ONLY a JSON array of target strings."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]
                text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = self.tokenizer([text], return_tensors="pt")
                with torch.no_grad():
                    outputs = self.model.generate(**inputs, max_new_tokens=150, do_sample=False)
                res = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1] :], skip_special_tokens=True)

                # Extract JSON array
                match = re.search(r"\[.*?\]", res, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    selected_targets = {str(x).strip() for x in parsed}
                    for item in candidate_items:
                        t_str = str(item["target_token"])
                        idx = int(item["index"])
                        if t_str in selected_targets:
                            self._cache_hard.add(t_str)
                            hard_indices[idx] = str(item["preceding_context"])
                    return hard_indices
            except Exception:
                pass

        # Context-aware structural fallback if offline LLM is unavailable
        for item in candidate_items:
            cand = str(item["target_token"])
            prev_ctx = str(item["preceding_context"])
            idx = int(item["index"])
            prev_has_num = bool(re.search(r"\d", prev_ctx))

            if (
                re.search(r"[A-Za-z0-9]+[-_/|][A-Za-z0-9]+", cand)
                or re.search(r"\d+[A-Za-zµα-ωΑ-Ω°\'\"%*]+|[A-Za-zµα-ωΑ-Ω°\'\"%*]+\d+", cand)
                or re.search(r"[µα-ωΑ-Ω°]", cand)
                or re.search(r"^[uU][A-Za-z]{1,4}$", cand)
                or (prev_has_num and re.search(r"^[\'\"%*\^°]?[A-Za-zµα-ωΑ-Ω]{1,5}$", cand))
            ):
                self._cache_hard.add(cand)
                hard_indices[idx] = prev_ctx
            else:
                self._cache_easy.add(cand)

        return hard_indices

    def resolve_with_context_and_search(
        self,
        tokens: List[str],
        candidate_generator,
        search_fn=None,
        context_window: int = 3,
    ) -> Dict[int, str]:
        """Use the LLM with preceding context + search evidence + candidate permutations
        to both IDENTIFY and RESOLVE high-difficulty scientific tokens without hardcoded regex rules.
        Preceding context words are strictly read-only and never modified.
        Returns a mapping {token_index: corrected_token}.
        """
        hard_map = self.classify_tokens_with_context(tokens, context_window=context_window)
        if not hard_map:
            return {}

        self._lazy_load_model()
        if not (self._llm_loaded and self.tokenizer and self.model):
            return {}

        corrections: Dict[int, str] = {}
        items_for_llm = []

        for idx, prev_ctx in hard_map.items():
            raw_tok = tokens[idx]
            # Preserve outer punctuation (e.g. parentheses, commas, semicolons)
            lead_m = re.match(r"^[.,;:()\[\]{}]*", raw_tok)
            trail_m = re.search(r"[.,;:()\[\]{}]*$", raw_tok)
            lead_p = lead_m.group(0) if lead_m else ""
            trail_p = trail_m.group(0) if trail_m else ""
            core_tok = raw_tok[len(lead_p) : len(raw_tok) - len(trail_p) if trail_p else len(raw_tok)]
            if not core_tok:
                continue

            # Generate general symbol permutations (no hardcoded domain strings)
            cands = candidate_generator(core_tok, prev_context=prev_ctx)
            if len(cands) <= 1:
                continue

            # Gather web search snippets for (preceding_context + candidate) if search_fn is provided
            search_hints = []
            if search_fn is not None:
                last_prev = prev_ctx.split()[-1] if prev_ctx else ""
                for c in cands[:6]:
                    phrase = f"{last_prev} {c}".strip()
                    res = search_fn(phrase)
                    if res and c in res:
                        search_hints.append(c)

            items_for_llm.append({
                "idx": idx,
                "lead": lead_p,
                "trail": trail_p,
                "core": core_tok,
                "preceding_context": prev_ctx,
                "candidates": cands[:12],
                "search_verified": search_hints,
            })

        if not items_for_llm:
            return corrections

        # Process in small batches so the 0.5B LLM can reason accurately over each item's context
        batch_size = 8
        for b_start in range(0, len(items_for_llm), batch_size):
            batch = items_for_llm[b_start : b_start + batch_size]
            prompt_data = [
                {
                    "id": item["idx"],
                    "preceding_context": item["preceding_context"],
                    "ocr_token": item["core"],
                    "candidates": item["candidates"],
                    "search_hits": item["search_verified"],
                }
                for item in batch
            ]

            prompt = (
                "You are an expert scientific OCR context resolver. "
                "Each item below contains a special scientific 'ocr_token', its read-only 'preceding_context' words, "
                "a list of visual permutation 'candidates' (where characters like ', %, *, u, p, A, l, I, 1, / may have been misread by OCR "
                "from scientific/Greek symbols like °, µ, /, ×, or superscripts), and 'search_hits' from phrase search. "
                "RULES:\n"
                "1. NEVER modify 'preceding_context'. Use 'preceding_context' ONLY to understand the scientific meaning:\n"
                "   - If 'preceding_context' is a number or thermal phrase (e.g., temperature, cycling, incubation), select the candidate with the degree symbol (°C, °C/time).\n"
                "   - If 'preceding_context' is a volume, mass, molarity, or enzyme activity number, select the candidate with the proper Greek micro symbol (µl, µg, µM, U/µl, ng/µl, µg/ml, cfu/µg).\n"
                "   - If 'ocr_token' is a scientific notation, gene/isoform slash sequence, vector, or restriction enzyme, select the candidate with proper slashes (/), digits (1), or Roman numerals (I).\n"
                "2. Select the single most accurate string from 'candidates' (or output the corrected scientific notation for 'ocr_token').\n"
                "Return ONLY a JSON object mapping each 'id' (as string) to the chosen corrected string.\n"
                f"Items: {json.dumps(prompt_data, ensure_ascii=False)}"
            )

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You resolve OCR errors on scientific symbols, Greek letters (µ), degree symbols (°), units, and slashes (/) "
                        "using preceding context (read-only) and candidate permutations. Output ONLY valid JSON mapping id to corrected token."
                    ),
                },
                {"role": "user", "content": prompt},
            ]

            try:
                text_in = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = self.tokenizer([text_in], return_tensors="pt")
                with torch.no_grad():
                    outputs = self.model.generate(**inputs, max_new_tokens=220, do_sample=False)
                res = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1] :], skip_special_tokens=True)

                match = re.search(r"\{.*?\}", res, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    for item in batch:
                        str_id = str(item["idx"])
                        if str_id in parsed and isinstance(parsed[str_id], str):
                            chosen = parsed[str_id].strip()
                            if chosen:
                                corrections[item["idx"]] = f"{item['lead']}{chosen}{item['trail']}"
            except Exception:
                continue

        return corrections

    def classify_tokens(self, tokens: List[str]) -> Set[str]:
        """Backward-compatible wrapper returning the set of hard tokens."""
        hard_map = self.classify_tokens_with_context(tokens)
        return {tokens[i] for i in hard_map}
