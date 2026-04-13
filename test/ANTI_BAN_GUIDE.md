# 反封锁指南 - 防止IP被封锁

## 概述

本指南详细介绍如何配置和使用反封锁功能，防止在频繁下载和检索时被网站封锁IP。

## 主要风险

### 1. 下载时的风险
- **频繁请求**: 短时间内大量下载请求
- **相同User-Agent**: 使用固定的User-Agent容易被识别
- **规律性请求**: 固定间隔的请求模式容易被检测

### 2. 检索时的风险
- **API限速**: 超过API的速率限制
- **429错误**: 服务器返回"Too Many Requests"
- **IP封锁**: 临时或永久封锁IP地址

## 反封锁机制

### 1. User-Agent轮换

**功能**: 自动轮换不同的User-Agent，模拟不同浏览器

**支持的浏览器**:
- Chrome (Windows, macOS, Linux)
- Firefox (Windows, macOS, Linux)
- Safari (macOS)
- Edge (Windows)

**配置**:
```yaml
runtime:
  anti_ban:
    rotate_user_agent: true  # 启用User-Agent轮换
```

### 2. 智能延迟

**功能**: 根据请求频率动态调整延迟时间

**延迟策略**:
- **低负载**: 1.5-3秒延迟
- **中等负载**: 3-5秒延迟
- **高负载**: 5-8秒延迟
- **超限**: 8-16秒延迟

**配置**:
```yaml
runtime:
  anti_ban:
    min_delay: 1.5  # 最小延迟（秒）
    max_delay: 8.0  # 最大延迟（秒）
    max_requests_per_minute: 15  # 每分钟最大请求数
```

### 3. 指数退避

**功能**: 失败后自动增加等待时间

**退避策略**:
- 第1次失败: 等待2秒
- 第2次失败: 等待4秒
- 第3次失败: 等待8秒
- 第4次失败: 等待16秒
- 第5次失败: 等待32秒

**配置**:
```yaml
runtime:
  download_retries: 8  # 最大重试次数
```

### 4. 来源封锁检测

**功能**: 检测并临时封锁失败率高的来源

**封锁条件**:
- 连续失败次数超过阈值
- 收到429状态码
- 收到403状态码

**配置**:
```yaml
runtime:
  anti_ban:
    ban_threshold: 3  # 失败次数阈值
    ban_duration: 600  # 封锁持续时间（秒）
```

### 5. 请求头伪装

**功能**: 生成真实的浏览器请求头

**包含的头部**:
- User-Agent (随机)
- Accept (随机)
- Accept-Language (随机)
- Accept-Encoding
- Connection
- Referer (基于URL)
- DNT (随机)
- Sec-Fetch-* (随机)

**配置**:
```yaml
runtime:
  anti_ban:
    rotate_user_agent: true  # 启用请求头伪装
```

### 6. 代理支持

**功能**: 通过代理服务器发送请求

**代理格式**:
```json
[
  {
    "http": "http://proxy1:8080",
    "https": "https://proxy1:8080"
  },
  {
    "http": "http://proxy2:8080",
    "https": "https://proxy2:8080"
  }
]
```

**配置**:
```yaml
runtime:
  anti_ban:
    use_proxy: true  # 启用代理
    proxy_file: "configs/proxies.json"  # 代理配置文件
```

## 配置文件详解

### 完整配置示例

```yaml
runtime:
  # 反封锁配置
  anti_ban:
    # 延迟配置
    min_delay: 1.5  # 最小延迟（秒）
    max_delay: 8.0  # 最大延迟（秒）
    
    # 请求频率限制
    max_requests_per_minute: 15  # 每分钟最大请求数
    
    # 封锁配置
    ban_threshold: 3  # 失败次数阈值
    ban_duration: 600  # 封锁持续时间（秒）
    
    # 代理配置
    use_proxy: false  # 是否使用代理
    # proxy_file: "configs/proxies.json"  # 代理配置文件路径
    
    # 请求头配置
    rotate_user_agent: true  # 是否轮换User-Agent
    add_random_delay: true  # 是否添加随机延迟
```

