"""Validate configuration without printing credentials or making network requests."""
import argparse
from pathlib import Path

import dotenv
from hydra import compose, initialize_config_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Also require SMTP credentials")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    dotenv.load_dotenv(root / ".env")
    with initialize_config_dir(config_dir=str(root / "config"), version_base=None):
        cfg = compose(config_name="default")
    missing = []
    if not str(cfg.zotero.user_id).isdigit():
        missing.append("ZOTERO_ID（Zotero 数字用户 ID）")
    if not cfg.zotero.api_key:
        missing.append("ZOTERO_KEY（个人文献库只读 API Key）")
    if cfg.llm.get("enabled", True):
        if not cfg.llm.api.key:
            missing.append("OPENAI_API_KEY（摘要服务 API Key）")
        if not str(cfg.llm.api.base_url).startswith("https://"):
            missing.append("OPENAI_API_BASE（HTTPS API 地址）")
        if not cfg.llm.generation_kwargs.model:
            missing.append("LLM_MODEL（模型名称）")
    if args.send:
        for key, value in (("SENDER", cfg.email.sender), ("RECEIVER", cfg.email.receiver)):
            if "@" not in str(value):
                missing.append(key + "（完整邮箱地址）")
        if not cfg.email.sender_password:
            missing.append("SENDER_PASSWORD（163 SMTP 授权码）")
    print("摘要模式：" + ("AI 中文摘要" if cfg.llm.get("enabled", True) else "论文原始摘要；不调用摘要 API"))
    print("邮件模式：" + ("发送" if args.send else "本地预览"))
    if missing:
        print("尚需填写 .env 或 GitHub Secrets：")
        for item in missing:
            print("- " + item)
        return 2
    print("配置字段检查通过；尚未验证远程账号、模型下载和邮件投递。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
