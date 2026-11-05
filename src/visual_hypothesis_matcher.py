"""Visual Hypothesis Matcher Module.
Implements the 4th Hybrid Layer:
1. Detects ambiguous mathematical / gene / vector tokens containing confusing characters:
   - '1' vs '/' vs 'I' vs 'l' vs '|'
   - Greek letters and special math symbols (α, β, γ, µ, °, etc.)
2. Generates all possible candidate permutations (Hypothesis Space).
3. Uses Unicode font rendering (DejaVu Sans / Arial Unicode MS) for template & contour matching,
   avoiding missing glyphs in Vietnamese fonts for Greek/Math characters.
4. Uses 2-3px padding when cropping bounding boxes from original image to avoid clipping character edges.
5. Evaluates each candidate against visual match confidence + scientific context priors.
"""

import itertools
import math
import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


class VisualHypothesisMatcher:
    """Matches ambiguous OCR tokens by testing candidate permutations
    and selecting the candidate with the highest visual and contextual confidence.
    """

    AMBIGUOUS_MAP = {
        "1": ["1", "/", "I", "l"],
        "/": ["/", "1", "I", "l"],
        "I": ["I", "1", "/", "l"],
        "l": ["l", "1", "/", "I"],
        "L": ["L", "1", "/"],
        "|": ["/", "1", "I"],
        "'": ["'", "°"],
        "\"": ["\"", "°", "'"],
        "%": ["%", "°"],
        "*": ["*", "°", "'", "×"],
        "^": ["^", "°"],
        "u": ["u", "µ"],
        "p": ["p", "µ"],
        "A": ["A", "µ"],
        "x": ["x", "×"],
    }

    # Available high-coverage Unicode fonts for Greek & Math matching
    UNICODE_FONTS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]

    def __init__(self, font_size: int = 32) -> None:
        self.font_size = font_size
        self.font: Optional[ImageFont.FreeTypeFont] = None
        self._init_unicode_font()

    def _init_unicode_font(self) -> None:
        """Initialize Unicode font (DejaVu Sans / Arial Unicode MS fallback)."""
        for path in self.UNICODE_FONTS:
            if os.path.exists(path):
                try:
                    self.font = ImageFont.truetype(path, self.font_size)
                    break
                except Exception:
                    continue

    @classmethod
    def generate_candidates(cls, token: str, prev_context: str = "") -> List[str]:
        """Generate plausible hypothesis permutations for a given token strictly from AMBIGUOUS_MAP."""
        chars = list(token)
        positions = [i for i, c in enumerate(chars) if c in cls.AMBIGUOUS_MAP]

        candidates: Set[str] = {token}

        if positions and len(positions) <= 5:
            options = [cls.AMBIGUOUS_MAP[chars[i]] for i in positions]
            for combo in itertools.product(*options):
                token_copy = list(chars)
                for idx, repl in zip(positions, combo):
                    token_copy[idx] = repl
                candidates.add("".join(token_copy))
        elif len(positions) > 5:
            # For longer tokens with many ambiguous positions, generate single and pair swaps
            for i in positions:
                for repl in cls.AMBIGUOUS_MAP[chars[i]]:
                    token_copy = list(chars)
                    token_copy[i] = repl
                    candidates.add("".join(token_copy))

        return list(candidates)

    @staticmethod
    def crop_with_padding(
        image: np.ndarray,
        bbox: Tuple[int, int, int, int],
        pad: int = 3,
    ) -> np.ndarray:
        """Crop an image region with 2-3 pixel padding to prevent tight edge clipping."""
        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox
        px1 = max(0, x1 - pad)
        py1 = max(0, y1 - pad)
        px2 = min(w, x2 + pad)
        py2 = min(h, y2 + pad)
        return image[py1:py2, px1:px2]

    def render_char_template(self, char: str, target_size: Tuple[int, int] = (40, 40)) -> np.ndarray:
        """Render a single character using DejaVu Sans / Arial Unicode MS font into a binary template."""
        tw, th = target_size
        img = Image.new("L", (tw, th), 255)
        draw = ImageDraw.Draw(img)

        if self.font:
            try:
                # Center text in box
                bbox = draw.textbbox((0, 0), char, font=self.font)
                cw = bbox[2] - bbox[0]
                ch = bbox[3] - bbox[1]
                ox = max(0, (tw - cw) // 2)
                oy = max(0, (th - ch) // 2)
                draw.text((ox, oy), char, font=self.font, fill=0)
            except Exception:
                draw.text((tw // 4, th // 4), char, fill=0)
        else:
            draw.text((tw // 4, th // 4), char, fill=0)

        return np.array(img)

    def match_visual_char(self, crop_img: np.ndarray, char_candidate: str) -> float:
        """Compare cropped character from original image against DejaVu Sans rendered glyph."""
        if crop_img is None or crop_img.size == 0:
            return 0.5

        if len(crop_img.shape) == 3:
            gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = crop_img.copy()

        # Resize crop to standard template height (40px) keeping aspect ratio
        ch, cw = gray.shape[:2]
        if ch <= 0 or cw <= 0:
            return 0.5

        target_h = 40
        target_w = max(10, int(cw * (target_h / ch)))
        resized_crop = cv2.resize(gray, (target_w, target_h), interpolation=cv2.INTER_AREA)

        # Render glyph template
        template = self.render_char_template(char_candidate, target_size=(max(target_w, 40), target_h))

        # Crop matching region
        if template.shape[1] > resized_crop.shape[1]:
            template = template[:, : resized_crop.shape[1]]
        elif resized_crop.shape[1] > template.shape[1]:
            resized_crop = resized_crop[:, : template.shape[1]]

        try:
            res = cv2.matchTemplate(resized_crop, template, cv2.TM_CCOEFF_NORMED)
            val = float(res.max())
            return max(0.0, val)
        except Exception:
            return 0.5

    @staticmethod
    def analyze_stroke_slant(crop_img: np.ndarray) -> float:
        """Analyze the dominant stroke orientation of an ambiguous character.
        Returns:
            Angle in degrees from horizontal:
            - ~85-95 deg: Vertical stroke (indicates '1', 'I', 'l', '|')
            - ~55-75 deg: Slanted stroke (indicates '/')
        """
        if crop_img is None or crop_img.size == 0:
            return 90.0

        if len(crop_img.shape) == 3:
            gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = crop_img

        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=15)

        if lines is None:
            return 90.0

        angles = []
        for line in lines[:5]:
            rho, theta = line[0]
            angle_deg = math.degrees(theta)
            angles.append(angle_deg)

        return float(np.median(angles)) if angles else 90.0

    @classmethod
    def score_candidate(cls, candidate: str, raw_token: str) -> float:
        """Calculate general structural confidence score for a candidate permutation
        without any hardcoded domain-specific gene/vector strings.
        """
        score = 0.5  # Base prior

        # General structural coherence: penalize unnatural consecutive slashes or mixed pipe/slash
        if "//" in candidate and "://" not in candidate:
            score -= 0.20

        # Penalize isolated slash at the very beginning or end of an alphanumeric token
        if (candidate.startswith("/") or candidate.endswith("/")) and len(candidate) > 1:
            score -= 0.15

        # Slight preference for preserving the original OCR reading unless visual evidence overrides it
        if candidate == raw_token:
            score += 0.05

        return score

    def disambiguate_token(
        self,
        token: str,
        prev_context: str = "",
        crop_img: Optional[np.ndarray] = None,
        initial_conf: Optional[float] = None,
        search_scorer: Optional[Callable[[str, str], float]] = None,
    ) -> str:
        """Generate all hypotheses for token and return candidate with highest visual, structural,
        and context-phrase search confidence.
        Preceding context is strictly read-only and used only to form full-phrase search queries.
        """
        candidates = self.generate_candidates(token, prev_context=prev_context)
        if len(candidates) <= 1:
            return token

        # Preserve leading/trailing punctuation when scoring/searching
        leading_punct = re.match(r"^[.,;:()\[\]{}]*", token).group(0)
        trailing_punct = re.search(r"[.,;:()\[\]{}]*$", token).group(0)

        def eval_cand(cand: str) -> float:
            score = self.score_candidate(cand, token)
            clean_cand = cand.strip(".,;:()[]{}")

            # 1. Context-phrase search verification (queries "<prev_context> <clean_cand>")
            if search_scorer is not None and clean_cand:
                score += search_scorer(prev_context, clean_cand)

            # 2. Visual Unicode font template matching and stroke slant analysis
            if crop_img is not None and crop_img.size > 0:
                slant = self.analyze_stroke_slant(crop_img)
                visual_sim = self.match_visual_char(crop_img, clean_cand or cand)
                score = 0.5 * score + 0.5 * visual_sim
                if "/" in cand and 50.0 <= slant <= 78.0:
                    score += 0.20
                elif ("1" in cand or "I" in cand) and 82.0 <= slant <= 98.0:
                    score += 0.20

            return score

        # Step 3: Evaluate initial token score first
        initial_score = eval_cand(token)
        if initial_conf is not None:
            initial_score = (initial_score + float(initial_conf)) / 2.0

        best_cand = token
        best_score = initial_score

        # Step 4: Compare with all other permutation candidates
        for cand in candidates:
            if cand == token:
                continue

            score = eval_cand(cand)

            # Strictly require candidate to beat initial score to replace it
            if score > best_score:
                best_score = score
                best_cand = cand

        return best_cand

    def process_text_tokens(
        self,
        text: str,
        crop_img: Optional[np.ndarray] = None,
        initial_conf: Optional[float] = None,
        search_scorer: Optional[Callable[[str, str], float]] = None,
        search_fn: Optional[Callable[[str], Optional[str]]] = None,
    ) -> str:
        """Scan text, use LLM with read-only preceding context + phrase search + visual candidates
        to both classify and resolve difficult scientific tokens without hardcoded regex rules.
        Normal/easy words and preceding context words are NEVER modified.
        """
        if not text:
            return ""

        tokens = text.split(" ")

        from src.llm_difficulty_filter import LLMDifficultyFilter
        if not hasattr(self, "_llm_filter"):
            self._llm_filter = LLMDifficultyFilter(enable_llm=True)

        # 1. Ask LLM to resolve hard tokens directly using preceding context + search + candidate permutations
        llm_corrections = self._llm_filter.resolve_with_context_and_search(
            tokens,
            candidate_generator=self.generate_candidates,
            search_fn=search_fn,
            context_window=3,
        )

        # 2. Also get the hard token map for visual/search fallback if LLM is offline/unavailable
        hard_map = self._llm_filter.classify_tokens_with_context(tokens, context_window=3)

        refined_tokens = []
        for idx, tok in enumerate(tokens):
            if idx in llm_corrections:
                refined_tokens.append(llm_corrections[idx])
            elif idx in hard_map:
                prev_ctx = hard_map[idx]
                best = self.disambiguate_token(
                    tok,
                    prev_context=prev_ctx,
                    crop_img=crop_img,
                    initial_conf=initial_conf,
                    search_scorer=search_scorer,
                )
                refined_tokens.append(best)
            else:
                # Normal / easy words MUST NEVER BE TOUCHED
                refined_tokens.append(tok)

        return " ".join(refined_tokens)
