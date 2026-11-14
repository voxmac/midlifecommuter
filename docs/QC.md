# MIDLIFE COMMUTER 제작 규칙과 자동 검증

SH01(「여섯 시 사십 분」)을 만들며 사람이 직접 찾아낸 문제를 규칙과 자동 검사로 바꿔 둔 문서입니다.
새 노래나 쇼츠를 만들 때는 이 순서대로 검사가 돌아가고, 걸린 것은 사람이 보기 전에 고쳐집니다.

## 1. 노래

| 문제 (SH01에서 실제로 있었던 일) | 규칙 | 자동 검사 |
| --- | --- | --- |
| 60초로 만들어서 마지막 줄이 잘림 | 길이는 가사에 맞춘다 (한 줄 2마디 + 앞뒤 여유) | `song.py`가 생성 전에 길이를 자동으로 늘림 |
| 고른 버전의 끝이 잘림 | 버전을 버리지 말고 끝만 다시 부른다 (`extend`) | 보컬 분리 후 "Song prep" 이슈에 ⚠ 표시 |
| 안 불린 줄 | — | 가사 줄별 일치율 50% 미만이면 ⚠ 표시 |

## 2. 장면 계획 (GPU 쓰기 전, `tools/make_short.py`)

| 문제 | 규칙 |
| --- | --- |
| 이웃 할머니가 장면 중간에 갑자기 나타남 | 동작 설명에 "나타난다/들어온다"를 쓰지 않는다. 등장인물은 첫 화면부터 그려 둔다 |
| 앉은 자세 그림에 벤치가 붙어 지하철 의자 위에 겹침 | `seated` 자세는 쓰지 않는다 (서 있는 자세 사용) |
| 언덕 장면에서 아들이 화면 끝에 잘림 | 인물 위치가 화면 가장자리에 걸리면 실행 전에 막는다 |
| 일본·중국풍 골목 | 장소 설명에 한국/서울이 없으면 "present-day South Korea"를 자동으로 붙인다 |
| 사람 없는 오토바이 | 오토바이·자전거는 되도록 쓰지 않는다 (영상 모델이 탄 사람을 자주 지움). 쓸 때는 반드시 탄 사람까지 쓴다 |

## 3. 그림과 영상 (Modal GPU, `studio/qc.py`)

장면 그림을 그린 직후와 움직임을 만든 직후(첫·중간·끝 화면) 두 번, 이미지 이해 모델(Qwen2.5-VL-7B)이 아래를 확인합니다.

1. 화면이 여러 칸으로 나뉘거나 같은 장면이 겹쳐 있음 (SH01 지하철 1차)
2. 아무도 타지 않은 오토바이·자전거가 움직이거나 길에 있음 (SH01 오르막 30초)
3. 탑·절 같은 일본·중국풍 건물 (SH01 오르막 2차)
4. 주요 인물이 화면에 잘리거나 얼굴·손발이 뭉개짐
5. 만화 캐릭터 옆의 실사 같은 사람
6. 장면 중간에 사람이나 물건이 갑자기 생기거나 사라짐
7. 인물 몸에 붙은 의자·벤치
8. 화면을 크게 차지하는 깨진 글씨

걸리면 장면 그림은 새로 최대 2번, 영상은 1번 더 만듭니다. 그래도 남은 문제는 검토 이슈에 ⚠로 표시되고,
`/retake S4`처럼 그 장면만 다시 만들 수 있습니다. 다 만든 장면은 Modal에 저장되므로 나머지는 다시 만들지 않습니다.

## 4. 자막과 화면

- 가사 한 줄은 끊지 않고 한 줄로 (길면 글씨를 줄여 맞춤), 반투명 띠 위, 화면 아래쪽(높이 83%)
- 상단 시리즈명 없음
- 장면은 가사 한 줄 = 한 장면, 모든 장면에 움직임(Wan 2.2)

## 5. 사람이 하는 일

가사 확정, 노래 버전 고르기(`/approve N`), 등장인물 고르기(`/pick`), 완성본 승인(`/approve`), 고칠 장면 지정(`/retake`).
Claude는 매 결과를 장면마다 처음·중간·끝 화면을 캡처해 직접 확인한 뒤에 보고합니다.

## Learned from SH03 (2026-11-14)
- Costume must match the story: after M leaves the company use `"lead": "mh"` (cardigan; `mh_sigh` is pyjamas for home mornings, `mh_bed` lies under a blanket). Lint blocks `m` (suit, badge, briefcase) in home scenes or in mh songs.
- Review every shot at 0.5 s steps (contact sheet per scene), not 3 frames: stray arms and vehicles appear mid-shot.
- Shot QC now checks 6 frames for vehicles in impossible places (slide, indoors) and hands that belong to nobody; Wan negative prompt lists them.
- Avoid street extras and roads near small children; prefer pedestrian paths, homes and eye-level plates (aerial plates make characters float).

## Learned from SH04 (2026-11-15)
- Every moving scene lists `must` (objects the motion animates: pot, laptop, phone...). The keyframe is checked for them before animating and redrawn if missing; lint refuses a motion that animates something not in `must`.
- `avoid` = scene-specific yes/no questions asked on every shot frame (e.g. steam from the ceiling instead of the pot).
- Plates are drawn square (1024²) and re-drawn at 9:16 from the centre crop: tall SDXL interiors stack into panels.
- An object a lyric depends on (laptop for "이력서를 쓴다") can be a composited `prop` instead of hoping the plate draws it; keep `key_seed` to reuse a good plate.
