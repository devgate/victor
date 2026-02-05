"""
Sentiment analysis module for news articles.
Uses Korean financial sentiment models.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.utils.exceptions import SentimentAnalysisError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SentimentLabel(Enum):
    """Sentiment classification labels."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class SentimentResult:
    """Sentiment analysis result."""
    label: SentimentLabel
    score: float  # Normalized score (-1 to 1)
    confidence: float  # Model confidence (0 to 1)

    @property
    def is_positive(self) -> bool:
        return self.label == SentimentLabel.POSITIVE

    @property
    def is_negative(self) -> bool:
        return self.label == SentimentLabel.NEGATIVE

    def to_dict(self) -> dict:
        return {
            "label": self.label.value,
            "score": self.score,
            "confidence": self.confidence,
        }


class SentimentAnalyzer:
    """
    Korean sentiment analyzer for financial news.

    Uses KR-FinBert or similar Korean financial sentiment model.
    Falls back to rule-based analysis if model is unavailable.
    """

    # Default model for Korean financial sentiment
    DEFAULT_MODEL = "snunlp/KR-FinBert-SC"

    # Keyword-based sentiment (fallback)
    POSITIVE_KEYWORDS = {
        "상승", "호실적", "증가", "성장", "수주", "계약", "매출",
        "이익", "호조", "상향", "돌파", "신고가", "개선", "확대",
        "인수", "투자", "협력", "긍정", "기대", "전망", "회복",
    }

    NEGATIVE_KEYWORDS = {
        "하락", "감소", "적자", "손실", "하향", "매도", "리콜",
        "소송", "규제", "조사", "철수", "파산", "부진", "우려",
        "악화", "축소", "위기", "불확실", "지연", "취소",
    }

    def __init__(
        self,
        model_name: Optional[str] = None,
        use_model: bool = True,
    ):
        """
        Initialize sentiment analyzer.

        Args:
            model_name: HuggingFace model name for sentiment analysis
            use_model: If False, use rule-based analysis only
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.use_model = use_model
        self._pipeline = None
        self._model_available = False

    def _load_model(self) -> bool:
        """
        Lazy load the sentiment model.

        Returns:
            True if model loaded successfully
        """
        if self._pipeline is not None:
            return self._model_available

        if not self.use_model:
            self._model_available = False
            return False

        try:
            from transformers import pipeline

            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                tokenizer=self.model_name,
                max_length=512,
                truncation=True,
            )
            self._model_available = True
            logger.info(f"Sentiment model loaded: {self.model_name}")
            return True

        except Exception as e:
            logger.warning(f"Failed to load sentiment model: {e}")
            logger.warning("Falling back to rule-based sentiment analysis")
            self._model_available = False
            return False

    def analyze(self, text: str) -> SentimentResult:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            SentimentResult with label, score, and confidence
        """
        if not text or not text.strip():
            return SentimentResult(
                label=SentimentLabel.NEUTRAL,
                score=0.0,
                confidence=0.0,
            )

        # Try model-based analysis first
        if self._load_model():
            try:
                return self._analyze_with_model(text)
            except Exception as e:
                logger.warning(f"Model analysis failed: {e}")

        # Fallback to rule-based
        return self._analyze_rule_based(text)

    def _analyze_with_model(self, text: str) -> SentimentResult:
        """
        Analyze sentiment using transformer model.

        Args:
            text: Text to analyze

        Returns:
            SentimentResult
        """
        # Truncate text to model max length
        text = text[:512]

        result = self._pipeline(text)[0]
        label_str = result["label"].lower()
        confidence = result["score"]

        # Map model output to our labels
        if "positive" in label_str or "pos" in label_str:
            label = SentimentLabel.POSITIVE
            score = confidence
        elif "negative" in label_str or "neg" in label_str:
            label = SentimentLabel.NEGATIVE
            score = -confidence
        else:
            label = SentimentLabel.NEUTRAL
            score = 0.0

        return SentimentResult(
            label=label,
            score=score,
            confidence=confidence,
        )

    def _analyze_rule_based(self, text: str) -> SentimentResult:
        """
        Analyze sentiment using keyword rules.

        Args:
            text: Text to analyze

        Returns:
            SentimentResult
        """
        text_lower = text.lower()

        # Count sentiment keywords
        positive_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
        negative_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)

        total = positive_count + negative_count

        if total == 0:
            return SentimentResult(
                label=SentimentLabel.NEUTRAL,
                score=0.0,
                confidence=0.3,
            )

        # Calculate score
        score = (positive_count - negative_count) / total
        confidence = min(total / 10, 1.0)  # More keywords = higher confidence

        # Determine label
        if score > 0.2:
            label = SentimentLabel.POSITIVE
        elif score < -0.2:
            label = SentimentLabel.NEGATIVE
        else:
            label = SentimentLabel.NEUTRAL

        return SentimentResult(
            label=label,
            score=score,
            confidence=confidence,
        )

    def analyze_batch(self, texts: list) -> list:
        """
        Analyze sentiment of multiple texts.

        Args:
            texts: List of texts to analyze

        Returns:
            List of SentimentResult objects
        """
        return [self.analyze(text) for text in texts]
