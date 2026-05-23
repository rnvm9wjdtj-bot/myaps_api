#!/bin/bash
# =====================================================
# Monitor Models - Migration Tool (Ubuntu/Linux)
# Usage: ./migrate_all_in_one.sh [option]
#   1 - Auto Migration (default)
#   2 - Create tables with Tortoise
#   3 - Reset migrations
#   5 - Backup only
# =====================================================

set -e

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR"

# 查找Python解释器
find_python() {
    if [ -f "$PROJECT_DIR/venv/bin/python" ]; then
        echo "$PROJECT_DIR/venv/bin/python"
        return
    fi
    if command -v python3 &> /dev/null; then
        echo "python3"
        return
    fi
    echo "python3"
}

PYTHON_CMD=$(find_python)

# 从.env读取配置
load_env() {
    if [ -f "$PROJECT_DIR/.env" ]; then
        export $(grep -v '^#' "$PROJECT_DIR/.env" | grep -v '^$' | xargs)
    fi
}

load_env

SQLITE_FILE="${SQLITE_FILE:-local_data}"
SQLITE_FILE="${SQLITE_FILE%.sqlite3}"

# 显示菜单
show_menu() {
    clear
    echo "========================================"
    echo "  Monitor Models - Migration Tool"
    echo "========================================"
    echo ""
    echo "  Default option [1] runs auto migration"
    echo ""
    echo "  Please select an operation:"
    echo ""
    echo "    [1] Auto Migration (Recommended)"
    echo "        - Backup database automatically"
    echo "        - Create missing tables"
    echo "        - Add missing fields"
    echo "        - Preserve existing data"
    echo ""
    echo "    [2] Create tables with Tortoise"
    echo "        - Only create new tables"
    echo ""
    echo "    [3] Reset migrations"
    echo "        - Delete all migrations and re-init"
    echo ""
    echo "    [4] Add log query indexes"
    echo "        - Optimize log query performance"
    echo ""
    echo "    [5] Backup only"
    echo "        - Just backup database"
    echo ""
    echo "    [Q] Exit"
    echo ""
    echo "========================================"
}

# 备份数据库
backup_db() {
    echo ""
    echo "========================================"
    echo "  Backup Only"
    echo "========================================"
    
    local db_file="storage/${SQLITE_FILE}.sqlite3"
    if [ ! -f "$db_file" ]; then
        echo "[ERROR] Database not found: $db_file"
        return 1
    fi
    
    echo "[OK] Database exists"
    
    local backup_dir="backups"
    mkdir -p "$backup_dir"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${backup_dir}/${SQLITE_FILE}_${timestamp}.sqlite3"
    
    cp "$db_file" "$backup_file"
    echo "[OK] Backup successful: $backup_file"
    
    echo ""
    echo "========================================"
    echo "  Backup completed!"
    echo "========================================"
}

# 自动迁移
auto_migrate() {
    echo ""
    echo "========================================"
    echo "  Auto Migration"
    echo "========================================"
    
    echo ""
    echo "[INFO] Running auto migration..."
    echo ""
    
    $PYTHON_CMD scripts/migrate/auto_migrate.py
}

# 使用 Tortoise 创建表
tortoise_create() {
    echo ""
    echo "========================================"
    echo "  Create tables with Tortoise"
    echo "========================================"
    
    echo ""
    echo "[INFO] This option only creates new tables"
    echo ""
    
    $PYTHON_CMD scripts/migrate/migrate_with_tortoise.py
}

# 重置迁移
reset_migrations() {
    echo ""
    echo "========================================"
    echo "  Reset migrations"
    echo "========================================"
    echo ""
    echo "[WARNING] This will delete all migrations!"
    
    read -p "Are you sure? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "[INFO] Cancelled"
        return 0
    fi
    
    echo ""
    echo "[1/2] Deleting migrations..."
    
    if [ -d "migrations/monitor_models" ]; then
        rm -rf "migrations/monitor_models"
        echo "[OK] Deleted migrations/monitor_models"
    fi
    
    if [ -d "migrations" ]; then
        rm -rf migrations/*
        echo "[OK] Cleared migrations directory"
    fi
    
    echo ""
    echo "[2/2] Re-creating tables with Tortoise..."
    $PYTHON_CMD scripts/migrate/migrate_with_tortoise.py
    
    echo ""
    echo "========================================"
    echo "  Migrations reset!"
    echo "========================================"
}

# 添加日志查询索引
add_log_indexes() {
    echo ""
    echo "========================================"
    echo "  Add Log Query Indexes"
    echo "========================================"
    
    echo ""
    echo "[INFO] Creating indexes for log query optimization..."
    echo ""
    
    $PYTHON_CMD scripts/migrate/add_log_query_indexes.py --action migrate
}

# 主函数
main() {
    local choice="${1:-}"
    
    if [ -z "$choice" ]; then
        show_menu
        read -p "Enter option (default: 1): " choice
        choice="${choice:-1}"
    fi
    
    case "$choice" in
        1)
            auto_migrate
            ;;
        2)
            tortoise_create
            ;;
        3)
            reset_migrations
            ;;
        4)
            add_log_indexes
            ;;
        5)
            backup_db
            ;;
        [Qq])
            echo "Exit"
            exit 0
            ;;
        *)
            echo "[ERROR] Invalid option: $choice"
            show_menu
            exit 1
            ;;
    esac
}

main "$@"
