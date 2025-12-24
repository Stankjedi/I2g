# 🚀 프로젝트 개선 탐색 보고서

> 이 문서는 Vibe Coding Report VS Code 확장에서 자동으로 관리됩니다.  
> **적용된 개선 항목은 자동으로 필터링되어 미적용 항목만 표시됩니다.**
>
> 💡 **구체적인 구현 코드는 `Prompt.md` 파일을 참조하세요.**

---

## 📋 프로젝트 정보

| 항목 | 값 |
|------|-----|
| **프로젝트명** | I2g |
| **최초 분석일** | 2025-12-23 12:40 |

---

<!-- AUTO-ERROR-EXPLORATION-START -->
## 🔍 오류 및 리스크 탐색 절차

> 이 섹션은 개선 항목이 어떤 기준으로 도출되었는지를 설명합니다.

### 1. 데이터 수집
- 최근 빌드/테스트/런타임 로그 분석
- VS Code 문제 패널(Problems) 확인
- Git diff 및 커밋 메시지 검토
- TODO/FIXME 주석 스캔

### 2. 자동 분석
- 테스트 실패/스킵 케이스 분류
- 빌드 오류/경고 메시지 그룹화
- 빈번하게 수정되는 파일/모듈 탐지
- 정적 분석(lint, type-check) 결과 검토

### 3. 개선 후보 도출
- 동일 원인의 오류/경고를 하나의 "개선 항목 후보"로 묶기
- 영향도(테스트 실패, 빌드 실패, 성능 저하)에 따라 우선순위 부여
- 프로젝트 비전과의 일치 여부 검토

### 4. 최종 백로그 정제
- 복잡도/리스크 대비 효용 검토
- Definition of Done 명시
- 관련 평가 점수 카테고리 매핑
<!-- AUTO-ERROR-EXPLORATION-END -->

---

## 📌 사용 방법

1. 이 보고서의 개선 항목을 검토합니다
2. 적용하고 싶은 항목을 선택하여 `Prompt.md`를 생성합니다
3. AI 에이전트(Copilot Chat 등)에 붙여넣어 구현을 요청합니다
4. 다음 보고서 업데이트 시 적용된 항목은 자동으로 제외됩니다

---

<!-- AUTO-SUMMARY-START -->
## 📊 개선 현황 요약

- 본 보고서는 **아직 적용되지 않은(대기 중인)** 개선 항목만 포함합니다(완료 이력/세션 로그는 `Session_History.md`에서 관리).

| 우선순위 | 대기 개수 |
|:---:|:---:|
| 🔴 P1 | 1 |
| 🟡 P2 | 2 |
| 🟢 P3 | 1 |
| 🚀 OPT | 1 |

| # | 항목명 | 우선순위 | 카테고리 |
|:---:|:---|:---:|:---|
| 1 | 경로 인자 워크스페이스 경계 검증 일원화 | P1 | 🔒 보안 / 📦 프로덕션 |
| 2 | 라인엔딩/포맷 표준화 및 저장소 규칙 도입 | P2 | 🧹 코드 품질 |
| 3 | Lua 실패 메타/에러 표준화(조기 종료 포함) | P2 | 🧭 관측성 / 🧹 코드 품질 |
| 4 | offset/pad(마진/패딩) 포함 그리드 자동 감지 고도화 | P3 | ✨ 기능 추가 |
| 5 | watcher 내부 상태(처리 목록/폴링 캐시) 누적 방지 최적화 | OPT | 🚀 성능 / 🧹 품질 |

- **P1:** 워크스페이스 경계 기반의 경로 정책을 완성해 보안/운영 사고 가능성을 최소화
- **P2:** 협업/자동화 품질(포맷)과 실패 진단성(메타/에러 표준)을 강화
- **P3:** 다양한 스프라이트시트 입력(마진/패딩 포함)에 대한 자동 감지 정확도를 높여 사용성을 개선
- **OPT:** 장시간 실행(감시 모드)에서 메모리/상태 누적을 줄여 안정성을 개선
<!-- AUTO-SUMMARY-END -->

