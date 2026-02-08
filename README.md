# Victor Trading System

뉴스 기반 자동 주식 트레이딩 시스템입니다. 매일 뉴스를 수집하고 분석하여 한국투자증권 API를 통해 자동으로 매매를 실행합니다.

## 주요 기능

- **뉴스 수집**: 뉴닉, 어피티, 매일경제, 한국경제, 이데일리, 연합뉴스에서 뉴스 자동 수집
- **동적 키워드 추적**: 이슈가 되는 키워드를 자동으로 발견하고 추적
- **트렌드 감지**: 급상승 키워드 및 신규 이슈 실시간 탐지
- **키워드 추출**: KoNLPy, KeyBERT를 활용한 핵심 키워드 분석
- **감성 분석**: KR-FinBert 모델 기반 뉴스 감성 분석
- **동적 종목 매핑**: 트렌딩 키워드 → 관련 종목 자동 연결
- **자동 매매**: 한국투자증권 API 연동 자동 매수/매도
- **리스크 관리**: 손절/익절, 분할 매매, 일일 손실 한도
- **알림**: Slack을 통한 실시간 거래 알림, 계좌 현황 및 일일 리포트

## 시스템 요구사항

- Python 3.10+
- 한국투자증권 계좌 및 API 키
- Slack Webhook URL (알림용)

## 설치

### 1. 저장소 클론

```bash
git clone <repository-url>
cd victor
```

### 2. 가상환경 생성 및 활성화

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. KoNLPy 설치 (한국어 형태소 분석)

```bash
# Mac
brew install java
# Ubuntu
sudo apt-get install default-jdk

pip install konlpy
```

## 설정

### 1. 환경 변수 설정

`.env.example`을 복사하여 `.env` 파일을 생성하고 값을 입력합니다.

```bash
cp .env.example .env
```

**.env 파일 내용:**

```env
# 한국투자증권 API
KIS_APP_KEY=your_app_key_here
KIS_APP_SECRET=your_app_secret_here
KIS_ACCOUNT_NUMBER=your_account_number  # 예: 12345678-01
KIS_HTS_ID=your_hts_id
KIS_VIRTUAL=false                       # 환경변수로 모의투자 설정 가능

# Slack Webhook
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz

# 앱 설정
LOG_LEVEL=INFO
ENV=development
```

### 2. 설정 파일 생성

`config/config.example.yaml`을 복사하여 `config/config.yaml`을 생성합니다.

```bash
cp config/config.example.yaml config/config.yaml
```

### 3. 주요 설정값 설명

**config/config.yaml:**

```yaml
# 앱 설정
app:
  name: "victor-trading"
  env: "development"    # development 또는 production
  log_level: "INFO"     # DEBUG, INFO, WARNING, ERROR

# 한국투자증권 API (환경변수 참조)
kis:
  app_key: ${KIS_APP_KEY}
  app_secret: ${KIS_APP_SECRET}
  account_number: ${KIS_ACCOUNT_NUMBER}
  hts_id: ${KIS_HTS_ID}
  virtual: true         # true: 모의투자, false: 실거래

# 뉴스 소스 설정
news:
  sources:
    - name: "newneek"
      enabled: true
      fetch_limit: 10    # 수집할 기사 수
    - name: "uppity"
      enabled: true
      fetch_limit: 10
    - name: "maekyung"
      enabled: true
      fetch_limit: 20
    - name: "hankyung"    # 한국경제
      enabled: true
      fetch_limit: 20
    - name: "edaily"      # 이데일리
      enabled: true
      fetch_limit: 15
    - name: "yonhap"      # 연합뉴스
      enabled: true
      fetch_limit: 15
  cache:
    enabled: true
    ttl_hours: 24
    directory: "./data/news_cache"

# 분석 설정
analysis:
  keyword_extraction:
    method: "combined"           # konlpy, keybert, combined
    min_keyword_length: 2
    top_n: 15
  sentiment:
    model: "snunlp/KR-FinBert-SC"
    threshold:
      positive: 0.3
      negative: -0.2

# 트레이딩 전략
trading:
  strategy:
    # 포지션 사이징
    max_single_trade_ratio: 0.1  # 1회 거래 최대 비율 (10%)
    split_count: 3               # 분할 매매 횟수

    # 리스크 관리
    stop_loss_rate: -0.05        # 손절 기준 (-5%)
    take_profit_rate: 0.10       # 익절 기준 (+10%)
    max_holding_ratio: 0.2       # 종목당 최대 보유 비율 (20%)
    daily_loss_limit: -0.03      # 일일 최대 손실 (-3%)
    max_trades_per_day: 10       # 일일 최대 거래 횟수

    # 시그널 임계값
    buy_threshold: 0.3           # 매수 감성 임계값
    sell_threshold: -0.2         # 매도 감성 임계값
    min_mentions: 3              # 최소 언급 횟수

# Slack 알림 (환경변수 참조)
slack:
  webhook_url: ${SLACK_WEBHOOK_URL}
  enabled: true

# 스케줄러 (평일만 실행)
scheduler:
  timezone: "Asia/Seoul"
  jobs:
    morning_analysis: "08:30"         # 아침 분석
    intraday_analysis: "10:00,13:00"  # 장중 분석
    daily_report: "16:00"             # 일일 리포트
    risk_reset: "08:00"               # 리스크 한도 리셋

# 데이터 경로
data:
  news_cache: "./data/news_cache"
  trade_history: "./data/trade_history"
  logs: "./data/logs"
```

