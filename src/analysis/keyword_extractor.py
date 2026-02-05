"""
Keyword extraction module for news analysis.
Supports multiple extraction methods: KoNLPy, KeyBERT, KR-WordRank.
"""
from typing import List, Optional, Set, Tuple

from src.utils.exceptions import KeywordExtractionError
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Stop words for Korean text
KOREAN_STOP_WORDS = {
    # Common particles and endings
    "것", "수", "등", "및", "중", "위", "말", "더", "때", "곳", "데",
    "점", "번", "회", "차", "측", "간", "내", "후", "전", "현", "대",
    # Common verbs/adjectives
    "있다", "하다", "되다", "이다", "없다", "같다", "보다", "않다",
    # Time-related
    "오늘", "어제", "내일", "올해", "지난해", "작년", "현재", "최근",
    # Numbers and counters
    "억", "만", "원", "달러", "개", "명", "건", "곳",
    # Other common words
    "뉴스", "기자", "기사", "보도", "발표", "관련", "대해", "통해",
}


class KeywordExtractor:
    """
    Korean keyword extractor using multiple methods.

    Supports:
    - KoNLPy (noun extraction using morphological analysis)
    - KeyBERT (semantic keyword extraction using transformers)
    - Combined approach (intersection/union of methods)
    """

    def __init__(
        self,
        method: str = "combined",
        min_keyword_length: int = 2,
        top_n: int = 15,
    ):
        """
        Initialize keyword extractor.

        Args:
            method: Extraction method ("konlpy", "keybert", "combined")
            min_keyword_length: Minimum keyword length
            top_n: Number of keywords to extract
        """
        self.method = method
        self.min_keyword_length = min_keyword_length
        self.top_n = top_n

        # Lazy-loaded components
        self._okt = None
        self._keybert = None

    @property
    def okt(self):
        """Lazy load KoNLPy Okt tokenizer."""
        if self._okt is None:
            try:
                from konlpy.tag import Okt
                self._okt = Okt()
                logger.info("KoNLPy Okt initialized")
            except ImportError:
                logger.warning("KoNLPy not installed, noun extraction disabled")
                raise KeywordExtractionError(
                    "KoNLPy not installed. Run: pip install konlpy"
                )
        return self._okt

    @property
    def keybert(self):
        """Lazy load KeyBERT model."""
        if self._keybert is None:
            try:
                from keybert import KeyBERT
                # Use multilingual model for Korean support
                self._keybert = KeyBERT("paraphrase-multilingual-MiniLM-L12-v2")
                logger.info("KeyBERT initialized with multilingual model")
            except ImportError:
                logger.warning("KeyBERT not installed")
                raise KeywordExtractionError(
                    "KeyBERT not installed. Run: pip install keybert"
                )
        return self._keybert

    def extract(self, text: str) -> List[str]:
        """
        Extract keywords from text using configured method.

        Args:
            text: Text to extract keywords from

        Returns:
            List of keywords
        """
        if not text or not text.strip():
            return []

        try:
            if self.method == "konlpy":
                return self.extract_nouns(text)
            elif self.method == "keybert":
                keywords = self.extract_keybert(text)
                return [kw for kw, score in keywords]
            else:  # combined
                return self.extract_combined(text)
        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")
            # Fallback to simple extraction
            return self._simple_extract(text)

    def extract_nouns(self, text: str) -> List[str]:
        """
        Extract nouns using KoNLPy morphological analysis.

        Args:
            text: Text to analyze

        Returns:
            List of noun keywords
        """
        try:
            nouns = self.okt.nouns(text)

            # Filter and clean
            filtered = []
            for noun in nouns:
                if len(noun) < self.min_keyword_length:
                    continue
                if noun in KOREAN_STOP_WORDS:
                    continue
                if noun.isdigit():
                    continue
                filtered.append(noun)

            # Count frequencies and return top N
            from collections import Counter
            counts = Counter(filtered)
            return [word for word, _ in counts.most_common(self.top_n)]

        except Exception as e:
            raise KeywordExtractionError(f"Noun extraction failed: {e}", cause=e)

    def extract_keybert(
        self,
        text: str,
        diversity: float = 0.7,
    ) -> List[Tuple[str, float]]:
        """
        Extract keywords using KeyBERT semantic similarity.

        Args:
            text: Text to analyze
            diversity: MMR diversity parameter (0-1)

        Returns:
            List of (keyword, score) tuples
        """
        try:
            # Limit text length for model
            text = text[:5000]

            keywords = self.keybert.extract_keywords(
                text,
                keyphrase_ngram_range=(1, 2),
                stop_words=None,
                top_n=self.top_n,
                use_mmr=True,
                diversity=diversity,
            )

            # Filter by length and stop words
            filtered = []
            for kw, score in keywords:
                if len(kw) < self.min_keyword_length:
                    continue
                if kw in KOREAN_STOP_WORDS:
                    continue
                filtered.append((kw, score))

            return filtered

        except Exception as e:
            raise KeywordExtractionError(f"KeyBERT extraction failed: {e}", cause=e)

    def extract_combined(self, text: str) -> List[str]:
        """
        Extract keywords using combined approach.

        Combines noun extraction (high precision) with KeyBERT (high recall).

        Args:
            text: Text to analyze

        Returns:
            List of keywords
        """
        combined_keywords: Set[str] = set()

        # Try KoNLPy first
        try:
            nouns = self.extract_nouns(text)
            combined_keywords.update(nouns[:self.top_n])
        except Exception as e:
            logger.debug(f"KoNLPy extraction skipped: {e}")

        # Try KeyBERT
        try:
            keybert_results = self.extract_keybert(text)
            for kw, score in keybert_results:
                # Add high-confidence keywords
                if score > 0.3:
                    combined_keywords.add(kw)
        except Exception as e:
            logger.debug(f"KeyBERT extraction skipped: {e}")

        # If both methods failed, use simple extraction
        if not combined_keywords:
            return self._simple_extract(text)

        return list(combined_keywords)[:self.top_n]

    def _simple_extract(self, text: str) -> List[str]:
        """
        Simple keyword extraction fallback.

        Uses basic word frequency analysis.

        Args:
            text: Text to analyze

        Returns:
            List of keywords
        """
        import re
        from collections import Counter

        # Extract Korean words (2+ chars)
        words = re.findall(r"[가-힣]{2,}", text)

        # Filter stop words
        filtered = [w for w in words if w not in KOREAN_STOP_WORDS]

        # Return most common
        counts = Counter(filtered)
        return [word for word, _ in counts.most_common(self.top_n)]

    def extract_with_scores(self, text: str) -> List[Tuple[str, float]]:
        """
        Extract keywords with relevance scores.

        Args:
            text: Text to analyze

        Returns:
            List of (keyword, score) tuples
        """
        try:
            return self.extract_keybert(text)
        except Exception:
            # Fallback without scores
            keywords = self.extract(text)
            return [(kw, 1.0 / (i + 1)) for i, kw in enumerate(keywords)]
