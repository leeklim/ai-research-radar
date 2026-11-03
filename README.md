# AI Research Radar

32개 AI 연구조직의 공개 연구 페이지를 정기 확인하고 GitHub Pages에서 보여주는 개인 연구 모니터링 대시보드입니다.

## 빠른 시작

1. GitHub에서 **public repository**를 생성하고 이 프로젝트 파일을 업로드합니다.
2. Repository **Settings → Pages → Build and deployment**에서 **GitHub Actions**를 선택합니다. 워크플로가 수집 후 `docs/`를 배포합니다.
3. **Actions → Refresh AI research → Run workflow**로 첫 수집을 실행합니다.
4. [공개 대시보드](https://leeklim.github.io/ai-research-radar/)에서 결과를 확인합니다.
5. 이후 GitHub Actions가 매일 00:17, 12:17 UTC(한국시간 09:17, 21:17)에 자동 수집합니다. GitHub의 예약 작업은 지연되거나 누락될 수 있습니다.

## 로컬 실행

```bash
python -m pip install -r requirements.txt
python scripts/collect.py
python -m http.server 8000
```

브라우저에서 `http://localhost:8000/docs/`를 엽니다. 로컬 확인 시 `/docs/` 경로가 중요합니다.

## 기능

- 기관별 논문 목록, 신규 연구 결과 수집, 제목 검색, 기관 필터
- 브라우저 로컬 저장소 기반 읽음 표시 및 북마크 (다른 기기와 동기화되지 않음)
- 사이트별 마지막 수집 성공/실패 표시
- 기존 게시물 ID와 최초 발견일 유지, 중복 방지
- GitHub Pages 정적 호스팅과 GitHub Actions 스케줄링

## 중요한 한계

- 기관이 운영하는 연구·출판 목록에서 직접 확인한 항목만 수집합니다. 각 카드의 공식 게시 목록 링크로 출처를 확인할 수 있습니다.
- 연구 페이지에 실린 원문이 외부 학술 사이트에 있더라도 등록할 수 있습니다. 목록 접근이 실패하면 이전에 같은 공식 목록에서 확인한 기록만 보존합니다. MIT CSAIL은 LIS 그룹, CMU ML은 학위논문 목록, Hugging Face는 Science 팀이 직접 편집한 논문 컬렉션을 확인합니다.
- `discovered`는 최초 발견일, `published`는 자료원에서 확인한 게시일입니다. 기관 목록에서 게시일을 제공하지 않으면 발견일만 표시합니다.
- 외부 사이트의 이용약관 및 robots 정책을 확인하고 필요한 기관별 수집기를 보완해야 합니다.
- 사이트가 실패하면 기존 기록은 유지되며, `docs/data.json`의 `status`에 실패 사유를 남깁니다.
- GitHub Pages는 기본적으로 공개 웹사이트입니다. 이메일 알림은 아직 구현되지 않았습니다. 알림이 필요하면 별도의 GitHub Actions 메일 발송이나 Telegram 연동을 추가해야 합니다.
- GitHub Actions의 저장소 쓰기 권한이 조직 정책으로 제한되면 workflow commit 단계가 실패할 수 있습니다.

## 구조

```
config/sources.json        # 추적할 32개 공식 사이트
scripts/collect.py        # RSS / HTML 수집, 기존 데이터 병합
.github/workflows/update.yml  # 하루 2회 수집
 docs/index.html           # 대시보드
 docs/sources.json         # 공개 대시보드용 기관 목록
 docs/data.json            # 수집 데이터
```

사이트 목록을 바꿀 때 `config/sources.json`과 `docs/sources.json`을 함께 변경하세요.
