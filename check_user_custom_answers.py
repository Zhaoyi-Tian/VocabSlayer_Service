#!/usr/bin/env python3
"""
检查user_custom_answers表结构
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

def check_table():
    print("检查user_custom_answers表结构")
    print("=" * 60)

    try:
        # 连接数据库
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("✓ 数据库连接成功")

        # 检查表是否存在
        cur.execute("""
            SELECT EXISTS (
                SELECT * FROM information_schema.tables
                WHERE table_name = 'user_custom_answers'
            );
        """)
        table_exists = cur.fetchone()[0]
        print(f"\n表是否存在: {table_exists}")

        if table_exists:
            # 检查表结构
            print("\n表结构:")
            cur.execute("""
                SELECT column_name, ordinal_position, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'user_custom_answers'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()
            for col in columns:
                print(f"  {col[1]}: {col[0]} ({col[2]}) - {'可空' if col[3] == 'YES' else '非空'}")

            # 检查数据
            cur.execute("SELECT COUNT(*) FROM user_custom_answers")
            count = cur.fetchone()[0]
            print(f"\n记录数: {count}")

            if count > 0:
                cur.execute("SELECT * FROM user_custom_answers LIMIT 5")
                records = cur.fetchall()
                print("\n前5条记录:")
                for record in records:
                    print(f"  {record}")
        else:
            # 创建表
            print("\n创建表...")
            cur.execute("""
                CREATE TABLE user_custom_answers (
                    answer_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    is_correct BOOLEAN NOT NULL,
                    answer_time INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_mastered BOOLEAN DEFAULT FALSE,
                    review_count INTEGER DEFAULT 0,
                    last_review_at TIMESTAMP,
                    UNIQUE(user_id, question_id)
                );
            """)
            print("✓ 表创建成功")

        # 关闭连接
        cur.close()
        conn.close()

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_table()