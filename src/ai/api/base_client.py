# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 基础API客户端
提供统一的错误处理、重试机制、超时控制
"""

import time
import requests
from typing import Dict, Any, Optional, Callable
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..log.logger import get_logger


class APIError(Exception):
    """API调用错误基类"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)


class APITimeoutError(APIError):
    """API超时错误"""
    pass


class APIRateLimitError(APIError):
    """API限流错误"""
    pass


class APIAuthError(APIError):
    """API认证错误"""
    pass


class BaseAPIClient:
    """基础API客户端类"""
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 300,
        max_retries: int = 3,
        logger_name: Optional[str] = None
    ):
        """
        初始化基础API客户端
        
        Args:
            base_url: API基础URL
            api_key: API密钥
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            logger_name: 日志记录器名称
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = get_logger(logger_name or self.__class__.__name__)
        self.session = requests.Session()
        
        # 统计信息
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_retries": 0
        }
    
    def _get_headers(self) -> Dict[str, str]:
        """
        获取请求头（子类可重写）
        
        Returns:
            请求头字典
        """
        return {
            "Content-Type": "application/json"
        }
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        处理API响应（子类可重写）
        
        Args:
            response: requests响应对象
        
        Returns:
            响应数据字典
        
        Raises:
            APIError: API调用错误
        """
        try:
            data = response.json()
        except Exception:
            data = {"text": response.text}
        
        # 处理HTTP错误状态码
        if response.status_code == 401 or response.status_code == 403:
            raise APIAuthError(
                f"认证失败: {data.get('message', '未授权')}",
                status_code=response.status_code,
                response_data=data
            )
        elif response.status_code == 429:
            raise APIRateLimitError(
                f"请求过于频繁: {data.get('message', '已达到速率限制')}",
                status_code=response.status_code,
                response_data=data
            )
        elif response.status_code >= 400:
            raise APIError(
                f"API错误 ({response.status_code}): {data.get('message', response.text)}",
                status_code=response.status_code,
                response_data=data
            )
        
        return data
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, APIRateLimitError)),
        reraise=True
    )
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        发起HTTP请求（带重试机制）
        
        Args:
            method: HTTP方法（GET/POST/PUT/DELETE）
            endpoint: API端点
            data: 请求体数据
            params: URL参数
            headers: 额外的请求头
            timeout: 超时时间（秒）
        
        Returns:
            响应数据字典
        
        Raises:
            APIError: API调用错误
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_headers = self._get_headers()
        if headers:
            request_headers.update(headers)
        
        timeout = timeout or self.timeout
        
        self.stats["total_requests"] += 1
        self.logger.debug(f"发起请求: {method} {url}")
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=request_headers,
                timeout=timeout
            )
            
            result = self._handle_response(response)
            self.stats["successful_requests"] += 1
            self.logger.debug(f"请求成功: {method} {url}")
            
            return result
            
        except requests.exceptions.Timeout:
            self.stats["failed_requests"] += 1
            self.logger.error(f"请求超时: {method} {url}")
            raise APITimeoutError(f"请求超时 ({timeout}秒)")
        
        except requests.exceptions.RequestException as e:
            self.stats["failed_requests"] += 1
            self.stats["total_retries"] += 1
            self.logger.warning(f"请求失败，准备重试: {e}")
            raise
        
        except APIError:
            self.stats["failed_requests"] += 1
            raise
    
    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """GET请求"""
        return self._request("GET", endpoint, params=params, **kwargs)
    
    def post(self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """POST请求"""
        return self._request("POST", endpoint, data=data, **kwargs)
    
    def put(self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """PUT请求"""
        return self._request("PUT", endpoint, data=data, **kwargs)
    
    def delete(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """DELETE请求"""
        return self._request("DELETE", endpoint, **kwargs)
    
    def poll_until_complete(
        self,
        check_func: Callable[[], Dict[str, Any]],
        is_complete_func: Callable[[Dict[str, Any]], bool],
        interval: float = 5.0,
        max_wait: float = 1800.0
    ) -> Dict[str, Any]:
        """
        轮询直到任务完成
        
        Args:
            check_func: 检查任务状态的函数
            is_complete_func: 判断任务是否完成的函数
            interval: 轮询间隔（秒）
            max_wait: 最大等待时间（秒）
        
        Returns:
            最终任务结果
        
        Raises:
            APITimeoutError: 超时错误
        """
        start_time = time.time()
        self.logger.info(f"开始轮询任务状态，间隔 {interval}秒，最长等待 {max_wait}秒")
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > max_wait:
                raise APITimeoutError(f"轮询超时 ({max_wait}秒)")
            
            try:
                result = check_func()
                
                if is_complete_func(result):
                    self.logger.info(f"任务完成，总耗时 {elapsed:.1f}秒")
                    return result
                
                self.logger.debug(f"任务进行中... 已等待 {elapsed:.1f}秒")
                time.sleep(interval)
                
            except Exception as e:
                self.logger.error(f"轮询过程中出错: {e}")
                raise
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取API调用统计信息
        
        Returns:
            统计信息字典
        """
        return self.stats.copy()
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_retries": 0
        }
    
    def close(self):
        """关闭会话"""
        self.session.close()
        self.logger.debug("API客户端会话已关闭")
