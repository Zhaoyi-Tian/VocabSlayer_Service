/**
 * VocabSlayer 排行榜数据服务
 * 使用 libpq 连接 openGauss 数据库
 * 输出所有用户的统计数据，供客户端排序和显示
 */

#include <iostream>
#include <string>
#include <vector>
#include <ctime>
#include <sstream>
#include <iomanip>
#include <cstring>
#include <libpq-fe.h>
#include <unistd.h>

using namespace std;

// 用户统计数据结构
struct UserStats {
    string username;
    int today_questions;           // 今日答题数
    double today_accuracy;         // 今日正确率
    int total_questions;           // 历史总答题数
    double total_accuracy;         // 历史平均正确率
    int words_learned;             // 学习单词数
    double total_score;            // 总积分
    int study_days;                // 学习天数
    int continuous_days;           // 连续学习天数

    UserStats() : today_questions(0), today_accuracy(0.0),
                  total_questions(0), total_accuracy(0.0),
                  words_learned(0), total_score(0.0),
                  study_days(0), continuous_days(0) {}
};

// 数据库连接类
class DatabaseConnection {
private:
    PGconn* conn;
    string connInfo;

public:
    DatabaseConnection(const string& host, int port, const string& dbname,
                      const string& user, const string& password) {
        stringstream ss;
        ss << "host=" << host
           << " port=" << port
           << " dbname=" << dbname
           << " user=" << user
           << " password=" << password;
        connInfo = ss.str();
        conn = nullptr;
    }

    ~DatabaseConnection() {
        if (conn) {
            PQfinish(conn);
        }
    }

    bool connect() {
        conn = PQconnectdb(connInfo.c_str());
        if (PQstatus(conn) != CONNECTION_OK) {
            cerr << "连接数据库失败: " << PQerrorMessage(conn) << endl;
            return false;
        }
        cout << "✓ 成功连接到 openGauss 数据库" << endl;
        return true;
    }

    PGresult* executeQuery(const string& query) {
        PGresult* res = PQexec(conn, query.c_str());
        if (PQresultStatus(res) != PGRES_TUPLES_OK &&
            PQresultStatus(res) != PGRES_COMMAND_OK) {
            cerr << "查询失败: " << PQerrorMessage(conn) << endl;
            cerr << "SQL: " << query << endl;
            PQclear(res);
            return nullptr;
        }
        return res;
    }
};

// 统计数据服务类
class StatsService {
private:
    DatabaseConnection* db;

    // 安全地获取整数值
    int safeGetInt(PGresult* res, int row, int col) {
        char* val = PQgetvalue(res, row, col);
        return (val && strlen(val) > 0) ? atoi(val) : 0;
    }

    // 安全地获取浮点值
    double safeGetDouble(PGresult* res, int row, int col) {
        char* val = PQgetvalue(res, row, col);
        return (val && strlen(val) > 0) ? atof(val) : 0.0;
    }

    // 安全地获取字符串值
    string safeGetString(PGresult* res, int row, int col) {
        char* val = PQgetvalue(res, row, col);
        return (val && strlen(val) > 0) ? string(val) : "";
    }

public:
    StatsService(DatabaseConnection* database) : db(database) {}

    // 获取所有用户的综合统计数据
    vector<UserStats> getAllUserStats() {
        vector<UserStats> allStats;

        // 构建复杂查询，一次性获取所有数据
        string query = R"(
            SELECT
                u.username,

                -- 今日数据
                COALESCE(today.total_questions, 0) as today_questions,
                COALESCE(today.accuracy, 0) as today_accuracy,

                -- 历史总数据
                COALESCE(total.total_questions, 0) as total_questions,
                COALESCE(total.avg_accuracy, 0) as total_accuracy,

                -- 学习单词数
                COALESCE(words.words_learned, 0) as words_learned,

                -- 总积分
                COALESCE(config.total_score, 0) as total_score,

                -- 学习天数
                COALESCE(days.study_days, 0) as study_days

            FROM users u

            -- 今日统计
            LEFT JOIN (
                SELECT user_id, total_questions, accuracy
                FROM user_daily_stats
                WHERE date = CURRENT_DATE
            ) today ON u.user_id = today.user_id

            -- 历史总统计
            LEFT JOIN (
                SELECT user_id,
                       SUM(total_questions) as total_questions,
                       AVG(accuracy) as avg_accuracy
                FROM user_daily_stats
                GROUP BY user_id
            ) total ON u.user_id = total.user_id

            -- 学习单词统计
            LEFT JOIN (
                SELECT user_id,
                       COUNT(DISTINCT vocab_id) as words_learned
                FROM user_learning_records
                GROUP BY user_id
            ) words ON u.user_id = words.user_id

            -- 总积分
            LEFT JOIN user_config config ON u.user_id = config.user_id

            -- 学习天数统计
            LEFT JOIN (
                SELECT user_id,
                       COUNT(DISTINCT date) as study_days
                FROM user_daily_stats
                WHERE total_questions > 0
                GROUP BY user_id
            ) days ON u.user_id = days.user_id

            ORDER BY u.username
        )";

