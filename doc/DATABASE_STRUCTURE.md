# 数据库表结构说明

## 表创建顺序调整

已将 `create_tables.sql` 中的表按照外键依赖关系重新组织，确保按正确顺序创建。

## 表依赖层级

### 第一层：独立基础表（无外键依赖）

这些表不依赖其他表，应首先创建：

1. **`userinfo`** - 用户信息表
2. **`admininfo`** - 管理员信息表
3. **`user_id_sequence`** - 用户ID序列表
4. **`movies`** - 电影信息表
5. **`persons`** - 人物信息表（演员、导演等）
6. **`keywords`** - 电影关键词表
7. **`production_companies`** - 制作公司表
8. **`production_countries`** - 制作国家表
9. **`spoken_languages`** - 语言表
10. **`scraper_state`** - 爬虫状态表

### 第二层：依赖于基础表的表

这些表依赖第一层的表，在第一层创建完成后创建：

#### 依赖 `userinfo` + `movies`
- **`user_ratings`** - 用户评分表
- **`comments`** - 电影评论表
- **`recommendations`** - 推荐表
- **`user_watch_history`** - 用户观影历史表

#### 仅依赖 `userinfo`
- **`user_genre_preferences`** - 用户类型偏好表

#### 依赖 `movies` + `persons`
- **`movie_cast`** - 电影演员表
- **`movie_crew`** - 电影工作人员表

#### 依赖 `movies` + 其他基础表
- **`movie_keywords`** - 电影-关键词关联表（movies + keywords）
- **`movie_production_companies`** - 电影-制作公司关联表（movies + production_companies）
- **`movie_production_countries`** - 电影-制作国家关联表（movies + production_countries）
- **`movie_spoken_languages`** - 电影-语言关联表（movies + spoken_languages）

### 第三层：依赖于第二层表的表

这些表依赖第二层的表，最后创建：

- **`comment_likes`** - 评论点赞表（依赖 `userinfo` + `user_ratings`）
- **`comment_replies`** - 评论回复表（依赖 `userinfo` + `user_ratings`）

## 表关系图

```
第一层（独立表）
├── userinfo
├── admininfo
├── user_id_sequence
├── movies
├── persons
├── keywords
├── production_companies
├── production_countries
├── spoken_languages
└── scraper_state

第二层（依赖基础表）
├── user_ratings (userinfo → movies)
│   ├── comment_likes (第三层)
│   └── comment_replies (第三层)
├── comments (userinfo → movies)
├── recommendations (userinfo → movies)
├── user_watch_history (userinfo → movies)
├── user_genre_preferences (userinfo)
├── movie_cast (movies → persons)
├── movie_crew (movies → persons)
├── movie_keywords (movies → keywords)
├── movie_production_companies (movies → production_companies)
├── movie_production_countries (movies → production_countries)
└── movie_spoken_languages (movies → spoken_languages)

第三层（依赖第二层表）
├── comment_likes (userinfo → user_ratings)
└── comment_replies (userinfo → user_ratings)
```

## 外键约束说明

所有外键约束都使用 `ON DELETE CASCADE`，确保：
- 删除用户时，自动删除其评分、评论、观影历史等
- 删除电影时，自动删除相关的评分、评论、关联关系等
- 维护数据的参照完整性

## 使用说明

### 创建数据库

```sql
CREATE DATABASE IF NOT EXISTS movies_recommend 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE movies_recommend;
```

### 执行表创建脚本

```sql
SOURCE movies_recommend/doc/create_tables.sql;
```

或通过命令行：

```bash
mysql -u root -p movies_recommend < movies_recommend/doc/create_tables.sql
```

### 验证表创建

```sql
-- 查看所有表
SHOW TABLES;

-- 查看表结构
DESCRIBE userinfo;
DESCRIBE movies;

-- 查看外键约束
SELECT 
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'movies_recommend'
AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME;
```

## 表数量统计

- **总表数**: 23个
- **独立基础表**: 10个
- **第二层表**: 11个
- **第三层表**: 2个

## 注意事项

1. **编码**: 所有表使用 `utf8mb4` 字符集和 `utf8mb4_unicode_ci` 排序规则
2. **存储引擎**: 所有表使用 InnoDB 引擎，支持外键和事务
3. **级联删除**: 所有外键约束都设置了 `ON DELETE CASCADE`
4. **索引**: 关键字段已创建索引，优化查询性能
5. **时间戳**: 使用 MySQL 的自动时间戳功能（`CURRENT_TIMESTAMP`）





