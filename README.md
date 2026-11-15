# MIDLIFE COMMUTER — 자동 제작 파이프라인

출근하는 모든 어른을 위한 노래 채널. 작업 파일(JSON) 하나를 올리면 **Modal GPU**에서 노래나 그림이 만들어지고,
GitHub이 검토 이슈를 메일로 보냅니다. 사람이 하는 일은 **듣고·보고 고르는 것**뿐입니다.

```
작업 파일 커밋 (songs/MCxx.json, cast/CASTx.json)
        │  GitHub Actions: produce
        ▼
Modal GPU (L4, 초당 과금, 월 $30 무료 크레딧)
  노래: ACE-Step 1.5 (한국어)  ·  그림: ComfyUI + SDXL (3D 애니풍)
        │
        ▼
GitHub Release(결과 파일) + 검토 이슈(메일 알림)
        │
VOXMAC 댓글: /approve 2   /pick m=3   /rerun
```

## 처음 한 번만 설정

### 1. Modal 토큰 만들기
1. https://modal.com 에 GitHub 계정으로 가입·로그인합니다.
2. 무료 크레딧(월 $30)을 받으려면 결제 수단 등록이 필요할 수 있습니다. 크레딧을 넘기 전에는 청구되지 않지만,
   **Settings → Usage and Billing**에서 월 사용 한도(예: $30)를 걸어 두세요.
3. **Settings → API Tokens → New Token**을 누릅니다.
4. 화면에 나오는 `token-id`(`ak-`로 시작)와 `token-secret`(`as-`로 시작)을 복사합니다. **secret은 이때 한 번만 보입니다.**

### 2. GitHub에 비밀값 등록
저장소 `voxmac/midlifecommuter` → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
| --- | --- |
| `MODAL_TOKEN_ID` | 위의 token-id (`ak-...`) |
| `MODAL_TOKEN_SECRET` | 위의 token-secret (`as-...`) |

### 3. Actions 권한 확인
**Settings → Actions → General → Workflow permissions**가 **Read and write permissions**인지 확인합니다
(결과를 Release로 올리고, 이슈를 만들고, 고른 버전을 커밋하기 위해 필요).

### 4. 첫 실행
**Actions → produce → Run workflow**에 `CAST1`(주인공 M 디자인 + 배너 배경) 또는 `MC01`(첫 노래)을 넣고 실행합니다.
첫 실행은 도구 설치와 모델 내려받기 때문에 30~60분 걸리고, 다음부터는 Modal 저장 공간(Volume)에 남아 훨씬 빨라집니다.

> Kaggle 토큰은 이 저장소에 필요 없습니다. Kaggle은 한 사람당 계정 하나만 허용하므로, Kaggle은 키즈 채널(puddlepals-studio)에서만 씁니다.

## 검토 이슈에서 쓰는 명령 (댓글)
| 명령 | 어디서 | 동작 |
| --- | --- | --- |
| `/approve 2` | 노래 검토 | 2번 버전을 확정 → 보컬 분리 + 가사 타이밍을 자동으로 만들고 "Song prep" 이슈가 옴 |
| `/pick m=3` | 디자인 검토 | 3번 후보를 주인공 M의 마스터 컷아웃(`assets/m_cut.png`)으로 저장 |
| `/rerun` | 어디서나 | 다시 실행 (노래는 새 시드로 새 버전 4개) |
| `/approve` | 어디서나 | 이슈 닫기 |

## 폴더
- `songs/` 노래 작업 (MC01, MC02 …). `lang: "ko"`, `duration`(초), `style`, `lyrics`, `gpu`.
- `cast/` 캐릭터 디자인·배경 작업 (CAST1 …).
- `studio/` 제작 엔진 (키즈 채널과 같은 코드), `tools/modal_job.py` Modal 실행기.
- `assets/` 확정된 컷아웃, 고른 노래 mp3.

## 비용 감
- 노래 60초 × 4버전: L4에서 수 분 → 수십 센트 수준.
- 디자인 후보 8장 + 배경 4장: L4에서 20~40분 → 1달러 안팎.
- 각 실행의 GPU 시간과 대략 비용은 검토 이슈 맨 아래 `Modal:` 줄에 나옵니다.

## GPU: Kaggle (free) + Modal (credits)
- `tools/route.py` decides: songs, character designs and first renders of a Short go to **Kaggle** (free T4, ~30 GPU h/week, slower;
  results collected every 20 min by `collect.yml`). Retakes and anything with `"runner": "modal"` go to **Modal** (fast L40S).
- Needs repo secrets `KAGGLE_USERNAME` / `KAGGLE_KEY` (the one original Kaggle account, same as puddlepals-studio). Without them everything runs on Modal.
- A Kaggle error or full GPU quota falls back to Modal automatically. Force one with Actions → produce → Run workflow → runner.
- Kaggle T4 has no room for the Qwen2.5-VL checker, so Kaggle renders rely on the scene plan's `must`/`avoid` lint and the 0.5 s frame review.