---

<!-- AUTO-IMPROVEMENT-LIST-START -->
## 📝 개선 항목 목록

### 🔴 중요 (P1)

#### [P1-1] 경로 인자 워크스페이스 경계 검증 일원화

| 항목 | 내용 |
|------|------|
| **ID** | `sec-path-policy-001` |
| **카테고리** | 🔒 보안 / 📦 배포 |
| **복잡도** | Medium |
| **대상 파일** | `src/ss_anim_mcp/server.py`, `src/ss_anim_mcp/config.py`, `src/ss_anim_mcp/models.py`, `tests/test_directory_overrides.py` |
| **Origin** | static-analysis |
| **리스크 레벨** | critical |
| **관련 평가 카테고리** | security, productionReadiness, maintainability |

- **현재 상태:** `_resolve_override_dir()`는 `processed_dir/failed_dir`에만 적용되며, `watch_start`의 `inbox_dir/out_dir`, `convert_file`의 `input_path/out_dir` 등은 경로 정규화/경계 검증 없이 사용됩니다.
- **문제점 (Problem):** 워크스페이스 외부 경로 접근/쓰기 가능성이 남아 있고, 툴별 정책이 달라 예측 가능성이 떨어집니다.
- **영향 (Impact):** 보안 경계 붕괴(의도치 않은 파일 접근/유출), 운영 사고(잘못된 위치로 산출물 생성), 테스트/문서의 정책 불일치.
- **원인 (Cause):** “경로 인자 처리(정규화·허용 범위·옵트인)”가 툴 전반에 공통화되어 있지 않습니다.
- **개선 내용 (Proposed Solution):** (1) 공통 경로 해석/검증 헬퍼 도입(상대 경로는 `workspace_root` 기준, `expanduser/resolve`) (2) 모든 경로 인자에 동일 정책 적용(`inbox_dir/out_dir/input_path/...`) (3) 필요한 툴에 `allow_external_paths` 확장 및 기본은 안전(워크스페이스 내부만 허용) (4) 경로 관련 테스트 추가.
- **기대 효과:** 경로 정책 일관화로 보안/운영 리스크 감소, 사용자/에이전트의 예측 가능성 향상.

**Definition of Done**
- [ ] 주요 코드 리팩토링 및 구현 완료
- [ ] 관련 테스트 추가/수정 및 통과
- [ ] 빌드 및 린트 에러 없음
- [ ] 문서 또는 주석 보완 (필요시)

### 🟡 중요 (P2)

#### [P2-1] 라인엔딩/포맷 표준화 및 저장소 규칙 도입

| 항목 | 내용 |
|------|------|
| **ID** | `maint-line-endings-001` |
| **카테고리** | 🧹 코드 품질 |
| **복잡도** | Low |
| **대상 파일** | `src/ss_anim_mcp/watcher.py`, `aseprite_scripts/convert_sheet_to_anim.lua`, (선택) `.vscode/mcp.json` |
| **Origin** | static-analysis |
| **리스크 레벨** | medium |
| **관련 평가 카테고리** | codeQuality, maintainability, productionReadiness |

- **현재 상태:** 일부 파일에서 CRLF/이상 제어문자 혼재가 관찰되어(diff 노이즈, 리뷰/머지 비용 증가) 유지보수 품질을 저하시킵니다.
- **문제점 (Problem):** 동일 변경이 과도한 diff로 나타나고, 도구/OS(Windows/WSL/CI) 간 포맷 차이로 충돌이 발생할 수 있습니다.
- **영향 (Impact):** 코드 리뷰 지연, 자동화(포매터/린터) 적용 난이도 증가, 릴리스 안정성 저하.
- **원인 (Cause):** 저장소 차원의 라인엔딩/텍스트 파일 규칙(.gitattributes 등)이 부재하거나 일관되게 적용되지 않습니다.
- **개선 내용 (Proposed Solution):** (1) `.gitattributes`로 텍스트 파일 eol=lf 강제 (2) 문제 파일의 라인엔딩을 LF로 정규화 (3) CI에서 CRLF 혼입 방지 체크(간단 스크립트) 추가(선택).
- **기대 효과:** diff 노이즈 감소, 협업/자동화 품질 향상, 장기 유지보수 비용 절감.

