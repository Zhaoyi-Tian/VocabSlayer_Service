#!/usr/bin/env python3
"""
检查数据库表结构
"""
import psycopg2

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'vocabulary_db',
    'user': 'openEuler',
    'password': 'Qq13896842746'
}

def check_schema():
    print("检查数据库表结构")
    print("=" * 60)

    try:
        # 连接数据库
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("✓ 数据库连接成功")

        # 检查user_custom_banks表结构
        print("\nuser_custom_banks表结构:")
        cur.execute("""
            SELECT column_name, ordinal_position, data_type
            FROM information_schema.columns
            WHERE table_name = 'user_custom_banks'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        for col in columns:
            print(f"  {col[1]}: {col[0]} ({col[2]})")

        # 检查user_custom_questions表结构
        print("\nuser_custom_questions表结构:")
        cur.execute("""
            SELECT column_name, ordinal_position, data_type
            FROM information_schema.columns
            WHERE table_name = 'user_custom_questions'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        for col in columns:
            print(f"  {col[1]}: {col[0]} ({col[2]})")

        # 关闭连接
        cur.close()
        conn.close()

    except Exception as e:
        print(f"\n✗ 错误: {e}")

if __name__ == "__main__":
    check_schema()