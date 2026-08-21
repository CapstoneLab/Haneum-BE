# KeyBack Backend

Android 보안 키보드의 입력 분석 요청을 받아 규칙 분석과 데이터 저장을 수행하고,
Claude 또는 Mac mini 로컬 LLM의 문맥 분석을 결합하는 FastAPI 백엔드입니다.

## 현재 구현 범위

- `POST /api/v1/analyze`
- `POST /api/v1/actions`
- `GET /api/v1/health`
- `GET/DELETE /api/v1/risk-logs`
- `GET/PUT /api/v1/settings/{device_id}`
- PostgreSQL 모델과 Alembic 초기 마이그레이션
- Claude Messages API 구조화 출력 클라이언트
- 선택 가능한 Mac mini 내부 LLM 클라이언트
- LLM 장애 fallback, 위험 점수 통합, 최소 점수 보정
- 원문 미저장과 서버 재마스킹
- API Key 인증, 요청 크기·필드 제한, `request_id` 멱등 처리
- Raspberry Pi용 Docker Compose

## 로컬 실행

```bash
cd backend
cp .env.example .env
# .env의 ANTHROPIC_API_KEY, ANDROID_API_KEY와 PostgreSQL 비밀번호를 변경
docker compose up --build
```

API 문서는 개발 환경에서 `http://localhost:8000/docs`로 확인할 수 있습니다.

## Android 터미널 시뮬레이터

서버 호출 없이 Android 요청과 로컬 마스킹 결과만 확인합니다.

```powershell
python -m scripts.android_simulator --dry-run `
  --context "검찰 수사관입니다" `
  --text "인증번호 123456을 지금 보내주세요"
```

FastAPI, PostgreSQL, Android API Key 없이 로컬 규칙과 Claude 분석 결과를 확인합니다.

```powershell
python -m scripts.android_simulator --standalone `
  --context "검찰 수사관입니다"
```

이 모드는 `.env`의 `ANTHROPIC_API_KEY`만 필요합니다.

실제 FastAPI와 Claude까지 호출하려면 Docker Compose로 서버를 실행한 뒤 `--dry-run`을
제거합니다. `--text`를 생략하면 터미널에서 문장을 대화형으로 입력할 수 있습니다.

```powershell
python -m scripts.android_simulator --context "검찰 수사관입니다"
```

## Claude API 설정

`backend/.env`에 다음 값을 설정합니다.

```dotenv
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=실제_Anthropic_API_Key
ANTHROPIC_MODEL=claude-sonnet-4-6
```

`.env`는 `.gitignore`에 포함되어 있으므로 저장소에 커밋하지 않습니다. Claude에는 서버에서
재마스킹한 현재 입력과 최근 문맥만 전송하며, 최종 위험 판단은 백엔드 Risk Engine이 수행합니다.

## Mac mini 로컬 LLM 선택 사항

로컬 LLM을 사용하려면 `.env`의 `LLM_PROVIDER=local`로 변경합니다.

백엔드는 다음 내부 API를 호출합니다.

- `POST {LLM_BASE_URL}/analyze`
- `GET {LLM_BASE_URL}/health`

요청에는 `X-Internal-API-Key`와 `X-Request-ID`가 포함됩니다. 기본 URL은 `http://host.docker.internal:8001/internal/v1`이며 Raspberry Pi 운영 환경에서는 Mac mini의 내부 IP로 변경해야 합니다.

## 테스트

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
```

## 설계상 보조 필드

`analysis_requests.result_payload`는 동일 `request_id` 재요청 시 LLM을 다시 호출하지 않고 최초 응답을 그대로 반환하기 위한 JSONB 스냅샷입니다. 입력 원문이나 전체 대화는 포함하지 않습니다.
