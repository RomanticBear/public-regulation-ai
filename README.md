# 사규관리규정 AI 벤치마킹 (데모)

공공기관 사규관리규정을 검색·비교하는 PoC입니다.

## 빠른 시작 (약 10분)

### 1. Python 설치

[python.org](https://www.python.org/downloads/) 에서 Python 3.11+ 설치  
설치 시 **"Add Python to PATH"** 체크

### 2. 의존성 설치 및 인덱스 생성

```powershell
cd public-regulation-ai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_index.py
```

### 3. 데모 실행

```powershell
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

## data 폴더

| 파일 | 형식 | 비고 |
|------|------|------|
| 한국수자원공사_사규관리규정.pdf | PDF | ✅ 바로 파싱 가능 |
| 나머지 5개 | HWP | 자동 추출 시도, 실패 시 PDF 변환 |

HWP 파싱이 실패하면 한글(HWP)에서 **PDF로 저장** 후 `data/`에 넣으세요.

## 데모 기능

- **조문 검색**: "입안예고 기간" 등 키워드 검색
- **기관 비교**: 두 기관의 동일 주제 조문 나란히 보기
- **검토 권고**: 타 기관 대비 약한 조문 주제 표시

## 다음 단계

1. HWP → PDF 일괄 변환 (6개 기관 전체)
2. OpenAI/Azure API 연동 (자연어 요약·비교표)
3. 조문 embedding 검색 (유사 조문 매칭)
