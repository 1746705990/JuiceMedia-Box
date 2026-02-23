#!/bin/bash

# 定义路径和文件名
CHFS_DIR="/root/chfs"
CHFS_BIN="$CHFS_DIR/chfs-linux-amd64-3.1"
CHFS_INI="$CHFS_DIR/chfs.ini"

# 转换后的下载链接 (dl=1)
URL_BIN="https://www.dropbox.com/scl/fi/0tg9mtulqahygrea4mke4/chfs-linux-amd64-3.1?rlkey=sirb6ab26ed7ank3tg8rhbfti&st=3lndb9p9&dl=1"
URL_INI="https://www.dropbox.com/scl/fi/hjeiq52xtm0w4movtzge5/chfs.ini?rlkey=83o0tzf1aryv4gs2ob7m7ycqf&st=y8pegbd2&dl=1"

# 确保目录存在
mkdir -p $CHFS_DIR

# 下载函数
check_and_download() {
    if [ ! -f "$CHFS_BIN" ]; then
        echo "正在下载 chfs 主程序..."
        wget -O "$CHFS_BIN" "$URL_BIN"
        chmod +x "$CHFS_BIN"
    fi

    if [ ! -f "$CHFS_INI" ]; then
        echo "正在下载配置文件 chfs.ini..."
        wget -O "$CHFS_INI" "$URL_INI"
    fi
}

# 运行函数
start_chfs() {
    pid=$(pgrep -f "chfs-linux-amd64-3.1")
    if [ -n "$pid" ]; then
        echo "chfs 已经在运行中，PID: $pid"
    else
        echo "正在启动 chfs..."
        check_and_download
        cd $CHFS_DIR && ./chfs-linux-amd64-3.1 --file=chfs.ini > /dev/null 2>&1 &
        sleep 1
        new_pid=$(pgrep -f "chfs-linux-amd64-3.1")
        if [ -n "$new_pid" ]; then
            echo "chfs 启动成功，PID: $new_pid"
        else
            echo "chfs 启动失败，请检查配置。"
        fi
    fi
}

# 中止函数
stop_chfs() {
    pid=$(pgrep -f "chfs-linux-amd64-3.1")
    if [ -n "$pid" ]; then
        echo "正在停止 chfs (PID: $pid)..."
        kill $pid
        echo "chfs 已停止。"
    else
        echo "chfs 当前未运行。"
    fi
}

# 菜单循环
while true; do
    echo "=========================="
    echo "    chfs 管理脚本"
    echo "--------------------------"
    echo " 1. 运行 chfs"
    echo " 2. 中止 chfs"
    echo " 0. 退出脚本"
    echo "=========================="
    read -p "请输入选项 [0-2]: " choice

    case $choice in
        1)
            start_chfs
            ;;
        2)
            stop_chfs
            ;;
        0)
            echo "退出脚本。"
            exit 0
            ;;
        *)
            echo "无效输入，请重新选择。"
            ;;
    esac
    echo ""
done