### 4. 종목-키워드 매핑 (선택사항)

> **참고**: 키워드를 미리 정의하지 않아도 됩니다. 시스템이 뉴스를 분석하면서 이슈가 되는 키워드를 **자동으로 발견**하고 관련 종목을 매핑합니다.

`config/keywords_mapping.yaml`에서 기본 종목 매핑을 설정할 수 있습니다. 이 설정은 선택사항이며, 동적 학습과 함께 사용됩니다.

```yaml
# 종목별 기본 키워드 (동적 학습으로 자동 확장됨)
stocks:
  - stock_code: "005930"
    stock_name: "Samsung Electronics"
    industry: "semiconductor"
    keywords:
      - "Samsung"
      - "semiconductor"
    weight: 1.0
```

**동적 키워드 학습:**
- 뉴스에서 자주 언급되는 키워드 자동 추출
- 키워드와 종목 간 연관관계 자동 학습
- 학습된 매핑은 `data/stock_cache/`에 저장

## 실행

`run.sh` 스크립트를 사용하여 실행합니다. (Python 캐시 자동 정리)

### 기본 실행 (데몬 모드)

스케줄러가 설정된 시간에 자동으로 분석 및 매매를 실행합니다.

```bash
./run.sh --mode daemon
```

### 1회 실행 (테스트)

뉴스 수집 → 분석 → 매매를 1회 실행합니다.

```bash
./run.sh --mode once
```

### 캐시 무시하고 실행

이미 분석한 뉴스도 다시 분석합니다.

```bash
./run.sh --mode once --no-cache
```

### 상태 확인

시스템 설정 및 계좌 상태를 확인합니다.

```bash
./run.sh --mode status
```

### 실거래 모드

**주의: 실제 돈이 사용됩니다!**

```bash
./run.sh --mode daemon --live
```

### 뉴스 수집만 테스트

KIS API 호출 없이 뉴스 수집만 테스트합니다.

```bash
./run.sh --mode once --no-cache --skip-kis
```

### 로그 레벨 설정

```bash
./run.sh --mode daemon --log-level DEBUG
```

## 실행 모드

| 모드 | 설명 |
|------|------|
| `daemon` | 스케줄러 기반 자동 실행 (기본) |
| `once` | 1회 분석 사이클 실행 |
| `status` | 시스템 상태 확인 |

| 옵션 | 설명 |
|------|------|
| `--live` | 실거래 모드 활성화 |
| `--log-level` | 로그 레벨 (DEBUG/INFO/WARNING/ERROR) |
| `--no-cache` | 뉴스 캐시 무시 (모든 기사 다시 분석) |
| `--skip-kis` | KIS API 호출 건너뛰기 (뉴스 수집 테스트용) |

## Slack 알림

모든 리포트 마지막에 계좌 현황이 포함됩니다:

- **분석 사이클 결과**: 수집된 기사 수, 생성된 시그널, 거래 결과 + 계좌 현황
- **일일 리포트**: 키워드 분석, 감성 분석, 거래 통계 + 계좌 현황
- **거래 알림**: 매수/매도 실행 결과
- **오류 알림**: 시스템 오류 발생 시

### 계좌 현황 포함 정보

- 예수금 (현금)
- 주식 평가금액
- 총 평가금액
- 총 손익금액 및 수익률
- 보유 종목 목록 (종목명, 수량, 수익률)

## 스케줄 (평일)

| 시간 | 작업 | 설명 |
|------|------|------|
| 08:00 | 리스크 리셋 | 일일 거래 한도 초기화 |
| 08:30 | 아침 분석 | 장 시작 전 뉴스 분석 및 매매 |
| 10:00 | 장중 분석 | 추가 뉴스 분석 및 매매 |
| 13:00 | 장중 분석 | 추가 뉴스 분석 및 매매 |
| 16:00 | 일일 리포트 | Slack으로 일일 결과 전송 |

