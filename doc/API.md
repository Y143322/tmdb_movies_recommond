# API 文档 (API Documentation)

本文档详细说明了电影推荐系统的 RESTful API 接口。

## 📋 目录

- [基本信息](#基本信息)
- [认证](#认证)
- [错误处理](#错误处理)
- [API 端点](#api-端点)
  - [认证相关](#认证相关)
  - [电影相关](#电影相关)
  - [用户相关](#用户相关)
  - [推荐相关](#推荐相关)
  - [评分评论](#评分评论)

---

## 基本信息

### Base URL

```
开发环境: http://localhost:5000/api
生产环境: https://your-domain.com/api
```

### 响应格式

所有 API 响应均为 JSON 格式：

```json
{
  "code": 200,
  "success": true,
  "message": "操作成功",
  "data": {
    // 具体数据
  }
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

---

## 认证

### JWT Token 认证

大多数 API 需要 JWT Token 认证。

#### 获取 Token

登录后会返回 access_token，在后续请求的 Header 中携带：

```http
Authorization: Bearer YOUR_ACCESS_TOKEN
```

#### Token 过期

- Access Token: 24小时
- Refresh Token: 30天

---

## 错误处理

### 错误响应格式

```json
{
  "code": 400,
  "success": false,
  "message": "错误描述",
  "error": "详细错误信息"
}
```

### 常见错误

```json
// 未授权
{
  "code": 401,
  "success": false,
  "message": "请先登录"
}

// 参数错误
{
  "code": 400,
  "success": false,
  "message": "参数错误",
  "error": "缺少必需参数: user_id"
}

// 资源不存在
{
  "code": 404,
  "success": false,
  "message": "电影不存在"
}
```

---

## API 端点

### 认证相关

#### 1. 用户注册

```http
POST /api/auth/register
```

**请求体**

```json
{
  "username": "user1",
  "password": "password123",
  "email": "user@example.com"
}
```

**响应**

```json
{
  "code": 201,
  "success": true,
  "message": "注册成功",
  "data": {
    "user_id": 1,
    "username": "user1"
  }
}
```

---

#### 2. 用户登录

```http
POST /api/auth/login
```

**请求体**

```json
{
  "username": "user1",
  "password": "password123"
}
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "message": "登录成功",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "user": {
      "id": 1,
      "username": "user1",
      "email": "user@example.com"
    }
  }
}
```

---

#### 3. 刷新 Token

```http
POST /api/auth/refresh
```

**Header**

```
Authorization: Bearer REFRESH_TOKEN
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "access_token": "new_access_token"
  }
}
```

---

#### 4. 登出

```http
POST /api/auth/logout
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "message": "登出成功"
}
```

---

### 电影相关

#### 1. 获取电影列表

```http
GET /api/movies
```

**查询参数**

| 参数 | 类型 | 必需 | 说明 | 默认值 |
|------|------|------|------|--------|
| page | int | 否 | 页码 | 1 |
| pageSize | int | 否 | 每页数量 (1-50) | 10 |
| sort | string | 否 | 排序方式: hot/time/rating | hot |
| genre | string | 否 | 电影类型过滤 | - |
| year | int | 否 | 年份过滤 | - |
| keyword | string | 否 | 关键词搜索 | - |

**示例请求**

```http
GET /api/movies?page=1&pageSize=20&sort=rating&genre=Action
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "message": "获取成功",
  "data": {
    "list": [
      {
        "id": 1,
        "title": "肖申克的救赎",
        "originalTitle": "The Shawshank Redemption",
        "overview": "电影简介...",
        "posterPath": "https://image.tmdb.org/t/p/w500/xxx.jpg",
        "backdropPath": "https://image.tmdb.org/t/p/original/xxx.jpg",
        "releaseDate": "1994-09-23",
        "voteAverage": 9.3,
        "voteCount": 26000,
        "genres": "Drama,Crime",
        "popularity": 85.5
      }
    ],
    "total": 1000,
    "page": 1,
    "pageSize": 20,
    "totalPages": 50
  }
}
```

---

#### 2. 获取电影详情

```http
GET /api/movies/{movie_id}
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| movie_id | int | 电影ID |

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "id": 1,
    "title": "肖申克的救赎",
    "originalTitle": "The Shawshank Redemption",
    "overview": "电影简介...",
    "posterPath": "https://...",
    "backdropPath": "https://...",
    "releaseDate": "1994-09-23",
    "runtime": 142,
    "budget": 25000000,
    "revenue": 28341469,
    "voteAverage": 9.3,
    "voteCount": 26000,
    "genres": ["Drama", "Crime"],
    "director": "Frank Darabont",
    "cast": [
      {
        "id": 1,
        "name": "Tim Robbins",
        "character": "Andy Dufresne",
        "profilePath": "https://..."
      }
    ],
    "keywords": ["prison", "friendship", "hope"],
    "similarMovies": [12, 34, 56]
  }
}
```

---

#### 3. 搜索电影

```http
GET /api/movies/search
```

**查询参数**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词 |
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页数量 |

**示例请求**

```http
GET /api/movies/search?q=肖申克&page=1&pageSize=10
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "list": [...],
    "total": 5,
    "page": 1,
    "pageSize": 10
  }
}
```

---

### 用户相关

#### 1. 获取用户信息

```http
GET /api/user/profile
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "id": 1,
    "username": "user1",
    "email": "user@example.com",
    "createdAt": "2024-01-01T00:00:00",
    "stats": {
      "ratingsCount": 150,
      "reviewsCount": 45,
      "watchlistCount": 30
    }
  }
}
```

---

#### 2. 更新用户信息

```http
PUT /api/user/profile
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**请求体**

