"""
Keyword extraction module for news analysis.
Supports multiple extraction methods: KoNLPy, KeyBERT, KR-WordRank.
"""
from typing import List, Optional, Set, Tuple

from src.utils.exceptions import KeywordExtractionError
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Stop words for Korean text (expanded for financial news filtering)
KOREAN_STOP_WORDS = {
    # Common particles, suffixes, and endings
    "것", "수", "등", "및", "중", "위", "말", "더", "때", "곳", "데",
    "점", "번", "회", "차", "측", "간", "내", "후", "전", "현", "대",
    "바", "씩", "별", "용", "약", "여", "이상", "이하", "이후", "이전",
    "개월", "가량", "정도", "가운데", "가지", "만큼", "에서", "부터",
    # Common verbs/adjectives (stem forms)
    "있다", "하다", "되다", "이다", "없다", "같다", "보다", "않다",
    "주다", "받다", "나오다", "알다", "좋다", "크다", "많다",
    "높다", "낮다", "작다", "새롭다", "어렵다", "쉽다",
    # Common adjective forms appearing in news
    "좋은", "다양한", "많은", "최고의", "새로운", "다른", "모든",
    "큰", "작은", "높은", "낮은", "중요한", "필요한", "주요",
    "최대", "최소", "주요한", "대표적", "기본적", "일반적",
    # Common nouns (non-financial, generic)
    "사람", "사회", "문제", "경우", "결과", "사실", "이유", "상황",
    "방법", "시간", "부분", "의미", "정도", "생각", "방향", "분야",
    "역할", "필요", "과정", "변화", "활동", "이용", "관계", "내용",
    "모습", "자리", "모두", "하나", "이후", "사이", "가운데", "의견",
    "함께", "단순", "국산", "국제", "국내", "해외", "글로벌",
    # Person/demographic (not financial)
    "노인", "청년", "학생", "여성", "남성", "아이", "가족", "부모",
    "자녀", "세대", "시민", "국민", "주민",
    # News/journalism boilerplate
    "뉴스", "기자", "기사", "보도", "발표", "관련", "대해", "통해",
    "연합뉴스", "송고", "댓글", "밝혔다", "전했다", "말했다",
    "따르면", "설명", "강조", "지적", "제공", "공개", "진행",
    "예정", "것으로", "판단", "분석", "확인", "조사", "실시",
    "관계자", "대변인", "취재", "보도자료", "언론", "인터뷰",
    # Time-related
    "오늘", "어제", "내일", "올해", "지난해", "작년", "현재", "최근",
    "이번", "지난", "다음", "매년", "연초", "연말", "상반기", "하반기",
    "분기", "월초", "월말", "당시", "이날",
    # Numbers and counters
    "억", "만", "원", "달러", "개", "명", "건", "곳", "배",
    "만원", "억원", "조원", "만명", "천명", "여명",
    # Common adverbs
    "또한", "특히", "이미", "다시", "계속", "아직", "매우", "가장",
    "직접", "실제", "상당", "여전히", "한편", "다만", "그러나",
    # Place names (generic, non-financial)
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    # Misc common words appearing in polluted data
    "겨냥한", "다채롭데이", "소폭", "명이", "인원이", "폰트",
    "급식", "패션", "채식", "주차장", "초슬림", "댓글",
}

