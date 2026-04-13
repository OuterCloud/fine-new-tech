from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = Path(".env")

# 配置项定义：(env_key, label, 是否敏感, 分组, 说明)
CONFIG_FIELDS = [
    (
        "API_KEY",
        "API Key",
        True,
        "AI 服务",
        "AI 服务商的 API 密钥，如硅基流动、DeepSeek、Groq 等",
    ),
    (
        "API_BASE_URL",
        "API Base URL",
        False,
        "AI 服务",
        "AI 服务的接口地址，不同服务商地址不同",
    ),
    (
        "LLM_MODEL",
        "模型名称",
        False,
        "AI 服务",
        "使用的大语言模型名称，如 deepseek-ai/DeepSeek-V3",
    ),
    (
        "LLM_MAX_TOKENS",
        "最大 Token 数",
        False,
        "AI 服务",
        "单次生成的最大 Token 数，影响报告完整度",
    ),
    (
        "MAX_GITHUB_REPOS",
        "GitHub 抓取数量",
        False,
        "数据抓取",
        "每次抓取 GitHub Trending 的仓库数量",
    ),
    (
        "MAX_HN_STORIES",
        "Hacker News 抓取数量",
        False,
        "数据抓取",
        "每次抓取 Hacker News 的文章数量",
    ),
    (
        "GITHUB_PAGES_REPO",
        "GitHub Pages 仓库地址",
        False,
        "发布",
        "发布目标仓库的 HTTPS 地址，如 https://github.com/user/repo.git",
    ),
    (
        "GITHUB_TOKEN",
        "GitHub Token",
        True,
        "发布",
        "GitHub Personal Access Token，用于推送到仓库，需要 repo 权限",
    ),
]


class Settings(BaseSettings):
    api_key: str = ""
    api_base_url: str = "https://api.siliconflow.cn/v1"
    llm_model: str = "deepseek-ai/DeepSeek-V3"
    llm_max_tokens: int = 16384
    max_github_repos: int = 25
    max_hn_stories: int = 30
    github_pages_repo: str = ""
    github_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def _mask(value: str) -> str:
    """对敏感值脱敏：保留前4后4，中间用 * 替代。"""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def get_settings_display() -> list[dict]:
    """返回当前配置列表（敏感字段脱敏）。"""
    env_values = _read_env()
    result = []
    for env_key, label, sensitive, group, hint in CONFIG_FIELDS:
        # 优先从 .env 文件读，否则从 settings 对象取
        attr = env_key.lower()
        raw = env_values.get(env_key, str(getattr(settings, attr, "")))
        result.append(
            {
                "key": env_key,
                "label": label,
                "value": _mask(raw) if sensitive and raw else raw,
                "sensitive": sensitive,
                "group": group,
                "hint": hint,
            }
        )
    return result


def _read_env() -> dict[str, str]:
    """读取 .env 文件为 dict。"""
    values = {}
    if not _ENV_FILE.exists():
        return values
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values


def update_settings(updates: dict[str, str]) -> None:
    """更新 .env 文件中的配置项，并热更新 settings 对象。"""
    global settings
    env_values = _read_env()

    # 合并更新（空字符串的敏感字段表示不修改）
    sensitive_keys = {k for k, _, s, _, _ in CONFIG_FIELDS if s}
    for key, value in updates.items():
        # 如果是敏感字段且值包含 *，说明是脱敏值，跳过
        if key in sensitive_keys and "*" in value:
            continue
        env_values[key] = value

    # 写回 .env
    lines = []
    for env_key, label, sensitive, group, hint in CONFIG_FIELDS:
        if env_key in env_values and env_values[env_key]:
            lines.append(f"{env_key}={env_values[env_key]}")
    _ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 热更新 settings 对象
    settings = Settings()
