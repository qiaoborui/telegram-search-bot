#!/bin/bash
set -e

# 配置项
IMAGE_NAME="telegram-search-bot"
VERSION=$(date +"%Y%m%d")
REGISTRY="docker.io/qiaoborui"  # 默认改为Docker Hub官方仓库
PLATFORMS="linux/amd64,linux/arm64"

# 显示帮助信息
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  echo "用法: $0 [版本号] [仓库地址]"
  echo ""
  echo "参数:"
  echo "  版本号      镜像版本号，默认为当前日期 (${VERSION})"
  echo "  仓库地址    Docker镜像仓库地址，默认为 ${REGISTRY}"
  echo ""
  echo "示例:"
  echo "  $0                           # 使用默认设置构建并发布到Docker Hub"
  echo "  $0 v1.2.3                    # 指定版本号"
  echo "  $0 v1.2.3 ghcr.io/username   # 指定版本号和仓库地址"
  exit 0
fi

# 处理命令行参数
if [ -n "$1" ]; then
  VERSION="$1"
fi

if [ -n "$2" ]; then
  REGISTRY="$2"
fi

FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}"

echo "===== 开始构建多平台Docker镜像 ====="
echo "镜像名称: ${FULL_IMAGE_NAME}"
echo "版本: ${VERSION}"
echo "平台: ${PLATFORMS}"
echo "==============================="

# 确保Docker buildx可用
if ! docker buildx version > /dev/null 2>&1; then
  echo "错误: Docker buildx 不可用，正在尝试创建..."
  docker buildx create --name multiarch --use || {
    echo "无法创建Docker buildx构建器，请确保Docker版本支持buildx功能"
    exit 1
  }
fi

# 检查Docker登录状态
check_docker_login() {
  local registry=$1
  
  # 提取域名部分
  local domain=$(echo $registry | cut -d'/' -f1)
  
  # 如果是Docker Hub，域名是docker.io
  if [[ $domain != *"."* ]]; then
    domain="docker.io"
  fi
  
  # 检查是否已登录
  if ! docker info 2>/dev/null | grep -q "Username"; then
    echo "您尚未登录到Docker。请先登录:"
    
    if [[ $domain == "docker.io" ]]; then
      echo "运行: docker login"
    else
      echo "运行: docker login $domain"
    fi
    
    read -p "是否现在登录? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      if [[ $domain == "docker.io" ]]; then
        docker login
      else
        docker login $domain
      fi
    else
      echo "未登录，退出构建"
      exit 1
    fi
  else
    echo "已检测到Docker登录状态"
  fi
}

# 检查登录状态
check_docker_login $REGISTRY

# 构建并推送镜像
echo "正在构建并推送多平台Docker镜像..."
docker buildx build \
  --platform ${PLATFORMS} \
  --tag ${FULL_IMAGE_NAME}:${VERSION} \
  --tag ${FULL_IMAGE_NAME}:latest \
  --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
  --build-arg VERSION=${VERSION} \
  --push \
  .

echo "===== 构建完成 ====="
echo "镜像已发布: ${FULL_IMAGE_NAME}:${VERSION}"
echo "镜像已发布: ${FULL_IMAGE_NAME}:latest"
echo "==================="

# 显示如何使用镜像的提示
echo "使用方法:"
echo "docker pull ${FULL_IMAGE_NAME}:${VERSION}"
echo ""
echo "或者使用docker-compose:"
echo "---"
echo "version: '3'"
echo "services:"
echo "  telegram-search-bot:"
echo "    image: ${FULL_IMAGE_NAME}:${VERSION}"
echo "    volumes:"
echo "      - ./config:/app/config"
echo "    environment:"
echo "      - TELEGRAM_BOT_TOKEN=your_token_here"
echo "---" 