**Definition of Done**
- [ ] 주요 코드 리팩토링 및 구현 완료
- [ ] 관련 테스트 추가/수정 및 통과
- [ ] 빌드 및 린트 에러 없음
- [ ] 문서 또는 주석 보완 (필요시)

#### [P2-2] Lua 실패 메타/에러 표준화(조기 종료 포함)

| 항목 | 내용 |
|------|------|
| **ID** | `obs-lua-error-meta-001` |
| **카테고리** | 🧭 관측성 / 🧹 코드 품질 |
| **복잡도** | Medium |
| **대상 파일** | `aseprite_scripts/convert_sheet_to_anim.lua`, `src/ss_anim_mcp/aseprite_runner.py`, `tests/test_output_validation.py` |
| **Origin** | static-analysis |
| **리스크 레벨** | medium |
| **관련 평가 카테고리** | errorHandling, productionReadiness, maintainability |

- **현재 상태:** Lua 스크립트는 입력/출력 오류에서 조기 `return`하며, 이 경우 `meta.json`이 생성되지 않을 수 있습니다. Python은 산출물 계약 검증으로 실패를 잡지만, 실패 원인이 “누락 파일” 중심으로 요약됩니다(상세는 stdout/stderr에만 존재).
- **문제점 (Problem):** 자동화(에이전트/CI)에서 실패 원인 파악이 어렵고, 동일 실패의 분류/대응이 일관되지 않습니다.
- **영향 (Impact):** 디버깅 지연, 실패 재시도 비용 증가, 사용자 경험 저하.
- **원인 (Cause):** Lua→Python 사이의 “실패 메타 계약”(status/error_code/error_message)이 정의·활용되지 않습니다.
- **개선 내용 (Proposed Solution):** (1) Lua에서 어떤 실패 경로든 `meta.json`에 `status=failed`와 에러 정보를 기록 (2) Python에서 `meta.json`의 실패를 우선적으로 해석해 `error_code`/`error_message`를 구조화 (3) 단위 테스트로 메타 파싱/에러 메시지 표준 검증.
- **기대 효과:** 실패 원인 가시성 향상, 에러 분류 표준화, 운영/자동화 신뢰성 강화.

**Definition of Done**
- [ ] 주요 코드 리팩토링 및 구현 완료
- [ ] 관련 테스트 추가/수정 및 통과
- [ ] 빌드 및 린트 에러 없음
- [ ] 문서 또는 주석 보완 (필요시)
<!-- AUTO-IMPROVEMENT-LIST-END -->

---

<!-- AUTO-FEATURE-LIST-START -->
## ✨ 기능 추가 항목

> 새로운 사용자 가치(정확도/자동화 범위)를 제공하는 P3 기능 백로그입니다.

### 🟢 개선 (P3)

#### [P3-1] offset/pad(마진/패딩) 포함 그리드 자동 감지 고도화

| 항목 | 내용 |
|------|------|
| **ID** | `feat-grid-offset-pad-detect-001` |
| **카테고리** | ✨ 기능 추가 |
| **복잡도** | High |
| **대상 파일** | `src/ss_anim_mcp/detector.py`, `src/ss_anim_mcp/aseprite_runner.py`, `tests/` |
| **Origin** | static-analysis |
| **리스크 레벨** | medium |
| **관련 평가 카테고리** | scalability, productionReadiness, performance |