```json
{
  "email": "newemail@example.com",
  "password": "newpassword123"
}
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "message": "更新成功"
}
```

---

#### 3. 获取用户评分历史

```http
GET /api/user/ratings
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**查询参数**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页数量 |

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "list": [
      {
        "id": 1,
        "movieId": 100,
        "movieTitle": "肖申克的救赎",
        "rating": 9,
        "comment": "非常好看！",
        "createdAt": "2024-01-15T10:30:00"
      }
    ],
    "total": 150,
    "page": 1,
    "pageSize": 20
  }
}
```

---

### 推荐相关

#### 1. 获取个性化推荐

```http
GET /api/recommendations
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**查询参数**

| 参数 | 类型 | 必需 | 说明 | 默认值 |
|------|------|------|------|--------|
| n | int | 否 | 推荐数量 | 10 |
| algorithm | string | 否 | 算法类型: cf/content/hybrid | hybrid |

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "recommendations": [
      {
        "id": 123,
        "title": "电影名称",
        "posterPath": "https://...",
        "score": 8.5,
        "reason": "因为您喜欢《肖申克的救赎》"
      }
    ],
    "algorithm": "hybrid",
    "generatedAt": "2024-01-15T10:30:00"
  }
}
```

---

#### 2. 获取相似电影

```http
GET /api/movies/{movie_id}/similar
```

**路径参数**

| 参数 | 类型 | 说明 |
|------|------|------|
| movie_id | int | 电影ID |

**查询参数**

| 参数 | 类型 | 必需 | 说明 | 默认值 |
|------|------|------|------|--------|
| n | int | 否 | 推荐数量 | 5 |

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "movies": [
      {
        "id": 456,
        "title": "绿里奇迹",
        "posterPath": "https://...",
        "similarity": 0.85,
        "reason": {
          "type": "director",
          "reason": "相同导演：Frank Darabont"
        }
      }
    ]
  }
}
```

---

#### 3. 刷新推荐

```http
POST /api/recommendations/refresh
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**请求体**

```json
{
  "currentMovies": [1, 2, 3, 4, 5]
}
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "movies": [...]
  }
}
```

---

### 评分评论

#### 1. 提交评分

