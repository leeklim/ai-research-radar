# AI Research Radar

27개 AI 연구조직의 공개 연구 페이지를 정기 확인하고 GitHub Pages에서 보여주는 개인 연구 모니터링 대시보드입니다.

## 빠른 시작

1. GitHub에서 **public repository**를 생성하고 이 프로젝트 파일을 업로드합니다.
2. Repository **Settings → Pages → Build and deployment → Deploy from a branch**, branch `main`, folder `/docs`로 설정합니다.
3. **Actions → Refresh AI research → Run workflow**로 첫 수집을 실행합니다.
4. 몇 분 뒤 `https://<계정>.github.io/<저장소>/`에서 확인합니다.
5. 이후 GitHub Actions가 매일 00:17, 12:17 UTC(한국시간 09:17, 21:17)에 자동 수집합니다. GitHub의 예약 작업은 지연되거나 누락될 수 있습니다.

## 로컬 실행

```bash
python -m pip install -r requirements.txt
python scripts/collect.py
python -m http.server 8000
```

브라우저에서 `http://localhost:8000/docs/`를 엽니다. 로컬 확인 시 `/docs/` 경로가 중요합니다.

## 기능

- 기관별 연구 페이지 목록, 신규 게시물 수집, 제목 검색, 기관 필터
- 브라우저 로컬 저장소 기반 읽음 표시 및 북마크 (다른 기기와 동기화되지 않음)
- 사이트별 마지막 수집 성공/실패 표시
- 기존 게시물 ID와 최초 발견일 유지, 중복 방지
- GitHub Pages 정적 호스팅과 GitHub Actions 스케줄링

## 중요한 한계

- 공식 RSS/Atom이 있는 경우 이를 우선 사용합니다. 나머지는 일반 HTML 링크를 휴리스틱으로 수집합니다. JavaScript 렌더링 사이트, 구조가 다른 페이지, 차단 정책에 따라 수집이 실패하거나 관련 없는 링크가 섞일 수 있습니다.
- 홈페이지의 링크를 찾았다고 해서 그 논문이 그날 발표된 것은 아닙니다. `discovered`는 최초 수집일이고 `published`는 피드에서 제공한 날짜 문자열입니다.
- HTML에서 본문이나 초록은 수집하지 않습니다. 제목/URL 위주로 저장합니다.
- 외부 사이트의 이용약관 및 robots 정책을 확인하고 필요한 기관별 수집기를 보완해야 합니다.
- 사이트가 실패하면 기존 기록은 유지되며, `docs/data.json`의 `status`에 실패 사유를 남깁니다.
- GitHub Pages는 기본적으로 공개 웹사이트입니다. 이메일 알림은 아직 구현되지 않았습니다. 알림이 필요하면 별도의 GitHub Actions 메일 발송이나 Telegram 연동을 추가해야 합니다.
- GitHub Actions의 저장소 쓰기 권한이 조직 정책으로 제한되면 workflow commit 단계가 실패할 수 있습니다.

## 구조

```
config/sources.json        # 추적할 27개 공식 사이트
scripts/collect.py        # RSS / HTML 수집, 기존 데이터 병합
.github/workflows/update.yml  # 하루 2회 수집
 docs/index.html           # 대시보드
 docs/sources.json         # 공개 대시보드용 기관 목록
 docs/data.json            # 수집 데이터
```

사이트 목록을 바꿀 때 `config/sources.json`과 `docs/sources.json`을 함께 변경하세요.