# Financial domain terms for relevance filtering
FINANCIAL_DOMAIN_TERMS = {
    # Major Korean companies
    "삼성전자", "삼성", "SK하이닉스", "하이닉스", "네이버", "카카오",
    "LG에너지솔루션", "LG에너지", "삼성SDI", "셀트리온", "현대차", "기아",
    "삼성바이오로직스", "삼성바이오", "한화", "포스코", "롯데", "두산",
    "현대모비스", "SK이노베이션", "LG화학", "SK텔레콤", "KT", "LG전자",
    "한국전력", "신한지주", "KB금융", "하나금융", "우리금융",
    "카카오뱅크", "카카오페이", "네이버파이낸셜", "토스",
    "크래프톤", "엔씨소프트", "넷마블", "펄어비스",
    "현대건설", "대우건설", "GS건설", "삼성물산",
    "CJ", "아모레퍼시픽", "LG생활건강",
    # Semiconductor / Tech
    "반도체", "메모리", "DRAM", "NAND", "파운드리", "HBM", "GPU", "NPU",
    "시스템반도체", "웨이퍼", "EUV", "패키징", "TSV",
    "AI", "인공지능", "딥러닝", "머신러닝", "LLM", "생성형AI",
    "클라우드", "데이터센터", "서버", "5G", "6G",
    "엔비디아", "NVIDIA", "AMD", "인텔", "TSMC", "퀄컴",
    # Battery / EV
    "배터리", "이차전지", "전기차", "리튬", "양극재", "음극재",
    "전해질", "분리막", "전고체", "NCM", "LFP",
    "충전", "충전소", "수소차", "수소연료전지",
    "테슬라", "BYD", "CATL",
    # Bio / Pharma
    "바이오", "신약", "임상", "FDA", "바이오시밀러", "항체",
    "세포치료", "유전자치료", "mRNA", "백신", "제약",
    "CMO", "CDMO", "CRO", "위탁생산",
    # Platform / Internet
    "플랫폼", "메타버스", "핀테크", "디지털전환", "SaaS",
    "이커머스", "온라인쇼핑", "구독", "콘텐츠",
    "애플", "구글", "아마존", "마이크로소프트", "메타",
    # Automotive
    "자동차", "EV", "자율주행", "모빌리티", "UAM",
    "전기차판매", "하이브리드", "내연기관",
    # Economic indicators
    "GDP", "금리", "환율", "물가", "고용", "수출", "수입",
    "경상수지", "무역수지", "실업률", "소비자물가", "CPI", "PPI",
    "기준금리", "국채", "채권", "외환", "원달러", "원엔",
    "인플레이션", "디플레이션", "스태그플레이션",
    "통화정책", "재정정책", "양적완화", "긴축",
    "한국은행", "금통위", "연준", "ECB", "BOJ",
    # Market terms
    "주가", "코스피", "코스닥", "시가총액", "매출", "영업이익",
    "순이익", "실적", "어닝", "컨센서스", "가이던스",
    "수주", "공급", "수요", "시장점유율",
    "상장", "IPO", "공모", "배당", "자사주", "분할",
    "유상증자", "무상증자", "감자", "상장폐지",
    "M&A", "인수", "합병", "제휴", "투자", "펀드",
    "상승", "하락", "급등", "급락", "강세", "약세",
    "저점", "고점", "돌파", "지지", "저항", "횡보",
    "거래량", "시초가", "종가", "고가", "저가",
    "외국인", "기관", "개인", "공매도", "대차잔고",
    "ETF", "ETN", "선물", "옵션", "파생",
    # Industry / Sector terms
    "조선", "해운", "철강", "화학", "정유", "건설",
    "방산", "방위산업", "국방", "로봇", "드론",
    "원자력", "원전", "태양광", "풍력", "신재생에너지",
    "게임", "엔터", "미디어", "관광", "호텔", "항공",
    "보험", "증권", "은행", "카드", "리스",
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
        top_n: int = 10,
        keybert_threshold: float = 0.5,
        use_financial_filter: bool = True,
    ):
        """
        Initialize keyword extractor.

        Args:
            method: Extraction method ("konlpy", "keybert", "combined")
            min_keyword_length: Minimum keyword length
            top_n: Number of keywords to extract
            keybert_threshold: Minimum KeyBERT score for combined method
            use_financial_filter: Apply financial domain filter
        """
        self.method = method
        self.min_keyword_length = min_keyword_length
        self.top_n = top_n
        self.keybert_threshold = keybert_threshold
        self.use_financial_filter = use_financial_filter

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

    def is_financial_keyword(self, keyword: str) -> bool:
        """
        Check if keyword is relevant to the financial domain.

        Args:
            keyword: Keyword to check

        Returns:
            True if financially relevant
        """
        # Direct match
        if keyword in FINANCIAL_DOMAIN_TERMS:
            return True
        # Check if keyword contains a financial term (or vice versa)
        keyword_lower = keyword.lower()
        for term in FINANCIAL_DOMAIN_TERMS:
            term_lower = term.lower()
            if len(term_lower) >= 2 and len(keyword_lower) >= 2:
                if term_lower in keyword_lower or keyword_lower in term_lower:
                    return True
        return False

    def _apply_financial_filter(self, keywords: List[str]) -> List[str]:
        """
        Filter keywords to only include financially relevant ones.

        Passes keywords that are either:
        - In the financial domain terms
        - Compound nouns of 4+ chars (potentially novel terms)
        """
        if not self.use_financial_filter:
            return keywords

        filtered = []
        for kw in keywords:
            if self.is_financial_keyword(kw):
                filtered.append(kw)
            elif len(kw) >= 4 and kw not in KOREAN_STOP_WORDS:
                # Allow longer compound nouns that might be novel financial terms
                filtered.append(kw)
        return filtered

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
                keywords = self.extract_nouns(text)
            elif self.method == "keybert":
                keywords = [kw for kw, score in self.extract_keybert(text)]
            else:  # combined
                keywords = self.extract_combined(text)
        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")
            # Fallback to simple extraction
            keywords = self._simple_extract(text)

        # Apply financial domain filter
        return self._apply_financial_filter(keywords)

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

        Uses intersection of KoNLPy and KeyBERT for high precision.
        Falls back to KoNLPy-first union if intersection is too small.

        Args:
            text: Text to analyze

        Returns:
            List of keywords
        """
        nouns: Set[str] = set()
        keybert_keywords: Set[str] = set()

        # Try KoNLPy first
        try:
            noun_list = self.extract_nouns(text)
            nouns = set(noun_list[:self.top_n])
        except Exception as e:
            logger.debug(f"KoNLPy extraction skipped: {e}")

        # Try KeyBERT
        try:
            keybert_results = self.extract_keybert(text)
            keybert_keywords = {
                kw for kw, score in keybert_results
                if score > self.keybert_threshold
            }
        except Exception as e:
            logger.debug(f"KeyBERT extraction skipped: {e}")

        # If both methods failed, use simple extraction
        if not nouns and not keybert_keywords:
            return self._simple_extract(text)

        # Prefer intersection (high precision)
        intersection = nouns & keybert_keywords
        if len(intersection) >= 3:
            return list(intersection)[:self.top_n]

        # Fall back to KoNLPy-first union if intersection is too small
        combined = list(nouns)
        for kw in keybert_keywords:
            if kw not in nouns:
                combined.append(kw)

        return combined[:self.top_n]

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