```http
POST /api/movies/{movie_id}/rate
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**请求体**

```json
{
  "rating": 9,
  "comment": "非常精彩的电影！"
}
```

**响应**

```json
{
  "code": 201,
  "success": true,
  "message": "评分成功",
  "data": {
    "ratingId": 123
  }
}
```

---

#### 2. 获取电影评论

```http
GET /api/movies/{movie_id}/reviews
```

**查询参数**

| 参数 | 类型 | 必需 | 说明 | 默认值 |
|------|------|------|------|--------|
| page | int | 否 | 页码 | 1 |
| pageSize | int | 否 | 每页数量 | 10 |
| sort | string | 否 | 排序: time/rating/likes | time |

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "list": [
      {
        "id": 1,
        "userId": 10,
        "username": "user1",
        "rating": 9,
        "comment": "非常好看！",
        "likesCount": 45,
        "isLiked": false,
        "createdAt": "2024-01-15T10:30:00",
        "replies": [
          {
            "id": 1,
            "userId": 20,
            "username": "user2",
            "content": "我也觉得！",
            "createdAt": "2024-01-15T11:00:00"
          }
        ]
      }
    ],
    "total": 1500,
    "page": 1,
    "pageSize": 10
  }
}
```

---

#### 3. 点赞评论

```http
POST /api/reviews/{review_id}/like
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "data": {
    "liked": true,
    "likeCount": 46
  }
}
```

---

#### 4. 回复评论

```http
POST /api/reviews/{review_id}/reply
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**请求体**

```json
{
  "content": "我也这么认为！"
}
```

**响应**

```json
{
  "code": 201,
  "success": true,
  "message": "回复成功",
  "data": {
    "replyId": 123
  }
}
```

---

#### 5. 删除评论

```http
DELETE /api/reviews/{review_id}
```

**Header**

```
Authorization: Bearer ACCESS_TOKEN
```

**响应**

```json
{
  "code": 200,
  "success": true,
  "message": "删除成功"
}
```

---

## 请求示例

### cURL

```bash
# 登录
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "password123"}'

# 获取电影列表
curl http://localhost:5000/api/movies?page=1&pageSize=10

# 获取推荐（需要认证）
curl http://localhost:5000/api/recommendations \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 评分电影
curl -X POST http://localhost:5000/api/movies/123/rate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{"rating": 9, "comment": "很棒的电影！"}'
```

### Python (requests)

```python
import requests

BASE_URL = "http://localhost:5000/api"

# 登录
response = requests.post(
    f"{BASE_URL}/auth/login",
    json={"username": "user1", "password": "password123"}
)
token = response.json()["data"]["access_token"]

# 获取推荐
headers = {"Authorization": f"Bearer {token}"}
response = requests.get(f"{BASE_URL}/recommendations", headers=headers)
recommendations = response.json()["data"]["recommendations"]

print(f"推荐了 {len(recommendations)} 部电影")
```

### JavaScript (Axios)

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:5000/api';

// 登录
const login = async () => {
  const response = await axios.post(`${BASE_URL}/auth/login`, {
    username: 'user1',
    password: 'password123'
  });
  return response.data.data.access_token;
};

// 获取推荐
const getRecommendations = async (token) => {
  const response = await axios.get(`${BASE_URL}/recommendations`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.data.data.recommendations;
};

// 使用
(async () => {
  const token = await login();
  const recommendations = await getRecommendations(token);
  console.log(`推荐了 ${recommendations.length} 部电影`);
})();
```

---

## 速率限制

为了保护 API 不被滥用，我们实施了速率限制：

- **未认证**: 每分钟 30 次请求
- **已认证**: 每分钟 100 次请求

超过限制将返回 429 Too Many Requests。

**响应头**

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642345678
```

---

## 版本控制

当前 API 版本: **v1**

未来可能会添加新版本（如 `/api/v2/...`），旧版本会保持兼容一段时间。

---

## 更新日志

### v1.0.0 (2024-01-15)
- 初始版本发布
- 实现基础的认证、电影、推荐功能

### v1.1.0 (计划中)
- 添加观影历史记录
- 添加收藏夹功能
- 优化推荐算法

---

## 联系支持

如有问题，请：
- 查看 [GitHub Issues](https://github.com/Y143322/tmdb_movies_recommond/issues)
- 发送邮件至: your.email@example.com

---

**注意**: 本文档会随着 API 的更新而更新，请定期查看最新版本。