## 동적 트렌드 추적 시스템

키워드를 미리 정의하지 않아도 시스템이 자동으로 이슈를 발견합니다.

### 동작 방식

```
뉴스 수집 (다양한 소스)
       ↓
키워드 자동 추출 (KoNLPy, KeyBERT)
       ↓
┌─────────────────────────────────┐
│     트렌드 트래커               │
│  - 키워드 빈도 추적             │
│  - 급상승 키워드 감지 (트렌딩)   │
│  - 신규 이슈 발견 (이머징)       │
└─────────────────────────────────┘
       ↓
┌─────────────────────────────────┐
│     동적 종목 매퍼              │
│  - 트렌딩 키워드 → 종목 매핑     │
│  - 새로운 연관관계 자동 학습     │
└─────────────────────────────────┘
       ↓
매매 시그널 생성
```

### 예시 출력

```
[INFO] Collecting news from all sources...
[INFO] Collected 45 new articles
[INFO] Analyzing 45 articles...
[INFO] Trending keywords: AI반도체, HBM, 전기차, FOMC, 실적발표
[INFO] Emerging issues: 트럼프관세, 금리인하, 신규상장
[INFO] Generated 12 trading signals
```

### 데이터 저장 위치

- `data/trends/` - 키워드 트렌드 데이터 (일별)
- `data/stock_cache/` - 학습된 키워드-종목 연관관계

## 프로젝트 구조

```
victor/
├── run.sh                  # 실행 스크립트 (권장)
├── main.py                 # 메인 실행 파일
├── config/
│   ├── config.yaml         # 설정 파일
│   ├── keywords_mapping.yaml  # 기본 종목 매핑 (선택)
│   └── settings.py         # 설정 로더
├── src/
│   ├── news/               # 뉴스 수집 모듈
│   │   ├── aggregator.py   # 뉴스 통합 수집
│   │   ├── newneek.py      # 뉴닉 크롤러
│   │   ├── uppity.py       # 어피티 크롤러
│   │   ├── maekyung.py     # 매일경제 크롤러
│   │   ├── hankyung.py     # 한국경제 크롤러
│   │   ├── edaily.py       # 이데일리 크롤러
│   │   └── yonhap.py       # 연합뉴스 크롤러
│   ├── analysis/           # 분석 모듈
│   │   ├── analyzer.py     # 통합 분석기
│   │   ├── trend_tracker.py    # 동적 트렌드 추적
│   │   ├── dynamic_mapper.py   # 동적 종목 매핑
│   │   ├── keyword_extractor.py  # 키워드 추출
│   │   ├── sentiment.py    # 감성 분석
│   │   └── stock_mapper.py # 정적 종목 매핑
│   ├── trading/            # 트레이딩 모듈
│   │   ├── kis_client.py   # 한국투자증권 API
│   │   ├── strategy.py     # 트레이딩 전략
│   │   ├── risk_manager.py # 리스크 관리
│   │   └── order.py        # 주문 실행
│   ├── notification/       # 알림 모듈
│   │   └── slack.py        # Slack 알림
│   ├── scheduler/          # 스케줄러 모듈
│   │   └── scheduler.py    # 작업 스케줄러
│   └── utils/              # 유틸리티
│       ├── logger.py       # 로깅
│       └── exceptions.py   # 예외 정의
├── data/
│   ├── news_cache/         # 뉴스 캐시
│   ├── trends/             # 트렌드 데이터
│   ├── stock_cache/        # 학습된 종목 매핑
│   ├── trade_history/      # 거래 기록
│   └── logs/               # 로그 파일
└── tests/                  # 테스트
```

## 안전 장치

1. **기본 모의투자**: `--live` 옵션 없이는 실거래 불가
2. **분할 매매**: 한 번에 전량 매매하지 않음
3. **손절/익절**: 자동 손절(-5%) 및 익절(+10%)
4. **포지션 제한**: 종목당 최대 20%
5. **일일 손실 한도**: -3% 도달 시 거래 중단
6. **일일 거래 횟수 제한**: 최대 10회

## 주의사항

- 이 시스템은 투자 참고용이며, 투자 결정은 본인 책임입니다
- 실거래 전 반드시 모의투자로 충분히 테스트하세요
- API 키와 비밀번호는 절대 공개하지 마세요
- 시장 상황에 따라 예상과 다른 결과가 발생할 수 있습니다

## 라이선스

MIT License
