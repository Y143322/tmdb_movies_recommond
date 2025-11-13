-- ============================================
-- 电影推荐系统数据库表创建脚本
-- 按照正确的依赖关系顺序创建表
-- ============================================

-- ============================================
-- 第一层：独立基础表（无外键依赖）
-- ============================================

-- 用户信息表：存储普通用户账户信息
CREATE TABLE if not exists `userinfo` (
  `id` int NOT NULL, -- 用户ID（主键，唯一标识）
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL, -- 用户名（唯一）
  `password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL, -- 密码（哈希加密存储）
  `email` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 用户邮箱
  `reset_password` tinyint(1) DEFAULT '0', -- 密码重置标志（0-无需重置，1-需重置）
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 账户创建时间戳
  `status` enum('active','banned','deleted') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active' COMMENT '用户状态(active-正常,banned-封禁,deleted-删除)', -- 账户状态
  `mute_expires_at` timestamp NULL DEFAULT NULL, -- 禁言到期时间
  PRIMARY KEY (`id`), -- 主键约束
  UNIQUE KEY `username` (`username`) -- 唯一索引（确保用户名不重复）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 管理员信息表：存储系统管理员账户信息
CREATE TABLE if not exists `admininfo` (
  `id` int NOT NULL, -- 管理员ID（主键，唯一标识）
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL, -- 管理员用户名（唯一）
  `password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL, -- 密码（使用哈希算法加密存储）
  `email` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 管理员联系邮箱
  `reset_password` tinyint(1) DEFAULT '0', -- 密码重置标志（0-无需重置，1-需重置）
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 账户创建时间戳
  PRIMARY KEY (`id`), -- 主键约束（基于id的唯一性）
  UNIQUE KEY `username` (`username`) -- 唯一索引（确保用户名不重复）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户ID序列表：集中管理用户和管理员ID生成
CREATE TABLE if not exists `user_id_sequence` (
  `next_id` int NOT NULL AUTO_INCREMENT, -- 自增序列值（用于生成唯一ID）
  `user_type` enum('user','admin') COLLATE utf8mb4_unicode_ci NOT NULL, -- 用户类型（user-普通用户，admin-管理员）
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间戳
  PRIMARY KEY (`next_id`) -- 主键约束
) ENGINE=InnoDB AUTO_INCREMENT=1049 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影信息表：存储电影的核心元数据
CREATE TABLE if not exists `movies` (
  `id` int NOT NULL, -- 电影ID（主键，通常来自TMDB）
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL, -- 电影标题（本地化翻译后）
  `original_title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 电影原始标题（未翻译）
  `overview` text COLLATE utf8mb4_unicode_ci, -- 剧情简介
  `poster_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 海报图片URL路径
  `backdrop_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 背景图URL路径
  `release_date` date DEFAULT NULL, -- 上映日期
  `popularity` float DEFAULT '0', -- 热度指数（用于推荐算法）
  `vote_average` float DEFAULT '0', -- 平均评分（范围0-10）
  `vote_count` int DEFAULT '0', -- 评分总数
  `original_language` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 原始语言代码
  `genres` text COLLATE utf8mb4_unicode_ci, -- 电影类型（逗号分隔）
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 记录最后更新时间
  PRIMARY KEY (`id`), -- 主键约束
  KEY `idx_movies_popularity` (`popularity` DESC), -- 降序索引（加速按热度排序）
  KEY `idx_movies_vote_average` (`vote_average` DESC), -- 降序索引（加速按评分排序）
  KEY `idx_movies_release_date` (`release_date` DESC) -- 降序索引（加速按上映时间排序）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 人物信息表：存储演员、导演等人物信息
CREATE TABLE if not exists `persons` (
  `id` int NOT NULL, -- 人物ID（主键，通常来自TMDB）
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL, -- 人物姓名
  `gender` tinyint DEFAULT NULL, -- 性别（0-未知，1-女，2-男）
  `popularity` float DEFAULT '0', -- 人物热度指数
  PRIMARY KEY (`id`), -- 主键约束
  KEY `idx_persons_popularity` (`popularity` DESC) -- 降序索引（加速按热度排序）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影关键词表：存储与电影相关的关键词
CREATE TABLE if not exists `keywords` (
  `id` int NOT NULL, -- 关键词ID（主键）
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL, -- 关键词名称
  PRIMARY KEY (`id`) -- 主键约束
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 制作公司表：存储电影制作公司信息
CREATE TABLE if not exists `production_companies` (
  `id` int NOT NULL, -- 公司ID（主键）
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL, -- 公司名称
  `logo_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 公司Logo URL路径
  `origin_country` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 公司所在国家代码
  PRIMARY KEY (`id`) -- 主键约束
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 制作国家表：存储ISO 3166-1国家代码与名称
CREATE TABLE if not exists `production_countries` (
  `iso_3166_1` char(2) COLLATE utf8mb4_unicode_ci NOT NULL, -- 国家ISO代码（主键）
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL, -- 国家全称
  PRIMARY KEY (`iso_3166_1`) -- 主键约束
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 语言表：存储ISO 639-1语言代码与名称
CREATE TABLE if not exists `spoken_languages` (
  `iso_639_1` char(2) COLLATE utf8mb4_unicode_ci NOT NULL, -- 语言ISO代码（主键）
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL, -- 语言全称
  PRIMARY KEY (`iso_639_1`) -- 主键约束
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 爬虫状态表：监控电影数据抓取进度（无外键依赖）
CREATE TABLE if not exists `scraper_state` (
  `id` int NOT NULL AUTO_INCREMENT, -- 自增主键（唯一标识爬虫状态记录）
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'idle', -- 爬虫状态（idle-空闲，running-运行中，finished-完成，error-错误）
  `current` int NOT NULL DEFAULT 0, -- 当前处理进度值
  `message` text COLLATE utf8mb4_unicode_ci NULL, -- 状态详情或错误信息
  `last_page` int DEFAULT 1, -- 最后抓取的页码
  `total_pages` int DEFAULT 1, -- 总页数
  `last_movie_id` int DEFAULT 0, -- 最后处理的电影ID
  `processed_movies` int NOT NULL DEFAULT 0, -- 已处理电影总数
  `target_movies` int DEFAULT 50000, -- 目标抓取电影总数
  `start_time` datetime DEFAULT NULL, -- 任务开始时间
  `end_time` datetime DEFAULT NULL, -- 任务结束时间
  `endpoint` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'movie/top_rated', -- 当前使用的API端点
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 记录创建时间戳
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 记录最后更新时间戳
  PRIMARY KEY (`id`) -- 主键约束
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 第二层：依赖于基础表的表
-- ============================================

-- 用户评分表：记录用户对电影的评分及评论
CREATE TABLE if not exists `user_ratings` (
  `id` int NOT NULL AUTO_INCREMENT, -- 自增主键（唯一标识评分记录）
  `user_id` int NOT NULL, -- 用户ID（外键关联userinfo表）
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `rating` float NOT NULL, -- 用户评分（1-10分）
  `comment` text COLLATE utf8mb4_unicode_ci, -- 评分附带的文字评论
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 评分创建时间戳
  PRIMARY KEY (`id`), -- 主键约束
  UNIQUE KEY `unique_user_movie` (`user_id`,`movie_id`), -- 复合唯一约束（防止用户重复评分）
  KEY `movie_id` (`movie_id`), -- 普通索引（加速按电影查询）
  CONSTRAINT `user_ratings_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `userinfo` (`id`) ON DELETE CASCADE, -- 级联删除约束（用户删除时同步删除评分）
  CONSTRAINT `user_ratings_ibfk_2` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE, -- 级联删除约束（电影删除时同步删除评分）
  CONSTRAINT `user_ratings_chk_1` CHECK (((`rating` >= 0.5) and (`rating` <= 10))) -- 数据校验约束（确保评分范围合法）
) ENGINE=InnoDB AUTO_INCREMENT=12283 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影评论表：存储用户对电影的文本评论
CREATE TABLE if not exists `comments` (
  `id` int NOT NULL AUTO_INCREMENT, -- 自增主键（唯一标识评论）
  `user_id` int NOT NULL, -- 用户ID（外键关联userinfo表）
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL, -- 评论内容文本
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 评论创建时间戳
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 评论最后更新时间戳
  PRIMARY KEY (`id`), -- 主键约束
  KEY `user_id` (`user_id`), -- 普通索引（加速按用户查询）
  KEY `movie_id` (`movie_id`), -- 普通索引（加速按电影查询）
  CONSTRAINT `comments_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `userinfo` (`id`) ON DELETE CASCADE, -- 级联删除约束（用户删除时同步删除评论）
  CONSTRAINT `comments_ibfk_2` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE -- 级联删除约束（电影删除时同步删除评论）
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 推荐表：存储系统生成的个性化电影推荐
CREATE TABLE if not exists `recommendations` (
  `id` int NOT NULL AUTO_INCREMENT, -- 自增主键（唯一标识推荐记录）
  `user_id` int NOT NULL, -- 用户ID（外键关联userinfo表）
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `score` float NOT NULL, -- 推荐评分（值越高推荐优先级越高）
  `recommendation_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL, -- 推荐算法类型（如collaborative/content-based）
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 推荐生成时间戳
  PRIMARY KEY (`id`), -- 主键约束
  UNIQUE KEY `unique_user_movie_rec` (`user_id`,`movie_id`,`recommendation_type`), -- 复合唯一约束（防止重复推荐）
  KEY `movie_id` (`movie_id`), -- 普通索引（加速按电影查询）
  CONSTRAINT `recommendations_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `userinfo` (`id`) ON DELETE CASCADE, -- 级联删除约束（用户删除时同步删除推荐）
  CONSTRAINT `recommendations_ibfk_2` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE -- 级联删除约束（电影删除时同步删除推荐）
) ENGINE=InnoDB AUTO_INCREMENT=81 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户类型偏好表：记录用户对不同电影类型的偏好程度
CREATE TABLE if not exists `user_genre_preferences` (
  `user_id` int NOT NULL, -- 用户ID（外键关联userinfo表）
  `genre_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL, -- 类型名称（存储genres字符串中的单个类型）
  `preference_score` float DEFAULT '0', -- 偏好分数（值越高偏好越强）
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 最后更新时间戳
  PRIMARY KEY (`user_id`,`genre_name`), -- 复合主键（按用户和类型名称唯一）
  CONSTRAINT `user_genre_preferences_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `userinfo` (`id`) ON DELETE CASCADE -- 级联删除约束
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户观影历史表：记录用户观看电影的时间
CREATE TABLE if not exists `user_watch_history` (
  `id` int NOT NULL AUTO_INCREMENT, -- 自增主键（唯一标识观影记录）
  `user_id` int NOT NULL, -- 用户ID（外键关联userinfo表）
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `watched_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 观看时间戳
  PRIMARY KEY (`id`), -- 主键约束
  KEY `user_id` (`user_id`), -- 普通索引（加速按用户查询）
  KEY `movie_id` (`movie_id`), -- 普通索引（加速按电影查询）
  CONSTRAINT `user_watch_history_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `userinfo` (`id`) ON DELETE CASCADE, -- 级联删除约束（用户删除时同步删除历史）
  CONSTRAINT `user_watch_history_ibfk_2` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE -- 级联删除约束（电影删除时同步删除历史）
) ENGINE=InnoDB AUTO_INCREMENT=1002 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影演员表：记录电影中演员与角色的对应关系
CREATE TABLE if not exists `movie_cast` (
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `person_id` int NOT NULL, -- 演员ID（外键关联persons表）
  `role_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL, -- 演员饰演的角色名称
  `cast_order` int DEFAULT NULL, -- 演员在演员表中的排序
  PRIMARY KEY (`movie_id`,`person_id`,`role_name`(100)), -- 复合主键（限制同一电影中同一演员的同角色名记录）
  KEY `person_id` (`person_id`), -- 普通索引（加速按演员查询）
  CONSTRAINT `movie_cast_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE, -- 级联删除约束（电影删除时同步删除演员关联）
  CONSTRAINT `movie_cast_ibfk_2` FOREIGN KEY (`person_id`) REFERENCES `persons` (`id`) ON DELETE CASCADE -- 级联删除约束（演员删除时同步删除关联）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影工作人员表：记录导演、编剧等工作人员信息
CREATE TABLE if not exists `movie_crew` (
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `person_id` int NOT NULL, -- 工作人员ID（外键关联persons表）
  `job` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL, -- 职位名称（如导演、编剧）
  `department` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL, -- 所属部门（如摄影部、服装部）
  PRIMARY KEY (`movie_id`,`person_id`,`job`), -- 复合主键（确保同一职位不重复记录）
  KEY `person_id` (`person_id`) -- 普通索引（加速按人员查询）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影-关键词关联表：建立电影与关键词的多对多关系
CREATE TABLE if not exists `movie_keywords` (
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `keyword_id` int NOT NULL, -- 关键词ID（外键关联keywords表）
  PRIMARY KEY (`movie_id`,`keyword_id`), -- 复合主键（防止重复关联）
  KEY `keyword_id` (`keyword_id`), -- 普通索引（加速按关键词查询）
  CONSTRAINT `movie_keywords_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE, -- 级联删除约束（电影删除时同步解除关联）
  CONSTRAINT `movie_keywords_ibfk_2` FOREIGN KEY (`keyword_id`) REFERENCES `keywords` (`id`) ON DELETE CASCADE -- 级联删除约束（关键词删除时同步解除关联）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影-制作公司关联表：记录电影的制作公司信息
CREATE TABLE if not exists `movie_production_companies` (
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `company_id` int NOT NULL, -- 公司ID（外键关联production_companies表）
  PRIMARY KEY (`movie_id`,`company_id`), -- 复合主键（防止重复关联）
  KEY `company_id` (`company_id`), -- 普通索引（加速按公司查询）
  CONSTRAINT `movie_production_companies_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE, -- 级联删除约束（电影删除时同步解除关联）
  CONSTRAINT `movie_production_companies_ibfk_2` FOREIGN KEY (`company_id`) REFERENCES `production_companies` (`id`) ON DELETE CASCADE -- 级联删除约束（公司删除时同步解除关联）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影-制作国家关联表：记录电影的制作国家信息
CREATE TABLE if not exists `movie_production_countries` (
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `country_iso` char(2) COLLATE utf8mb4_unicode_ci NOT NULL, -- 国家ISO代码（外键关联production_countries表）
  PRIMARY KEY (`movie_id`,`country_iso`), -- 复合主键（防止重复关联）
  KEY `country_iso` (`country_iso`), -- 普通索引（加速按国家代码查询）
  CONSTRAINT `movie_production_countries_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE, -- 级联删除约束（电影删除时同步解除关联）
  CONSTRAINT `movie_production_countries_ibfk_2` FOREIGN KEY (`country_iso`) REFERENCES `production_countries` (`iso_3166_1`) ON DELETE CASCADE -- 级联删除约束（国家删除时同步解除关联）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 电影-语言关联表：记录电影使用的对白语言
CREATE TABLE if not exists `movie_spoken_languages` (
  `movie_id` int NOT NULL, -- 电影ID（外键关联movies表）
  `language_iso` char(2) COLLATE utf8mb4_unicode_ci NOT NULL, -- 语言ISO代码（外键关联spoken_languages表）
  PRIMARY KEY (`movie_id`,`language_iso`), -- 复合主键（防止重复关联）
  KEY `language_iso` (`language_iso`), -- 普通索引（加速按语言代码查询）
  CONSTRAINT `movie_spoken_languages_ibfk_1` FOREIGN KEY (`movie_id`) REFERENCES `movies` (`id`) ON DELETE CASCADE, -- 级联删除约束（电影删除时同步解除关联）
  CONSTRAINT `movie_spoken_languages_ibfk_2` FOREIGN KEY (`language_iso`) REFERENCES `spoken_languages` (`iso_639_1`) ON DELETE CASCADE -- 级联删除约束（语言删除时同步解除关联）
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 第三层：依赖于第二层表的表
-- ============================================

-- 评论点赞表：记录用户对评论的点赞行为
CREATE TABLE if not exists `comment_likes` (
  `id` int NOT NULL AUTO_INCREMENT, -- 自增主键（唯一标识点赞记录）
  `user_id` int NOT NULL, -- 用户ID（外键关联userinfo表）
  `rating_id` int NOT NULL, -- 评分评论ID（外键关联user_ratings表）
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 点赞时间戳
  PRIMARY KEY (`id`), -- 主键约束
  UNIQUE KEY `user_rating` (`user_id`,`rating_id`), -- 复合唯一索引（防止用户重复点赞）
  KEY `rating_id` (`rating_id`), -- 普通索引（加速按评分评论查询）
  CONSTRAINT `comment_likes_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `userinfo` (`id`) ON DELETE CASCADE, -- 级联删除约束（用户删除时同步删除相关点赞）
  CONSTRAINT `comment_likes_ibfk_2` FOREIGN KEY (`rating_id`) REFERENCES `user_ratings` (`id`) ON DELETE CASCADE -- 级联删除约束（评论删除时同步删除相关点赞）
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 评论回复表：存储用户对评论的回复内容
CREATE TABLE if not exists `comment_replies` (
  `id` int NOT NULL AUTO_INCREMENT, -- 自增主键（唯一标识回复记录）
  `rating_id` int NOT NULL, -- 被回复的评分评论ID（外键关联user_ratings表）
  `user_id` int NOT NULL, -- 回复用户ID（外键关联userinfo表）
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL, -- 回复内容文本
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP, -- 回复创建时间戳
  PRIMARY KEY (`id`), -- 主键约束
  KEY `rating_id` (`rating_id`), -- 普通索引（加速按评论查询）
  KEY `user_id` (`user_id`), -- 普通索引（加速按用户查询）
  CONSTRAINT `comment_replies_ibfk_1` FOREIGN KEY (`rating_id`) REFERENCES `user_ratings` (`id`) ON DELETE CASCADE, -- 级联删除约束（评论删除时同步删除回复）
  CONSTRAINT `comment_replies_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `userinfo` (`id`) ON DELETE CASCADE -- 级联删除约束（用户删除时同步删除回复）
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- ============================================
-- 创建存储过程
-- ============================================

-- 删除已存在的存储过程（如果存在）
DROP PROCEDURE IF EXISTS get_next_user_id;

-- 创建获取下一个用户ID的存储过程
DELIMITER $$

CREATE PROCEDURE get_next_user_id(
    OUT next_id INT,
    IN user_type_param VARCHAR(10)
)
BEGIN
    -- 在user_id_sequence表中插入一条记录以获取自增ID
    INSERT INTO user_id_sequence (user_type) VALUES (user_type_param);
    
    -- 获取刚刚生成的自增ID
    SET next_id = LAST_INSERT_ID();
    
    -- 可选：删除刚刚插入的记录（如果不需要保留历史记录）
    -- DELETE FROM user_id_sequence WHERE next_id = next_id;
END$$

DELIMITER ;

-- 显示创建成功的消息
SELECT 'Stored procedure get_next_user_id created successfully!' AS Status;

