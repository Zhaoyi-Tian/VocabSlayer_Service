#!/usr/bin/env python3
"""
添加is_mastered字段到user_custom_answers表
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

def add_mastered_field():
    print("添加is_mastered字段")
    print("=" * 60)

    try:
        # 连接数据库
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("✓ 数据库连接成功")

        # 检查is_mastered字段是否存在
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'user_custom_answers'
            AND column_name = 'is_mastered';
        """)
        field_exists = cur.fetchone()

        if not field_exists:
            # 添加is_mastered字段
            print("\n添加is_mastered字段...")
            cur.execute("""
                ALTER TABLE user_custom_answers
                ADD COLUMN is_mastered BOOLEAN DEFAULT FALSE;
            """)
            print("✓ is_mastered字段添加成功")

            # 添加review_count字段
            print("\n添加review_count字段...")
            cur.execute("""
                ALTER TABLE user_custom_answers
                ADD COLUMN review_count INTEGER DEFAULT 0;
            """)
            print("✓ review_count字段添加成功")

            # 添加last_review_at字段
            print("\n添加last_review_at字段...")
            cur.execute("""
                ALTER TABLE user_custom_answers
                ADD COLUMN last_review_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            """)
            print("✓ last_review_at字段添加成功")

            # 提交更改
            conn.commit()
            print("\n✓ 所有更改已提交")
        else:
            print("\n is_mastered字段已存在")

        # 显示更新后的表结构
        print("\n更新后的表结构:")
        cur.execute("""
            SELECT column_name, ordinal_position, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'user_custom_answers'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        for col in columns:
            print(f"  {col[1]}: {col[0]} ({col[2]}) - {'可空' if col[3] == 'YES' else '非空'}")

        # 关闭连接
        cur.close()
        conn.close()

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    add_mastered_field()