        PGresult* res = db->executeQuery(query);
        if (!res) return allStats;

        int rows = PQntuples(res);
        for (int i = 0; i < rows; i++) {
            UserStats stats;
            stats.username = safeGetString(res, i, 0);
            stats.today_questions = safeGetInt(res, i, 1);
            stats.today_accuracy = safeGetDouble(res, i, 2);
            stats.total_questions = safeGetInt(res, i, 3);
            stats.total_accuracy = safeGetDouble(res, i, 4);
            stats.words_learned = safeGetInt(res, i, 5);
            stats.total_score = safeGetDouble(res, i, 6);
            stats.study_days = safeGetInt(res, i, 7);
            stats.continuous_days = 0; // TODO: 需要额外计算连续天数

            allStats.push_back(stats);
        }

        PQclear(res);
        return allStats;
    }

    // 打印表头
    void printHeader() {
        cout << "\n" << string(120, '=') << endl;
        cout << "  VocabSlayer 用户统计数据表 - 可用于客户端排序" << endl;
        cout << string(120, '=') << endl;

        cout << left
             << setw(18) << "用户名"
             << setw(12) << "今日题数"
             << setw(12) << "今日正确率"
             << setw(12) << "总题数"
             << setw(12) << "总正确率"
             << setw(12) << "学习单词"
             << setw(12) << "总积分"
             << setw(12) << "学习天数"
             << endl;
        cout << string(120, '-') << endl;
    }

    // 打印单行数据
    void printRow(const UserStats& stats) {
        cout << left
             << setw(18) << stats.username
             << setw(12) << stats.today_questions
             << setw(12) << fixed << setprecision(1) << stats.today_accuracy << "%"
             << setw(12) << stats.total_questions
             << setw(12) << fixed << setprecision(1) << stats.total_accuracy << "%"
             << setw(12) << stats.words_learned
             << setw(12) << fixed << setprecision(2) << stats.total_score
             << setw(12) << stats.study_days
             << endl;
    }

    // 打印表尾
    void printFooter() {
        cout << string(120, '=') << endl;
    }

    // 输出 JSON 格式
    void displayJsonStats() {
        vector<UserStats> allStats = getAllUserStats();

        cout << "{" << endl;
        cout << "  \"timestamp\": " << time(nullptr) << "," << endl;
        cout << "  \"user_count\": " << allStats.size() << "," << endl;
        cout << "  \"users\": [" << endl;

        for (size_t i = 0; i < allStats.size(); i++) {
            const UserStats& stats = allStats[i];
            cout << "    {" << endl;
            cout << "      \"username\": \"" << stats.username << "\"," << endl;
            cout << "      \"today_questions\": " << stats.today_questions << "," << endl;
            cout << "      \"today_accuracy\": " << fixed << setprecision(2) << stats.today_accuracy << "," << endl;
            cout << "      \"total_questions\": " << stats.total_questions << "," << endl;
            cout << "      \"total_accuracy\": " << fixed << setprecision(2) << stats.total_accuracy << "," << endl;
            cout << "      \"words_learned\": " << stats.words_learned << "," << endl;
            cout << "      \"total_score\": " << fixed << setprecision(2) << stats.total_score << "," << endl;
            cout << "      \"study_days\": " << stats.study_days << endl;
            cout << "    }" << (i < allStats.size() - 1 ? "," : "") << endl;
        }

        cout << "  ]" << endl;
        cout << "}" << endl;
    }

    // 显示所有用户统计数据（表格格式）
    void displayAllStats() {
        vector<UserStats> allStats = getAllUserStats();

        if (allStats.empty()) {
            cout << "\n暂无用户数据\n" << endl;
            return;
        }

        printHeader();
        for (const auto& stats : allStats) {
            printRow(stats);
        }
        printFooter();

        cout << "\n统计说明:" << endl;
        cout << "  • 今日题数     - 今天答题数量" << endl;
        cout << "  • 今日正确率   - 今天答题正确率" << endl;
        cout << "  • 总题数       - 历史累计答题数" << endl;
        cout << "  • 总正确率     - 历史平均正确率" << endl;
        cout << "  • 学习单词     - 学习过的不重复单词数" << endl;
        cout << "  • 总积分       - 用户累计总积分" << endl;
        cout << "  • 学习天数     - 累计学习天数" << endl;
        cout << "\n客户端可以根据任意列进行排序显示排行榜\n" << endl;
    }
};

