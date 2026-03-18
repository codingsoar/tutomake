## 2026-03-19 Step Instruction 기능 추가

- **Request**: 튜토리얼 내보내기 시 히트박스에 대한 상세 지시사항(instruction) 입력 기능 추가
- **Scope**: model, editor, player, web/document exporters
- **Implemented**:
  - `model.py`: Step에 `instruction: str = ""` 필드 추가
  - `editor.py`: Properties 패널에 멀티라인 Instruction 입력란 추가 (QTextEdit, 80px 높이)
  - `player.py`: 히트박스 설명 박스에서 instruction 우선 표시 + 동적 박스 크기 조정
  - `web_exporter.py`: HTML/Video HTML step data에 instruction 포함, 헤더에 instruction 표시 영역 추가
  - `document_exporter.py`: Markdown(인용 블록), PDF(이탤릭), PPTX(이탤릭 텍스트박스)에 instruction 추가
- **Validation**: 코드 변경 사항 리뷰 완료 (자동화 테스트 없음, GUI 기반 수동 테스트 필요)
- **Files**:
  - `src/model.py`
  - `src/ui/editor.py`
  - `src/ui/player.py`
  - `src/exporters/web_exporter.py`
  - `src/exporters/document_exporter.py`
- **Notes**: 기존 `.tutomake` 파일과 하위 호환성 유지 (instruction 기본값 빈 문자열)
