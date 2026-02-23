#!/bin/bash

# ==========================================
# 高对比度粗体颜色定义
# ==========================================
RED='\033[1;31m'    # 错误/卸载
GREEN='\033[1;32m'  # 成功
YELLOW='\033[1;33m' # 警告
BLUE='\033[1;34m'   # 装饰
CYAN='\033[1;36m'   # 提示/初始化
BOLD='\033[1m'      # 加粗
NC='\033[0m'        # 重置颜色

# ==========================================
# 1. 环境初始化 (自动安装逻辑)
# ==========================================
do_init_env() {
    echo -e "${CYAN}${BOLD}>>> 正在启动系统环境体检...${NC}"

    # 安装基础工具
    apt-get update -qq && apt-get install -y -qq sqlite3 fuse3 curl tar > /dev/null 2>&1

    # 检测并安装 JuiceFS
    if ! command -v juicefs &> /dev/null; then
        echo -e "${YELLOW}[状态] 未检测到客户端，正在通过官方脚本安装...${NC}"
        curl -sSL https://d.juicefs.com/install | sh > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}[成功] JuiceFS 已安装: $(juicefs --version)${NC}"
        else
            echo -e "${RED}[错误] 安装失败，请检查网络连接！${NC}"
        fi
    else
        echo -e "${GREEN}[就绪] JuiceFS 客户端已存在: $(juicefs --version)${NC}"
    fi

    # 加载必要内核模块
    modprobe fuse 2>/dev/null
    mkdir -p /mnt/juicefs_cache
    echo -e "${CYAN}${BOLD}>>> 环境体检完成！${NC}\n"
}

# ==========================================
# 2. 空间余量检测
# ==========================================
check_disk_space() {
    free_space=$(df / | tail -1 | awk '{print $4}')
    free_gb=$((free_space / 1024 / 1024))
    echo -e "${BOLD}系统盘可用空间: ${YELLOW}${free_gb} GB${NC}"
    if [ "$free_gb" -lt 1 ]; then
        echo -e "${RED}${BOLD}[警告] 空间不足 1GB，操作可能导致系统卡死！${NC}"
        return 1
    fi
    return 0
}

# ==========================================
# 3. 选项 1：新建挂载 (New)
# ==========================================
do_create() {
    check_disk_space || return
    echo -e "${CYAN}${BOLD}--- 新建 JuiceFS 存储配置 ---${NC}"
    printf "${BOLD}1. 存储名称 (如 tebi/wasabi): ${NC}"; read name
    printf "${BOLD}2. Bucket 地址 (完整 URL): ${NC}"; read bucket
    printf "${BOLD}3. Access Key: ${NC}"; read ak
    printf "${BOLD}4. Secret Key: ${NC}"; read sk

    db_path="/root/.$name.db"
    if [ -f "$db_path" ]; then
        echo -e "${RED}[错误] 数据库 $db_path 已存在！请先用选项 2 尝试恢复。${NC}"
        return
    fi

    echo -e "${BLUE}正在初始化元数据...${NC}"
    juicefs format --storage s3 --bucket "$bucket" --access-key "$ak" --secret-key "$sk" "sqlite3://$db_path" "$name"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}初始化成功，正在挂载...${NC}"
        do_recover
    else
        echo -e "${RED}初始化失败，请检查 Bucket 地址或密钥是否正确。${NC}"
    fi
}

