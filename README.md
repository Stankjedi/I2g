# I2g - AI Image Background Cleaner

AI로 생성된 이미지의 배경을 자동으로 제거하는 GUI 도구입니다.

![Version](https://img.shields.io/badge/version-0.0.3-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

[![Sponsor](https://img.shields.io/badge/💖_Sponsor-Support_Me-ff69b4?style=for-the-badge)](https://ctee.kr/place/stankjedi)

## ✨ 주요 기능

- **윤곽선 기반 배경 제거**: 검은색 윤곽선을 감지하여 외부 배경만 제거
- **실시간 미리보기**: 원본과 결과를 나란히 비교
- **확대/축소 & 이동**: 마우스 스크롤로 확대, 드래그로 이동
- **파라미터 조정**: Threshold, Dilation 값 슬라이더 또는 직접 입력

---

## 🚀 빠른 시작 (EXE 버전)

### 요구사항
- **없음!** Aseprite, Python 설치 없이 바로 실행 가능

### 다운로드 & 실행
1. [Releases](https://github.com/Stankjedi/I2g/releases)에서 `BackgroundCleaner_v0.0.3.exe` 다운로드
2. 다운로드한 exe 파일 더블클릭
3. 바로 사용 가능!

> ✅ 배포용 EXE는 **GitHub Releases**로만 제공합니다. 저장소에는 바이너리(`gui/dist/`)를 커밋하지 않습니다.

---

## 🔧 개발자용 설치 (Python)

### 요구사항
- Python 3.10+
- Pillow

### 설치 방법
```bash
git clone https://github.com/Stankjedi/I2g.git
cd I2g/gui

pip install -r requirements.txt
python main.py
```

---

## 📖 사용 방법

### 1. 이미지 열기
- **📂 Open** 버튼 클릭
- PNG, JPG, BMP 등 이미지 파일 선택

### 2. 파라미터 조정 (선택)
| 파라미터 | 설명 | 기본값 | 권장 범위 |
|---------|------|--------|----------|
| **Threshold** | 윤곽선 감지 밝기 임계값 (낮을수록 더 어두운 것만 윤곽선) | 20 | 10-40 |
| **Dilation** | 가장자리 정리 반복 횟수 | 50 | 30-100 |

#### 프리셋 사용
- **Preset** 드롭다운에서 자주 쓰는 조합을 선택하거나, **Save Preset**으로 저장해 재사용할 수 있습니다.

#### 파라미터 선택 가이드(요약)
- **Threshold(윤곽선 민감도):** 값이 **낮을수록** 더 어두운 픽셀만 “윤곽선”으로 인정합니다.
  - **내부 콘텐츠가 같이 지워짐(과삭제)** → Threshold를 **올리기**(예: 30~40)
  - **배경이 덜 지워짐(잔여물)** → Threshold를 **내리기**(예: 10~20)
- **Dilation(가장자리 정리 강도/횟수):** 값이 **높을수록** 제거 영역 가장자리를 더 적극적으로 정리합니다.
  - **초록빛 잔여물/반투명 테두리** → Dilation을 **올리기**(예: 60~100)
  - **처리가 너무 느림** → Dilation을 **내리기**(예: 10~40) 또는 이미지 해상도 낮춰 시도

### 3. 처리 실행
- **🔄 Process** 버튼 클릭
- 진행률 표시줄에서 진행 상황 확인

### 4. 결과 확인
- **마우스 스크롤**: 확대/축소
- **좌클릭 드래그**: 이미지 이동
- **Reset View**: 원래 크기로 복귀

### 5. 저장
- **💾 Save** 버튼 클릭
- PNG 형식으로 저장 (투명 배경 유지)

---

## 🖼️ 사용 예시

| Before | After |
|--------|-------|
| ![Before](docs/before.png) | ![After](docs/after.png) |

배경의 초록색이 완전히 제거되고 윤곽선 내부 콘텐츠는 그대로 유지됩니다.

---

## ⚠️ 제한 사항

- 이 도구는 **“윤곽선(검은 테두리)”을 기준으로 외곽 배경을 제거**하는 방식입니다. 윤곽선이 약하거나 끊기면 결과가 불안정할 수 있습니다.
- 알고리즘은 **이미지 모서리(코너) 색상**을 배경 기준으로 참고합니다. 모서리 배경 색이 크게 달라지거나 복잡하면 잔여물이 남을 수 있습니다.
- 대형 이미지(고해상도) + 높은 Dilation 조합은 처리 시간이 길어질 수 있습니다.

---

## 🧯 트러블슈팅

### 1) 내부 콘텐츠가 같이 지워지는 경우(과삭제)
- Threshold를 **올리기**(예: 30~40)
- Dilation을 **내리기**(예: 10~40)
- 입력 이미지에서 윤곽선이 너무 어둡지 않거나, 내부 영역이 배경과 유사한 색이면 과삭제가 발생할 수 있습니다.

### 2) 배경이 남거나 초록빛/반투명 테두리가 남는 경우
- Threshold를 **내리기**(예: 10~20)
- Dilation을 **올리기**(예: 60~100)
- 배경 색이 여러 톤인 경우, 먼저 배경을 단순화한 이미지를 사용하면 성공률이 올라갑니다.

### 3) 처리가 매우 느린 경우(대형 이미지)
- Dilation을 **내리기**(예: 10~40)
- 가능한 경우 입력 이미지를 **축소**한 뒤 처리 후 결과를 활용

---

## ❓ FAQ

### Q: Aseprite가 필요한가요?
**A: 아니요!** GUI 버전은 Python/Pillow만 사용하므로 Aseprite 없이 작동합니다.

### Q: 어떤 이미지에서 잘 작동하나요?
**A:** 검은색 윤곽선이 있는 AI 생성 픽셀아트/일러스트에 최적화되어 있습니다.

### Q: 내부 콘텐츠가 지워지는 경우
**A:** Threshold 값을 높이세요 (예: 30-40). 윤곽선이 더 잘 인식됩니다.

### Q: 배경 잔여물이 남는 경우
**A:** Threshold 값을 낮추세요 (예: 10-15). 더 많은 픽셀이 제거됩니다.

---

## 📁 프로젝트 구조

```
I2g/
├── gui/
│   ├── main.py           # GUI 애플리케이션
│   ├── cleanup_core.py   # 배경 제거 알고리즘
│   ├── BackgroundCleaner_v0.0.3.spec  # PyInstaller 스펙(예시)
│   ├── requirements.txt  # Python 의존성
│   └── dist/
│       └── BackgroundCleaner_v0.0.3.exe  # 패키징된 실행 파일(로컬 빌드 산출물)
├── docs/
│   ├── before.png        # 사용 예시(전)
│   └── after.png         # 사용 예시(후)
```

---

## 🔨 직접 EXE 빌드하기

```bash
cd gui
pip install pyinstaller
pyinstaller --onefile --windowed --name "BackgroundCleaner_v0.0.3" --add-data "cleanup_core.py;." main.py
```

빌드된 exe는 `gui/dist/` 폴더에 생성됩니다. 해당 폴더는 **빌드 산출물**이므로 Git에 포함하지 않습니다.

---

## 🖥️ 배치 처리 CLI (개발자용)

GUI 없이 파일/폴더를 일괄 처리하고 결과를 PNG로 저장합니다.

### 사용 예시

```bash
# 단일 파일 처리
python gui/cleanup_cli.py --input "input.png" --output-dir "out"

# 폴더 처리(지원 확장자: png, jpg, jpeg, bmp, gif, webp)
python gui/cleanup_cli.py --input "in_dir" --output-dir "out_dir" --threshold 20 --dilation 50

# 하위 폴더까지 재귀 처리(폴더 구조 유지)
python gui/cleanup_cli.py --input "in_dir" --output-dir "out_dir" --recursive --threshold 20 --dilation 50
```

- **출력 규칙:** `<파일명>_cleaned.png`로 저장(PNG 고정, 투명 배경 유지)
- **재귀 모드:** `--recursive` 사용 시 입력 폴더 구조를 출력 폴더에 그대로 유지합니다.

---

## 📄 라이선스

MIT License

---

## 🤝 기여

이슈 및 PR 환영합니다!
