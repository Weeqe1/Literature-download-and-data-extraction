"""反封锁工具模块 - 防止IP被封锁

提供以下功能：
1. User-Agent轮换
2. 随机延迟
3. 代理支持
4. 会话管理
5. 智能退避策略
6. 请求头伪装
"""

import os
import time
import random
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-Agent 池
# ---------------------------------------------------------------------------
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

# ---------------------------------------------------------------------------
# Accept 头部池
# ---------------------------------------------------------------------------
ACCEPT_HEADERS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "application/json, text/plain, */*",
    "application/pdf,*/*",
]

# ---------------------------------------------------------------------------
# Accept-Language 头部池
# ---------------------------------------------------------------------------
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "zh-CN,zh;q=0.9,en;q=0.8",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,de;q=0.8",
]

# ---------------------------------------------------------------------------
# 全局状态管理
# ---------------------------------------------------------------------------
class AntiBanManager:
    """反封锁管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # 请求历史记录
        self._request_history: Dict[str, List[float]] = defaultdict(list)
        
        # 封锁状态
        self._banned_sources: Dict[str, datetime] = {}
        
        # 失败计数
        self._failure_counts: Dict[str, int] = defaultdict(int)
        
        # 代理池
        self._proxies: List[Dict[str, str]] = []
        self._current_proxy_index = 0
        
        # 配置 - 优化后的反封锁参数
        self.config = {
            'min_delay': 2.0,  # 最小延迟（秒）- 从1.0增加到2.0
            'max_delay': 10.0,  # 最大延迟（秒）- 从5.0增加到10.0
            'max_requests_per_minute': 10,  # 每分钟最大请求数 - 从20减少到10
            'ban_threshold': 3,  # 失败次数阈值 - 从5减少到3，更快触发封禁
            'ban_duration': 600,  # 封锁持续时间（秒）- 从300增加到600
            'use_proxy': False,  # 是否使用代理
            'rotate_user_agent': True,  # 是否轮换User-Agent
            'add_random_delay': True,  # 是否添加随机延迟
            # 新增：针对不同来源的特殊配置
            'source_specific_delays': {
                'direct': 5.0,  # 直接下载增加延迟
                'unpaywall': 3.0,  # Unpaywall增加延迟
                'scihub': 2.0,  # Sci-Hub保持较低延迟
                'pmc': 2.0,  # PMC保持较低延迟
            },
            # 新增：超时设置
            'timeout_settings': {
                'default': 90,  # 默认超时从60增加到90
                'ssrn': 120,  # SSRN网站超时120秒
                'mdpi': 90,  # MDPI网站超时90秒
            },
        }
        
        # 线程锁
        self._history_lock = threading.Lock()
        self._ban_lock = threading.Lock()
        
        logger.info("[AntiBan] Anti-ban manager initialized")
    
    def get_random_user_agent(self) -> str:
        """获取随机User-Agent"""
        return random.choice(USER_AGENTS)
    
    def get_random_accept_header(self) -> str:
        """获取随机Accept头部"""
        return random.choice(ACCEPT_HEADERS)
    
    def get_random_accept_language(self) -> str:
        """获取随机Accept-Language头部"""
        return random.choice(ACCEPT_LANGUAGES)
    
    def get_headers(self, url: str = None, referer: str = None) -> Dict[str, str]:
        """获取伪装的请求头"""
        headers = {
            'User-Agent': self.get_random_user_agent(),
            'Accept': self.get_random_accept_header(),
            'Accept-Language': self.get_random_accept_language(),
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        # 添加Referer
        if referer:
            headers['Referer'] = referer
        elif url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
            except:
                pass
        
        # 随机添加其他头部
        if random.random() < 0.3:
            headers['DNT'] = '1'  # Do Not Track
        
        if random.random() < 0.2:
            headers['Sec-Fetch-Dest'] = 'document'
            headers['Sec-Fetch-Mode'] = 'navigate'
            headers['Sec-Fetch-Site'] = 'none'
            headers['Sec-Fetch-User'] = '?1'
        
        return headers
    
    def add_proxies(self, proxies: List[Dict[str, str]]):
        """添加代理列表"""
        self._proxies.extend(proxies)
        logger.info("[AntiBan] Added %d proxies, total: %d", len(proxies), len(self._proxies))
    
    def load_proxies_from_file(self, filepath: str):
        """从文件加载代理列表"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                proxies = json.load(f)
            self.add_proxies(proxies)
        except Exception as e:
            logger.warning("[AntiBan] Failed to load proxies from %s: %s", filepath, e)
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """获取下一个代理"""
        if not self._proxies or not self.config['use_proxy']:
            return None
        
        proxy = self._proxies[self._current_proxy_index % len(self._proxies)]
        self._current_proxy_index += 1
        return proxy
    
    def is_source_banned(self, source: str) -> bool:
        """检查来源是否被封锁"""
        with self._ban_lock:
            if source in self._banned_sources:
                ban_until = self._banned_sources[source]
                if datetime.now() < ban_until:
                    return True
                else:
                    # 封锁已过期，移除
                    del self._banned_sources[source]
                    self._failure_counts[source] = 0
            return False
    
    def record_failure(self, source: str, reason: str = "unknown"):
        """记录失败"""
        with self._ban_lock:
            self._failure_counts[source] += 1
            
            # 检查是否达到封锁阈值
            if self._failure_counts[source] >= self.config['ban_threshold']:
                ban_duration = self.config['ban_duration']
                self._banned_sources[source] = datetime.now() + timedelta(seconds=ban_duration)
                logger.warning(
                    "[AntiBan] Source '%s' banned for %ds after %d failures (reason: %s)",
                    source, ban_duration, self._failure_counts[source], reason
                )
    
    def record_success(self, source: str):
        """记录成功"""
        with self._ban_lock:
            # 重置失败计数
            self._failure_counts[source] = 0
    
    def get_smart_delay(self, source: str) -> float:
        """获取智能延迟时间 - 支持针对不同来源的特殊延迟配置"""
        with self._history_lock:
            now = time.time()
            recent_requests = self._request_history[source]
            
            # 清理超过1分钟的记录
            recent_requests = [t for t in recent_requests if now - t < 60]
            self._request_history[source] = recent_requests
            
            # 计算最近1分钟的请求数
            requests_per_minute = len(recent_requests)
            
            # 获取针对该来源的基础延迟
            source_delays = self.config.get('source_specific_delays', {})
            base_min_delay = source_delays.get(source, self.config['min_delay'])
            base_max_delay = max(base_min_delay * 2, self.config['max_delay'])
            
            # 根据请求数调整延迟
            if requests_per_minute >= self.config['max_requests_per_minute']:
                # 超过限制，增加延迟
                delay = base_max_delay * 2
            elif requests_per_minute >= self.config['max_requests_per_minute'] * 0.8:
                # 接近限制，使用最大延迟
                delay = base_max_delay
            elif requests_per_minute >= self.config['max_requests_per_minute'] * 0.5:
                # 中等负载，使用中间值
                delay = (base_min_delay + base_max_delay) / 2
            else:
                # 低负载，使用最小延迟
                delay = base_min_delay
            
            # 添加随机抖动（增加抖动范围以避免规律性）
            jitter = random.uniform(-1.0, 1.0)
            delay = max(1.0, delay + jitter)  # 最小延迟增加到1秒
            
            return delay
    
    def wait_for_source(self, source: str):
        """等待（应用智能延迟）"""
        if not self.config['add_random_delay']:
            return
        
        delay = self.get_smart_delay(source)
        
        # 检查是否被封锁
        if self.is_source_banned(source):
            ban_until = self._banned_sources[source]
            wait_time = (ban_until - datetime.now()).total_seconds()
            if wait_time > 0:
                logger.info("[AntiBan] Source '%s' is banned, waiting %.1fs", source, wait_time)
                time.sleep(wait_time)
        
        # 记录请求时间
        with self._history_lock:
            self._request_history[source].append(time.time())
        
        # 等待
        if delay > 0:
            time.sleep(delay)
    
    def get_session(self, source: str = "default") -> requests.Session:
        """获取配置好的会话"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 设置默认头部
        session.headers.update(self.get_headers())
        
        # 设置代理
        proxy = self.get_proxy()
        if proxy:
            session.proxies.update(proxy)
        
        return session
    
    def make_request(
        self,
        method: str,
        url: str,
        source: str = "default",
        timeout: int = 30,
        **kwargs
    ) -> Optional[requests.Response]:
        """发送请求（带反封锁保护）"""
        
        # 检查是否被封锁
        if self.is_source_banned(source):
            logger.warning("[AntiBan] Source '%s' is banned, skipping request", source)
            return None
        
        # 等待
        self.wait_for_source(source)
        
        # 获取会话
        session = self.get_session(source)
        
        # 更新头部
        headers = kwargs.pop('headers', {})
        headers.update(self.get_headers(url))
        
        # 设置代理
        proxy = self.get_proxy()
        if proxy:
            kwargs['proxies'] = proxy
        
        try:
            # 发送请求
            response = session.request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                **kwargs
            )
            
            # 检查响应状态
            if response.status_code == 429:
                # 被限速
                self.record_failure(source, "rate_limited")
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning("[AntiBan] Rate limited on %s, waiting %ds", source, retry_after)
                time.sleep(retry_after)
                return None
            
            if response.status_code == 403:
                # 被禁止
                self.record_failure(source, "forbidden")
                logger.warning("[AntiBan] Forbidden (403) on %s", source)
                return None
            
            if response.status_code >= 400:
                # 其他错误
                self.record_failure(source, f"http_{response.status_code}")
                return None
            
            # 成功
            self.record_success(source)
            return response
            
        except requests.exceptions.Timeout:
            self.record_failure(source, "timeout")
            logger.warning("[AntiBan] Timeout on %s", source)
            return None
            
        except requests.exceptions.ConnectionError:
            self.record_failure(source, "connection_error")
            logger.warning("[AntiBan] Connection error on %s", source)
            return None
            
        except Exception as e:
            self.record_failure(source, f"exception: {str(e)[:50]}")
            logger.warning("[AntiBan] Exception on %s: %s", source, e)
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._ban_lock, self._history_lock:
            return {
                'banned_sources': dict(self._banned_sources),
                'failure_counts': dict(self._failure_counts),
                'total_proxies': len(self._proxies),
                'recent_requests': {
                    source: len(requests)
                    for source, requests in self._request_history.items()
                },
            }


# ---------------------------------------------------------------------------
# 全局实例
# ---------------------------------------------------------------------------
_anti_ban_manager = None

def get_anti_ban_manager() -> AntiBanManager:
    """获取反封锁管理器实例"""
    global _anti_ban_manager
    if _anti_ban_manager is None:
        _anti_ban_manager = AntiBanManager()
    return _anti_ban_manager


def configure_anti_ban(config: Dict[str, Any]):
    """配置反封锁管理器"""
    manager = get_anti_ban_manager()
    manager.config.update(config)
    logger.info("[AntiBan] Configuration updated: %s", config)


def get_safe_headers(url: str = None, referer: str = None) -> Dict[str, str]:
    """获取安全的请求头"""
    manager = get_anti_ban_manager()
    return manager.get_headers(url, referer)


def safe_request(
    method: str,
    url: str,
    source: str = "default",
    timeout: int = 30,
    **kwargs
) -> Optional[requests.Response]:
    """发送安全的请求（带反封锁保护）"""
    manager = get_anti_ban_manager()
    return manager.make_request(method, url, source, timeout, **kwargs)


def wait_for_source(source: str):
    """等待指定来源"""
    manager = get_anti_ban_manager()
    manager.wait_for_source(source)