#!/usr/bin/env python3
"""
openGauss数据库命令行查询工具
无需依赖，直接查看数据库内容
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'VocabSlayer_update'))

try:
    import py_opengauss
except ImportError:
    try:
        import psycopg2 as py_opengauss
        print("注意: 使用 psycopg2 替代 py-opengauss")
    except ImportError:
        print("错误: 请安装 py-opengauss 或 psycopg2")
        print("命令: pip install py-opengauss psycopg2-binary")
        sys.exit(1)

# 数据库配置
DB_CONFIG = {
    'host': '10.129.211.118',
    'port': 5432,
    'database': 'vocabulary_db',
    'user': 'vocabuser',
    'password': 'OpenEuler123!'
}

def print_separator(title):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def connect_db():
    """连接数据库"""
    try:
        conn = py_opengauss.connect(**DB_CONFIG)
        print("✓ 数据库连接成功")
        return conn
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return None

def show_table_info(conn, table_name, description=""):
    """显示表信息"""
    try:
        cur = conn.cursor()

        # 获取记录数
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]

        # 获取前5条记录
        cur.execute(f"SELECT * FROM {table_name} LIMIT 5")
        records = cur.fetchall()

        # 获取列名
        cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position")
        columns = [col[0] for col in cur.fetchall()]

        print_separator(f"{description or table_name} ({count} 条记录)")

        # 打印列名
        print("列名:", " | ".join(f"{col:15}" for col in columns))
        print("-" * (16 * len(columns)))

        # 打印记录
        for record in records:
            values = []
            for value in record:
                if value is None:
                    values.append("NULL".ljust(15))
                elif isinstance(value, str) and len(value) > 13:
                    values.append(value[:13] + "...".ljust(15))
                else:
                    values.append(str(value)[:15].ljust(15))
            print(" | ".join(values))

        cur.close()

    except Exception as e:
        print(f"错误: {e}")

def show_vocabulary_stats(conn):
    """显示词汇统计"""
    try:
        cur = conn.cursor()

        print_separator("词汇库统计信息")

        # 词汇总数
        cur.execute("SELECT COUNT(*) FROM vocabulary")
        total = cur.fetchone()[0]
        print(f"词汇总数: {total}")

        # 按难度分布
        cur.execute("""
            SELECT level, COUNT(*) as count
            FROM vocabulary
            GROUP BY level
            ORDER BY level
        """)
        levels = cur.fetchall()
        print("\n难度分布:")
        for level, count in levels:
            print(f"  Level {level}: {count} 个词汇")

        # 随机显示5个词汇
        cur.execute("SELECT english, chinese FROM vocabulary ORDER BY RANDOM() LIMIT 5")
        samples = cur.fetchall()
        print("\n随机词汇示例:")
        for english, chinese in samples:
            print(f"  {english} - {chinese}")

        cur.close()

    except Exception as e:
        print(f"错误: {e}")

def show_user_stats(conn):
    """显示用户统计"""
    try:
        cur = conn.cursor()

        print_separator("用户统计信息")

        # 用户总数
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        print(f"用户总数: {total}")

        # 最活跃的用户
        cur.execute("""
            SELECT u.username, COUNT(lr.record_id) as study_count
            FROM users u
            LEFT JOIN user_learning_records lr ON u.user_id = lr.user_id
            GROUP BY u.user_id, u.username
            ORDER BY study_count DESC
            LIMIT 5
        """)
        users = cur.fetchall()
        print("\n最活跃用户:")
        for username, count in users:
            print(f"  {username}: {count} 条学习记录")

        cur.close()

    except Exception as e:
        print(f"错误: {e}")

def show_custom_banks(conn):
    """显示自定义题库"""
    try:
        cur = conn.cursor()

        print_separator("自定义题库信息")

        # 题库总数
        try:
            cur.execute("SELECT COUNT(*) FROM user_custom_banks")
            total = cur.fetchone()[0]
            print(f"自定义题库总数: {total}")

            # 题库详情
            cur.execute("""
                SELECT bank_name, question_count, created_at
                FROM user_custom_banks
                ORDER BY created_at DESC
                LIMIT 5
            """)
            banks = cur.fetchall()

            if banks:
                print("\n最近的题库:")
                for name, count, created in banks:
                    print(f"  {name}: {count} 道题 (创建于 {created})")
        except:
            print("自定义题库表不存在")

        cur.close()

    except Exception as e:
        print(f"错误: {e}")

def show_learning_progress(conn):
    """显示学习进度"""
    try:
        cur = conn.cursor()

        print_separator("学习进度概览")

        # 总学习记录
        cur.execute("SELECT COUNT(*) FROM user_learning_records")
        total_records = cur.fetchone()[0]
        print(f"总学习记录: {total_records}")

        # 按星级分布
        cur.execute("""
            SELECT star, COUNT(*) as count
            FROM user_learning_records
            WHERE star IS NOT NULL
            GROUP BY star
            ORDER BY star
        """)
        stars = cur.fetchall()
        print("\n掌握程度分布:")
        star_labels = {0: "未学习", 1: "认识", 2: "熟悉", 3: "掌握"}
        for star, count in stars:
            label = star_labels.get(star, f"Level {star}")
            print(f"  {label}: {count} 个词汇")

        cur.close()

    except Exception as e:
        print(f"错误: {e}")

def main():
    """主函数"""
    print("=" * 60)
    print("VocabSlayer - openGauss数据库查询工具")
    print("=" * 60)

    # 连接数据库
    conn = connect_db()
    if not conn:
        return

    try:
        # 1. 显示用户表
        show_table_info(conn, "users", "用户表")

        # 2. 显示词汇表
        show_table_info(conn, "vocabulary", "词汇表")

        # 3. 显示学习记录
        show_table_info(conn, "user_learning_records", "学习记录表")

        # 4. 显示复习列表
        show_table_info(conn, "user_review_list", "复习列表")

        # 5. 显示自定义题库
        try:
            show_table_info(conn, "user_custom_banks", "自定义题库表")
        except:
            print("\n自定义题库表不存在")

        # 6. 统计信息
        show_vocabulary_stats(conn)
        show_user_stats(conn)
        show_custom_banks(conn)
        show_learning_progress(conn)

        print_separator("数据库查询完成")

    finally:
        conn.close()
        print("数据库连接已关闭")

if __name__ == "__main__":
    main()