// 主函数
int main(int argc, char* argv[]) {
    // 检查是否为 JSON 模式
    bool jsonMode = false;
    bool onceMode = false;  // 只运行一次，不循环

    // 解析命令行参数
    string host = "localhost";
    int port = 5432;
    string dbname = "vocabulary_db";
    string user = "openEuler";
    string password = "Qq13896842746";

    for (int i = 1; i < argc; i++) {
        string arg = argv[i];
        if (arg == "--json") {
            jsonMode = true;
            onceMode = true;  // JSON 模式默认只运行一次
        } else if (arg == "--once") {
            onceMode = true;
        } else if (arg == "--help" || arg == "-h") {
            cout << "VocabSlayer 排行榜统计服务\n" << endl;
            cout << "用法:" << endl;
            cout << "  " << argv[0] << " [选项] [host] [port] [dbname] [user] [password]\n" << endl;
            cout << "选项:" << endl;
            cout << "  --json         输出 JSON 格式（自动启用 --once）" << endl;
            cout << "  --once         只查询一次，不循环刷新" << endl;
            cout << "  --help, -h     显示此帮助信息\n" << endl;
            cout << "数据库连接参数（可选，默认值如下）:" << endl;
            cout << "  host           数据库主机 (默认: localhost)" << endl;
            cout << "  port           数据库端口 (默认: 5432)" << endl;
            cout << "  dbname         数据库名称 (默认: vocabulary_db)" << endl;
            cout << "  user           数据库用户 (默认: openEuler)" << endl;
            cout << "  password       数据库密码 (默认: Qq13896842746)\n" << endl;
            cout << "示例:" << endl;
            cout << "  " << argv[0] << "                          # 表格模式，持续刷新" << endl;
            cout << "  " << argv[0] << " --json                  # JSON 模式，查询一次" << endl;
            cout << "  " << argv[0] << " --once                  # 表格模式，查询一次" << endl;
            cout << "  " << argv[0] << " localhost 5432 vocabulary_db openEuler password" << endl;
            return 0;
        } else if (i == 1 || (i == 2 && (string(argv[1]) == "--json" || string(argv[1]) == "--once"))) {
            host = arg;
        } else if (i == 2 || (i == 3 && (string(argv[1]) == "--json" || string(argv[1]) == "--once"))) {
            port = atoi(arg.c_str());
        } else if (i == 3 || (i == 4 && (string(argv[1]) == "--json" || string(argv[1]) == "--once"))) {
            dbname = arg;
        } else if (i == 4 || (i == 5 && (string(argv[1]) == "--json" || string(argv[1]) == "--once"))) {
            user = arg;
        } else if (i == 5 || (i == 6 && (string(argv[1]) == "--json" || string(argv[1]) == "--once"))) {
            password = arg;
        }
    }

    if (!jsonMode) {
        cout << "==================================================" << endl;
        cout << "  VocabSlayer 统计数据服务" << endl;
        cout << "==================================================" << endl;
    }

    // 创建数据库连接
    DatabaseConnection db(host, port, dbname, user, password);
    if (!db.connect()) {
        if (jsonMode) {
            cout << "{\"error\": \"无法连接到数据库\"}" << endl;
        } else {
            cerr << "无法连接到数据库" << endl;
        }
        return 1;
    }

    // 创建统计服务
    StatsService service(&db);

    if (onceMode) {
        // 只运行一次
        if (jsonMode) {
            service.displayJsonStats();
        } else {
            time_t now = time(nullptr);
            cout << "\n⏰ 查询时间: " << ctime(&now);
            service.displayAllStats();
        }
    } else {
        // 主循环 - 定时刷新统计数据
        int refreshInterval = 60; // 刷新间隔（秒）

        cout << "\n统计数据服务已启动，每 " << refreshInterval << " 秒刷新一次" << endl;
        cout << "按 Ctrl+C 退出服务\n" << endl;

        while (true) {
            // 显示当前时间
            time_t now = time(nullptr);
            cout << "\n⏰ 更新时间: " << ctime(&now);

            // 显示所有用户统计数据
            service.displayAllStats();

            // 等待下次刷新
            sleep(refreshInterval);
        }
    }

    return 0;
}
