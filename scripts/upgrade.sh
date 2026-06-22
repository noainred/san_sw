#!/usr/bin/env bash
# san_sw 자동 업그레이드 스크립트.
# 동작: 최신 릴리스 태그를 가져와 체크아웃하고 의존성을 설치한다.
# 주의: 코드 반영에는 프로세스 재시작이 필요하다(systemd/docker restart 등).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[upgrade] repo=$REPO_ROOT"
echo "[upgrade] 현재 버전: $(cat VERSION 2>/dev/null || echo unknown)"

echo "[upgrade] git fetch --tags ..."
git fetch --tags --prune origin

# 최신 semver 태그 선택(없으면 origin 기본 브랜치 최신)
LATEST_TAG="$(git tag -l 'v*' --sort=-v:refname | head -n1 || true)"
if [ -n "$LATEST_TAG" ]; then
  echo "[upgrade] 최신 태그로 체크아웃: $LATEST_TAG"
  git checkout -q "$LATEST_TAG"
else
  echo "[upgrade] 태그 없음 — 현재 브랜치 최신으로 갱신(git pull)"
  git pull --ff-only
fi

# 의존성 설치(venv가 있으면 그쪽 pip 사용)
if [ -x ".venv/bin/pip" ]; then
  PIP=".venv/bin/pip"
else
  PIP="python3 -m pip"
fi
echo "[upgrade] 의존성 설치: $PIP install -r requirements.txt"
$PIP install -q -r requirements.txt

echo "[upgrade] 완료. 새 버전: $(cat VERSION 2>/dev/null || echo unknown)"
echo "[upgrade] 프로세스를 재시작해야 새 코드가 반영됩니다."