### 配置参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `min_delay` | float | 1.5 | 最小延迟时间（秒） |
| `max_delay` | float | 8.0 | 最大延迟时间（秒） |
| `max_requests_per_minute` | int | 15 | 每分钟最大请求数 |
| `ban_threshold` | int | 3 | 失败次数阈值 |
| `ban_duration` | int | 600 | 封锁持续时间（秒） |
| `use_proxy` | bool | false | 是否使用代理 |
| `proxy_file` | string | null | 代理配置文件路径 |
| `rotate_user_agent` | bool | true | 是否轮换User-Agent |
| `add_random_delay` | bool | true | 是否添加随机延迟 |

## 使用方法

### 1. 启用反封锁功能

在配置文件中添加反封锁配置：

```yaml
runtime:
  anti_ban:
    min_delay: 1.5
    max_delay: 8.0
    max_requests_per_minute: 15
    rotate_user_agent: true
    add_random_delay: true
```

### 2. 配置代理（可选）

如果需要使用代理，创建代理配置文件：

**configs/proxies.json**:
```json
[
  {
    "http": "http://proxy1:8080",
    "https": "https://proxy1:8080"
  },
  {
    "http": "http://proxy2:8080",
    "https": "https://proxy2:8080"
  }
]
```

然后在配置文件中指定：

```yaml
runtime:
  anti_ban:
    use_proxy: true
    proxy_file: "configs/proxies.json"
```

### 3. 调整参数

根据实际情况调整参数：

**保守配置**（更安全，但更慢）:
```yaml
runtime:
  anti_ban:
    min_delay: 3.0
    max_delay: 15.0
    max_requests_per_minute: 8
    ban_threshold: 2
    ban_duration: 900
```

**激进配置**（更快，但风险更高）:
```yaml
runtime:
  anti_ban:
    min_delay: 0.5
    max_delay: 3.0
    max_requests_per_minute: 30
    ban_threshold: 5
    ban_duration: 300
```

## 监控和调试

### 1. 查看反封锁统计

程序运行时会输出反封锁统计信息：

```
[AntiBan] Source 'unpaywall' banned for 600s after 3 failures (reason: rate_limited)
[AntiBan] Configuration updated: {'min_delay': 1.5, 'max_delay': 8.0, ...}
```

### 2. 检查日志

查看详细的日志输出：

```
2026-04-12 18:40:44 [INFO] etl_ensemble.anti_ban: [AntiBan] Anti-ban manager initialized
2026-04-12 18:40:44 [DEBUG] etl_ensemble.downloader:   [Download] Request blocked or failed (attempt 1/5)
```

### 3. 监控失败率

如果看到大量"request_blocked"或"source_banned"错误，说明反封锁机制正在工作。

## 最佳实践

### 1. 请求频率控制

- **API请求**: 每分钟不超过20次
- **PDF下载**: 每分钟不超过15次
- **总请求**: 每分钟不超过30次

### 2. 延迟设置

- **最小延迟**: 至少1秒
- **最大延迟**: 根据网站限制调整
- **随机抖动**: 添加±0.5秒的随机延迟

### 3. 错误处理

- **429错误**: 立即停止，等待指定时间
- **403错误**: 增加延迟，继续尝试
- **连接错误**: 使用指数退避

### 4. 代理使用

- **免费代理**: 不稳定，仅用于测试
- **付费代理**: 稳定，推荐用于生产
- **住宅代理**: 最佳效果，但成本高

## 故障排除

### 1. 频繁被封锁

**症状**: 大量"source_banned"错误

**解决方案**:
- 增加`min_delay`和`max_delay`
- 减少`max_requests_per_minute`
- 降低`ban_threshold`
- 使用代理

### 2. 下载速度慢

**症状**: 下载时间过长

**解决方案**:
- 适当减少延迟时间
- 增加并发数
- 使用更快的代理

### 3. 代理不工作

**症状**: 代理连接失败

**解决方案**:
- 检查代理格式是否正确
- 验证代理是否可用
- 尝试其他代理

## 注意事项

### 1. 法律合规

- 遵守网站的robots.txt
- 尊重版权和知识产权
- 仅用于学术研究

### 2. 道德使用

- 不要过度请求
- 不要绕过付费墙
- 尊重网站资源

### 3. 技术限制

- 某些网站有高级反爬虫
- 代理可能不稳定
- 延迟会影响总时间

## 联系支持

如有问题或建议，请联系：
- 邮箱: wangqi@ahut.edu.cn
- 项目地址: https://github.com/your-repo/nfp-pdf-to-db

---

**最后更新**: 2026-04-12
**版本**: 1.0