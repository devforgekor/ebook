#!/bin/bash
# setup.sh - VM 초기 설정 (root 권한으로 실행됨)

set -e

# 임시 디스크 준비 (이미 /mnt에 마운트되어 있음)
mkdir -p /mnt/models /mnt/data /mnt/output
chown -R azureuser:azureuser /mnt

# 시스템 업데이트 및 필수 패키지
apt-get update
apt-get install -y blobfuse2 fuse3 git build-essential

# llama.cpp 빌드
cd /home/azureuser
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
make -j4

# 환경 변수 등록
echo 'export PATH=$PATH:/home/azureuser/llama.cpp' >> /home/azureuser/.bashrc

echo "Setup complete."
