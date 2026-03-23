#!/bin/bash
set -eu

WORKSPACE="$(pwd)"
GIT_COMMON_DIR_RAW="$(git rev-parse --git-common-dir)"

# 相対パス(.git)なら絶対パスに変換
case "$GIT_COMMON_DIR_RAW" in
/*) GIT_COMMON_DIR="$GIT_COMMON_DIR_RAW" ;;
*) GIT_COMMON_DIR="$WORKSPACE/$GIT_COMMON_DIR_RAW" ;;
esac
GIT_COMMON_DIR="$(realpath "$GIT_COMMON_DIR")"

# .env を生成（docker-compose.yaml の変数展開に使用）
cat >.devcontainer/.env <<EOF
GIT_REPO=$GIT_COMMON_DIR
CURRENT_WORKSPACE_FOLDER=$WORKSPACE
EOF

# docker-compose.yaml を生成
cat >.devcontainer/docker-compose.yaml <<EOF
services:
  devcontainer:
    build:
      context: $WORKSPACE
      dockerfile: $WORKSPACE/.devcontainer/Dockerfile
    command: sleep infinity
    env_file:
      - .env
    volumes:
      - $WORKSPACE:$WORKSPACE:rw
      - $HOME/.gitconfig:/home/cntuser/.gitconfig:ro
EOF

# worktree の場合: git-common-dir が絶対パス（/始まり）になる
if [[ "$GIT_COMMON_DIR_RAW" == /* ]]; then
  echo "Worktree detected: also mounting $GIT_COMMON_DIR"
  cat >>.devcontainer/docker-compose.yaml <<EOF
      - $GIT_COMMON_DIR:$GIT_COMMON_DIR:rw
EOF
fi