# ==========================================
# 4. 选项 2：恢复挂载 (Recover)
# ==========================================
do_recover() {
    check_disk_space || return
    # 查找所有隐藏的以 .db 结尾的文件，排除 shm 和 wal
    DB_FILES=$(ls /root/.*.db 2>/dev/null)

    if [ -z "$DB_FILES" ]; then
        echo -e "${RED}[提示] /root 下没找到任何隐藏的 .db 文件。${NC}"
        return
    fi

    echo -e "${BLUE}${BOLD}>>> 正在批量扫描并恢复挂载...${NC}"
    for db in $DB_FILES; do
        # 提取名称：去掉路径和前后缀 . .db
        name=$(basename "$db" | sed 's/^\.\(.*\)\.db$/\1/')
        mount_point="/mnt/$name"
        cache_dir="/mnt/juicefs_cache/$name"

        if mountpoint -q "$mount_point"; then
            echo -e "${GREEN}[在线]${NC} $name"
            continue
        fi

        mkdir -p "$mount_point" "$cache_dir"

        # 挂载：512MB 缓存限额 + 异步写模式
        juicefs mount -d --writeback --cache-dir "$cache_dir" --cache-size 512 -o allow_other "sqlite3://$db" "$mount_point" 2>/tmp/jfs_error.log

        if [ $? -eq 0 ]; then
            echo -e "${GREEN}[成功]${NC} $name -> $mount_point"
        else
            echo -e "${RED}[失败]${NC} $name (原因: $(tail -n 1 /tmp/jfs_error.log))"
        fi
    done
}

# ==========================================
# 5. 选项 3：彻底卸载与清理 (Cleanup)
# ==========================================
do_cleanup() {
    echo -e "${RED}${BOLD}！！！ 警告：即将执行环境彻底清理 ！！！${NC}"
    echo -e "${RED}此操作将：卸载所有桶、删除程序、清空缓存。${NC}"
    read -p "是否同时删除 /root 下的 .db 数据库文件？(y/n): " del_db

    # A. 卸载所有 JuiceFS 挂载
    echo -e "${YELLOW}正在强制卸载挂载点...${NC}"
    mount | grep juicefs | awk '{print $3}' | while read mp; do
        juicefs umount "$mp" --force
        echo -e "${BLUE}已弹出: $mp${NC}"
    done

    # B. 清理缓存目录
    echo -e "${YELLOW}正在清理缓存目录 /mnt/juicefs_cache ...${NC}"
    rm -rf /mnt/juicefs_cache/*

    # C. 删除 JuiceFS 软件程序
    echo -e "${RED}正在删除 JuiceFS 客户端程序...${NC}"
    rm -f /usr/local/bin/juicefs
    rm -f /usr/bin/juicefs

    # D. 可选：删除元数据
    if [[ "$del_db" == "y" || "$del_db" == "Y" ]]; then
        echo -e "${RED}正在抹除所有元数据文件 (.db/.db-shm/.db-wal)...${NC}"
        rm -f /root/.*.db /root/.*.db-shm /root/.*.db-wal
    fi

    echo -e "${GREEN}${BOLD}>>> 清理完成！环境已恢复至原始状态。${NC}"
}

# ==========================================
# 主界面循环
# ==========================================
clear
do_init_env

while true; do
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${GREEN}${BOLD}         JUICEFS 自动化管理脚本 v4.0${NC}"
    echo -e "${BLUE}==================================================${NC}"
    echo -e "  ${YELLOW}1.${NC} 新建并挂载存储 (New Storage)"
    echo -e "  ${YELLOW}2.${NC} 扫描并恢复所有挂载 (Recover)"
    echo -e "  ${RED}3. 彻底卸载 JuiceFS 并清场 (Uninstall & Cleanup)${NC}"
    echo -e "  ${BOLD}0. 退出脚本 (Exit)${NC}"
    echo -e "${BLUE}--------------------------------------------------${NC}"
    printf "${BOLD}请选择 [0-3]: ${NC}"
    read choice

    case $choice in
        1) do_create ;;
        2) do_recover ;;
        3) do_cleanup ;;
        0) echo -e "${GREEN}脚本已退出。${NC}"; exit 0 ;;
        *) echo -e "${RED}无效选择，请输入 0-3 之间的数字。${NC}" ;;
    esac

    echo -e "\n${CYAN}操作完成，按回车键返回主菜单...${NC}"
    read
    clear
done