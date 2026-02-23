#!/bin/bash

# 1. 动态获取当前所有 JuiceFS 挂载点
mount_points=$(mount | grep juicefs | awk '{print $3}')

if [ -z "$mount_points" ]; then
    echo "未发现活跃的 JuiceFS 挂载点。"
else
    for mp in $mount_points; do
        echo "正在卸载: $mp ..."
        juicefs umount "$mp"
        
        if [ $? -ne 0 ]; then
            echo "正常卸载失败，正在尝试强制卸载 $mp..."
            juicefs umount "$mp" --force
        fi
    done
    echo "所有 JuiceFS 挂载点已处理完毕。"
fi

# 2. 强制合并 SQLite WAL 日志到 .db 文件
echo "正在检测并合并元数据日志 (WAL)..."

# 检查是否安装了 sqlite3
if ! command -v sqlite3 &> /dev/null; then
    echo "错误: 未安装 sqlite3，无法执行合并。请运行: apt install sqlite3 -y"
else
    # 获取当前目录下所有的 .db 文件
    db_files=$(ls .*.db 2>/dev/null)
    
    for db in $db_files; do
        if [ -f "${db}-wal" ]; then
            echo "正在合并: $db ..."
            # 赋予权限确保可写，否则无法合并
            chmod +w "$db" "${db}-wal" "${db}-shm" 2>/dev/null
            # 执行强制合并
            sqlite3 "$db" "PRAGMA wal_checkpoint(TRUNCATE);"
            echo "$db 合并完成。"
        fi
    done
fi

echo "现在你可以安全地备份单独的 .db 文件了。"