- **현재 상태:** 자동 감지는 rows/cols 중심이며 `offset_x/offset_y/pad_x/pad_y`는 항상 0으로 반환됩니다. 마진/패딩이 있는 스프라이트시트는 `.job.json` 수동 오버라이드가 필요합니다.
- **기능 목적/가치:** (1) 수동 설정 최소화 (2) 다양한 입력(마진/패딩/테두리)에서 변환 성공률 향상 (3) 에이전트 자동화 품질 개선.
- **의존/연동:** `GridConfig`는 offset/pad 필드를 이미 보유하고, Lua 스크립트는 `grid_offset_*`/`grid_pad_*`를 반영합니다. Runner의 auto-detect 경로에서 감지 결과를 그대로 적용하면 됩니다.
- **구현 전략:** (1) 배경색 기반 가장자리 스캔으로 offset 추정 (2) gap 그룹 폭/간격 기반 padding 추정(중앙값/최빈값 등) (3) 감지 신뢰도/notes에 추정 근거 기록 (4) Pillow로 합성 이미지(마진/패딩 포함) 테스트 추가.
- **기대 효과:** 자동 감지 범위 확대, 변환 실패/재시도 감소, 사용자 경험 개선.

**Definition of Done**
- [ ] 주요 코드 리팩토링 및 구현 완료
- [ ] 관련 테스트 추가/수정 및 통과
- [ ] 빌드 및 린트 에러 없음
- [ ] 문서 또는 주석 보완 (필요시)
<!-- AUTO-FEATURE-LIST-END -->

---

<!-- AUTO-OPTIMIZATION-START -->
## 🚀 코드 품질 및 성능 최적화

> 기존 기능을 해치지 않으면서 코드 품질과 성능을 향상시킬 수 있는 개선점입니다.

### 1) 일반 분석(요약)
- 라인엔딩/포맷 혼재는 diff 노이즈를 키워 협업/자동화 품질을 떨어뜨립니다(저장소 규칙 필요).
- watcher 장시간 실행 시 내부 상태(set/dict) 누적이 메모리/성능 리스크로 이어질 수 있습니다(정리 정책 필요).
- 외부 도구(Aseprite/FFmpeg) 실패 시 원인 메타/로그를 더 구조화하면 운영 진단성이 향상됩니다.
- 경로 문자열 조립/정규화 로직은 공통 유틸로 통합해 중복과 정책 불일치를 줄일 여지가 있습니다.
- 입력 규모가 커질수록 스캔/감지 로직의 효율 차이가 커지므로 캐시/단일 패스/부분 선택 전략을 유지해야 합니다.

### 🚀 코드 최적화 (OPT-1)

| 항목 | 내용 |
|------|------|
| **ID** | `opt-watcher-state-prune-001` |
| **카테고리** | 🚀 코드 최적화 / ⚙️ 성능 튜닝 |
| **영향 범위** | 성능 / 품질 |
| **대상 파일** | `src/ss_anim_mcp/watcher.py` |

- **현재 상태:** 감시 과정에서 `_processed_files`(set)와 폴링 보조 상태(`seen_files`)가 파일 수/실행 시간에 따라 누적될 수 있으며, 제거된 파일에 대한 엔트리도 유지될 수 있습니다.
- **최적화 내용:** (1) 폴링 사이클마다 `seen_files`를 현재 파일 집합 기준으로 정리 (2) `_processed_files`도 “현재 inbox에 존재하는 파일” 기준으로 주기적 정리 또는 상한(`max_entries`) 적용 (3) 필요 시 상태 크기/정리 수행 횟수를 디버그 로그로 노출(스팸 방지).
- **예상 효과:** 장시간 실행 시 메모리 사용량 안정화, 폴링 루프 부하 감소, 운영 안정성 향상.
- **측정 지표:** N=10k 파일 처리 시 `_processed_files`/`seen_files` 크기 상한 유지 여부, 폴링 1회당 처리 시간(p50/p95) 및 메모리(대략) 비교.
<!-- AUTO-OPTIMIZATION-END -->
