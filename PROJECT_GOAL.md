# 프로젝트 목표: I2g (Image to Game Animation)

## 개요

**한 장의 스프라이트시트 PNG → 자동 분할 → 기준점(발/피벗) 자동 정렬 → 게임 제작에 바로 쓰기 좋은 애니메이션 산출물** 생성을 자동화하는 MCP 서버

### 산출물 형식
- `anim.aseprite` - 게임 파이프라인 원본
- `anim_sheet.png` + `anim_sheet.json` - 게임 엔진용 (Unity/Godot 호환)
- `anim_preview.gif` - 미리보기/커뮤니케이션용

---

## 사용자 플로우

1. 사용자가 `inbox/` 폴더에 **PNG 1장** 넣음
2. 사용자가 AI에게: **"방금 넣은 이미지로 게임용 애니메이션 만들어줘"** 요청
3. AI가 MCP 툴 호출 → `inbox/` 스캔 또는 감시 모드 활성화
4. MCP 서버가 **Aseprite CLI + Lua 스크립트** 실행으로 자동 처리
5. `out/<작업명>/`에 산출물 생성

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│  AI/Codex                                                   │
│  ↓ MCP 툴 호출                                              │
├─────────────────────────────────────────────────────────────┤
│  MCP 서버 (FastMCP + Python)                                │
│  ├─ watch_start/stop     ← 폴더 감시                        │
│  ├─ convert_inbox        ← 배치 처리                        │
│  ├─ convert_file         ← 단일 파일 처리                   │
│  └─ status               ← 상태 조회                        │
├─────────────────────────────────────────────────────────────┤
│  작업 큐 (동시성 1)                                         │
│  ↓                                                          │
│  Aseprite CLI + Lua 스크립트                                │
│  ├─ 프레임 분할 (그리드 기반 Import)                        │
│  ├─ 배경 투명화 (색상 매칭 기반, 향후 flood-fill 가능)       │
│  ├─ 기준점 정렬 (foot anchor)                               │
│  ├─ 타이밍 설정 (FPS + 루프 모드)                           │
│  └─ 내보내기 (.aseprite + PNG+JSON + GIF)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## MCP 툴 스펙

| 툴 이름 | 설명 | 반환 |
|---------|------|------|
| `watch_start` | 폴더 감시 시작 | `WatchStatus` |
| `watch_stop` | 감시 종료 | `Result` |
| `convert_inbox` | inbox 파일 일괄 처리 | `BatchReport` |
| `convert_file` | 단일 파일 처리 | `ConvertReport` |
| `status` | 서버 상태 조회 | `ServerStatus` |
| `dry_run_detect` | 그리드 자동 감지 미리보기 | `DetectionReport` |

---

## JobSpec (설정 오버라이드)

기본은 자동 감지이며, 입력 파일 옆에 `<입력파일 스템>.job.json`을 두면 설정을 오버라이드할 수 있습니다. (예: `walk.png` → `walk.job.json`)

- **지원 키:** `grid`, `timing`, `anchor`, `background`, `export`, `auto_detect_grid`
- **우선순위:** MCP 툴 인자(`grid_rows`, `grid_cols`, `fps`) > `.job.json` > 프로필 기본값

```json
{
  "grid": { "rows": 3, "cols": 4 },
  "timing": { "fps": 12, "loop_mode": "loop" },
  "anchor": { "mode": "foot", "alpha_thresh": 10 },
  "background": { "mode": "transparent" },
  "auto_detect_grid": true,
  "export": {
    "aseprite": true,
    "sheet_png_json": true,
    "gif_preview": true
  }
}
```

---

## 변환 품질 핵심 로직

### 1. 프레임 분할
- JobSpec에 rows/cols가 있으면 그대로 사용
- 없으면 Python detector가 배경 분석으로 그리드 자동 추정

### 2. 배경 투명화
- **현재 구현:** 배경색(`bg_color`)과 허용 오차(`bg_tolerance`)로 매칭되는 픽셀을 투명 처리(단순 색상 치환)
- **향후 개선:** edge flood-fill 방식으로 연결된 배경만 제거하여 내부 디테일 보존을 강화

### 3. 기준점 정렬 (지터 제거)
- `foot` 모드: 하단 불투명 픽셀 기준선 감지
- `anchor_x`: baseline 근처 픽셀들의 median
- 모든 프레임을 타깃 앵커로 이동 → 캔버스 확장으로 잘림 방지

### 4. 게임 엔진 Export
- `ExportSpriteSheet` API로 PNG+JSON 생성
- padding, trim, dataFormat 옵션 지원

---

## 수용 기준

| 항목 | 기준 |
|------|------|
| 12프레임(4x3) 입력 시 산출물 생성 | sheet.png, sheet.json, .aseprite, preview.gif |
| 앵커 지터 | `anchor_jitter_rms_px <= 1.0` |
| 프레임 duration | 모두 동일 |
| 실패 처리 | `failed/`로 이동 + error.txt 생성 |
| E2E 플로우 | inbox에 넣고 `convert_inbox` 1회 호출로 완료 |

---

## 기술 스택

- **런타임**: Python 3.10+
- **MCP 프레임워크**: FastMCP (python-sdk)
- **폴더 감시**: watchfiles (기본), polling (fallback)
- **스키마**: Pydantic
- **이미지 분석**: Pillow (그리드 감지)
- **변환 엔진**: Aseprite CLI + Lua
- **후처리**: FFmpeg, gifsicle (선택)

---

## 환경 변수

| 변수명 | 설명 | 필수 |
|--------|------|------|
| `ASEPRITE_EXE` | Aseprite 실행 파일 경로 | ✓ |
| `SS_ANIM_WORKSPACE` | 워크스페이스 루트 경로 | × (기본: `./workspace`) |

---

## 레퍼런스

- [Aseprite CLI 문서](https://www.aseprite.org/docs/cli/)
- [Aseprite ImportSpriteSheet API](https://www.aseprite.org/api/command/ImportSpriteSheet)
- [Aseprite ExportSpriteSheet API](https://www.aseprite.org/api/command/ExportSpriteSheet)
- [FastMCP (Python SDK)](https://github.com/modelcontextprotocol/python-sdk)
- [참고 레포: diivi/aseprite-mcp](https://github.com/diivi/aseprite-mcp)
