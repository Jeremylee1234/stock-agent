"""配置管理模块

使用Pydantic进行配置验证，支持环境变量和配置文件。
"""
import os
from typing import Optional, Literal
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class LLMConfig(BaseModel):
    """大语言模型配置"""
    model_config = ConfigDict(extra='forbid')
    
    default_model: str = Field(
        default="deepseek-v4-pro",
        description="默认使用的模型"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="模型温度参数"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        gt=0,
        description="最大生成token数"
    )
    timeout: int = Field(
        default=60,
        gt=0,
        description="API调用超时时间（秒）"
    )


class DataSourceConfig(BaseModel):
    """数据源配置"""
    model_config = ConfigDict(extra='forbid')
    
    # Tushare Pro配置
    tushare_token: Optional[str] = Field(
        default=None,
        description="Tushare Pro API Token"
    )
    tushare_timeout: int = Field(
        default=30,
        gt=0,
        description="Tushare API超时时间（秒）"
    )
    tushare_retry_count: int = Field(
        default=20,
        ge=0,
        description="Tushare API重试次数"
    )

    # iFinD 量化 API
    ifind_refresh_token: Optional[str] = Field(
        default=None,
        description="iFinD refresh_token（超级命令获取）"
    )
    ifind_timeout: int = Field(
        default=30,
        gt=0,
        description="iFinD API超时时间（秒）"
    )
    
    # 数据源优先级
    data_source_priority: list[str] = Field(
        default=["ifind", "tushare"],
        description="数据源优先级顺序"
    )


class CacheConfig(BaseModel):
    """缓存配置"""
    model_config = ConfigDict(extra='forbid')
    
    enable_cache: bool = Field(
        default=True,
        description="是否启用缓存"
    )
    cache_dir: Path = Field(
        default=Path("data_cache"),
        description="缓存目录"
    )
    cache_ttl: int = Field(
        default=3600,
        gt=0,
        description="缓存过期时间（秒）"
    )
    max_cache_size_mb: int = Field(
        default=1000,
        gt=0,
        description="最大缓存大小（MB）"
    )


class LogConfig(BaseModel):
    """日志配置"""
    model_config = ConfigDict(extra='forbid')
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="日志级别"
    )
    log_dir: Path = Field(
        default=Path("logs"),
        description="日志目录"
    )
    log_to_console: bool = Field(
        default=True,
        description="是否输出到控制台"
    )
    log_to_file: bool = Field(
        default=True,
        description="是否输出到文件"
    )
    log_rotation: str = Field(
        default="1 day",
        description="日志轮转周期"
    )
    log_retention: str = Field(
        default="30 days",
        description="日志保留时间"
    )
    log_max_size: str = Field(
        default="100 MB",
        description="单个日志文件最大大小"
    )


class PerformanceConfig(BaseModel):
    """性能配置"""
    model_config = ConfigDict(extra='forbid')
    
    max_concurrent_requests: int = Field(
        default=10,
        gt=0,
        description="最大并发请求数"
    )
    request_timeout: int = Field(
        default=300,
        gt=0,
        description="请求超时时间（秒）"
    )
    data_compression_threshold: int = Field(
        default=20000,
        gt=0,
        description="数据压缩阈值（token数）"
    )
    max_message_history: int = Field(
        default=30,
        gt=0,
        description="最大消息历史数量"
    )
    enable_data_compression: bool = Field(
        default=True,
        description="是否启用数据压缩"
    )


class APIConfig(BaseModel):
    """API配置"""
    model_config = ConfigDict(extra='forbid')
    
    host: str = Field(
        default="0.0.0.0",
        description="API服务监听地址"
    )
    port: int = Field(
        default=8000,
        gt=0,
        lt=65536,
        description="API服务端口"
    )
    cors_origins: list[str] = Field(
        default=["*"],
        description="允许的CORS源"
    )
    enable_docs: bool = Field(
        default=True,
        description="是否启用API文档"
    )


class Settings(BaseSettings):
    """应用配置
    
    支持从环境变量和.env文件加载配置。
    环境变量优先级高于配置文件。
    """
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_nested_delimiter='__',
        case_sensitive=False,
        extra='ignore'
    )
    
    # 环境配置
    environment: Literal["development", "testing", "production"] = Field(
        default="development",
        description="运行环境"
    )
    
    # API Keys
    deepseek_api_key: str = Field(
        ...,
        description="DeepSeek API Key（必需）"
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API Key（可选）"
    )
    serpapi_api_key: Optional[str] = Field(
        default=None,
        description="SerpAPI Key（可选）"
    )
    bing_search_api_key: Optional[str] = Field(
        default=None,
        description="Bing Search API Key（可选）"
    )
    bing_search_endpoint: str = Field(
        default="https://api.bing.microsoft.com/v7.0/search",
        description="Bing Search API端点"
    )
    
    # MCP Server
    mcp_server_url: Optional[str] = Field(
        default=None,
        description="MCP服务器URL（可选）"
    )
    
    # Database
    database_url: Optional[str] = Field(
        default=None,
        description="数据库连接URL（可选）"
    )
    
    # 子配置
    llm: LLMConfig = Field(default_factory=LLMConfig)
    data_source: DataSourceConfig = Field(default_factory=DataSourceConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    log: LogConfig = Field(default_factory=LogConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    
    @field_validator('deepseek_api_key')
    @classmethod
    def validate_deepseek_key(cls, v):
        """验证DeepSeek API Key"""
        if not v or not v.strip():
            raise ValueError("DEEPSEEK_API_KEY是必需的")
        if not v.startswith('sk-'):
            raise ValueError("DEEPSEEK_API_KEY格式无效，应以'sk-'开头")
        return v.strip()
    
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self.environment == "development"
    
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.environment == "production"
    
    def is_testing(self) -> bool:
        """是否为测试环境"""
        return self.environment == "testing"
    
    def get_tushare_token(self) -> Optional[str]:
        """获取Tushare Token"""
        return self.data_source.tushare_token
    
    def has_tushare(self) -> bool:
        """是否配置了Tushare"""
        return bool(self.data_source.tushare_token)

    def get_ifind_refresh_token(self) -> Optional[str]:
        """获取 iFinD refresh_token（环境变量 IFIND_REFRESH_TOKEN 优先）"""
        return os.getenv("IFIND_REFRESH_TOKEN") or self.data_source.ifind_refresh_token

    def has_ifind(self) -> bool:
        """是否配置了 iFinD"""
        return bool(self.get_ifind_refresh_token())


# 全局配置实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取配置实例（单例模式）"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """重新加载配置"""
    global _settings
    _settings = Settings()
    return _settings


# 向后兼容：导出常用配置项
settings = get_settings()

# API Keys
DEEPSEEK_API_KEY = settings.deepseek_api_key
OPENAI_API_KEY = settings.openai_api_key
SERPAPI_API_KEY = settings.serpapi_api_key
BING_SEARCH_API_KEY = settings.bing_search_api_key
BING_SEARCH_ENDPOINT = settings.bing_search_endpoint

# Tushare Pro
TUSHARE_TOKEN = settings.data_source.tushare_token

# iFinD
IFIND_REFRESH_TOKEN = settings.get_ifind_refresh_token()

# MCP Server
MCP_SERVER_URL = settings.mcp_server_url

# Database
DATABASE_URL = settings.database_url

# Model Configuration
DEFAULT_MODEL = settings.llm.default_model
TEMPERATURE = settings.llm.temperature

# API Configuration (convenience exports)
API_HOST = settings.api.host
API_PORT = settings.api.port
CORS_ORIGINS = settings.api.cors_origins
DEBUG = settings.is_development()

