# Render 배포 및 데이터 보관

확인일: 2026-10-31

## 현재 배포 구성

- 서비스: https://gnu-10team.onrender.com
- 저장소: `yongkyu4803/gnu_10team`, `main` 브랜치
- 런타임: Python 3.12, FastAPI + Uvicorn 단일 워커
- 요금제: Free (영구 디스크 미연결)
- 저장 방식: 프로젝트 루트의 `data/` 아래 JSON 및 작업 파일

기존 서비스에 다음 설정을 적용하고 배포를 확인했습니다. 메인·관리자 화면, 상태 확인·기준 조회 API, `ex.txt`의 JOC 기준 원고 분석이 정상 응답했습니다. 이는 확인 시점의 결과이며 이후 배포 상태는 CLI나 대시보드에서 확인합니다.

| 설정 | 값 |
|---|---|
| Root Directory | 비워 둠: 저장소 루트 |
| Build Command | `bash scripts/render-build.sh` |
| Start Command | `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health Check Path | `/api/health` |

빌드 스크립트가 spaCy 3.8.11과 영어 모델 `en_core_web_sm 3.8.0`을 설치·검증합니다. `gunicorn app:app`은 이 프로젝트의 진입점이 아닙니다. `.python-version`은 3.12이며 Render 환경변수의 Python 버전 재정의와 충돌하지 않아야 합니다.

`render.yaml`을 GitHub에 추가하는 것만으로 기존 수동 생성 서비스의 설정이 자동 변경되지는 않습니다. 위 설정은 기존 서비스에 직접 적용했습니다.

## 어떤 데이터가 유지되나요?

Render의 기본 파일시스템은 임시 저장소입니다. 영구 디스크가 없으면 재배포·서버 재시작 시 실행 중 만든 파일 변경이 소실됩니다. 무료 서비스에는 영구 디스크를 연결할 수 없습니다. 유료 서비스도 디스크를 연결하지 않으면 같은 제한이 있습니다. [Render 무료 서비스 안내](https://render.com/docs/free), [영구 디스크 안내](https://render.com/docs/disks)

| 데이터 | 저장 위치 | 재배포 후 |
|---|---|---|
| 앱 코드·화면·설정 | GitHub 저장소 | 배포 커밋의 파일로 제공 |
| 분야별 논문 마크다운 | GitHub 저장소의 분야별 폴더 | 유지 |
| 초기 분야 기준 | `baselines_markdown/` 등 추적 파일 | 유지, 새 `data/` 초기화에 사용 |
| 업로드 PDF·작업 결과·수정 판정 | `data/jobs/` | 소실 |
| 입력 원고·분석 결과 | `data/manuscripts/` | 소실 |
| 실행 중 생성한 기준 | `data/baselines/` | 소실 |
| 현재 적용 버전·변경 이력 | `data/admin/registry.json` | 소실 |
| 보관 기준 버전·재계산 작업 | `data/admin/versions/`, `data/admin/jobs/` | 소실 |
| 관리자 자격 정보·최초 비밀번호 | `data/admin/credentials.json`, `initial_password.txt` | 소실, 다음 초기화에서 새로 생성 |

`data/`는 `.gitignore`로 제외되어 GitHub 푸시로 백업되지 않습니다. 로컬 PC의 `data/`와 Render 서버의 `data/`도 서로 다른 파일이며 자동 동기화되지 않습니다.

예를 들어 관리자가 JOC 기준을 재계산해 적용한 후 새 코드를 배포하면, 현재 무료 구성에서는 변경한 기준과 이력이 사라지고 저장소에 포함된 초기 기준으로 초기화됩니다. 관리자 비밀번호와 세션 서명 키도 바뀌므로 이전 비밀번호·로그인 세션을 사용할 수 없습니다.

로컬 PC에서는 `data/`를 삭제하지 않는 한 앱 프로세스를 다시 실행해도 파일이 남습니다. Render에서의 초기화는 JSON 형식 때문이 아니라 서버 파일시스템의 수명 때문입니다.

## JSON 방식으로 영구 보관하려면

1. 영구 디스크를 지원하는 유료 웹 서비스로 전환합니다. 요금제 변경만으로 파일이 보존되지는 않습니다.
2. 현재 앱이 실제로 사용하는 `<프로젝트 루트>/data`에 영구 디스크를 연결합니다. 기본 네이티브 Python 환경에서는 `/opt/render/project/src/data`가 해당 경로이며, 적용 전에 서비스의 실제 프로젝트 경로를 확인합니다.
3. 기존 실행 데이터를 보관해야 한다면 전환·재배포 전에 `data/` 전체를 별도로 백업합니다. 새 디스크 연결 시 기존 임시 저장소 파일이 자동 복사되지는 않습니다.
4. 백업을 디스크에 복원한 다음 앱을 시작하고 현재 기준·이력·관리자 로그인을 확인합니다.
5. 테스트 데이터를 저장한 뒤 재시작·재배포하고 보존 여부를 확인합니다.

현재 코드는 저장 경로를 프로젝트 루트의 `data/`로 고정합니다. 다른 위치에 디스크를 연결하려면 저장 경로를 설정으로 받을 수 있도록 코드를 수정하거나 해당 경로를 연결해야 합니다. JSON 방식은 그대로 사용할 수 있으며 `--workers 1`을 유지합니다.

영구 디스크는 마운트 경로 아래 파일만 보존하며 빌드 단계에서는 접근할 수 없습니다. 기준 초기화는 현재 앱 시작 단계에서 수행합니다. [디스크 제한 사항](https://render.com/docs/disks)

## 백업과 복원

- 변경 이력과 관리자 상태까지 복원하려면 `data/` 전체를 함께 백업합니다. 기준 JSON 하나나 재계산 작업 ZIP만으로 전체 상태를 복원할 수 없습니다.
- 쓰기가 진행 중인 파일들의 불일치를 피하도록 분석·재계산·기준 적용을 멈춘 상태에서 일관된 백업을 확보합니다.
- 백업에는 원고·업로드 논문·관리자 비밀번호 해시·세션 서명 키가 포함됩니다. 비공개로 보관하고 GitHub에 커밋하지 않습니다.
- 복원은 같은 코드·분석 규칙 버전을 기준으로 수행하고 파일 접근 권한도 확인합니다. 규칙 해시가 다르면 기준 재계산이 필요할 수 있습니다.
- 영구 디스크도 실수로 삭제한 파일을 자동으로 되돌려 주는 백업의 대체 수단은 아닙니다. 별도 백업을 유지합니다.

현재 서비스에는 영구 디스크나 자동 백업을 설정하지 않았습니다. 무료 구성은 데이터 소실을 허용하는 시연·검증 용도로 사용합니다.

## CLI로 상태 확인

```sh
render login
render services --output json
render deploys list srv-dbiu60ks728c738aoc10 --output json
render logs --resources srv-dbiu60ks728c738aoc10 --limit 30 --output text
curl --max-time 30 https://gnu-10team.onrender.com/api/health
```

정상 상태 확인 응답은 `{"status":"ok"}`입니다. 이 응답만으로 분석 모델과 모든 기능의 정상 동작까지 보장하지는 않으므로 배포 후 기준 조회와 원고 분석도 확인합니다.

[Render CLI 문서](https://render.com/docs/cli)
