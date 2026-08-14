from __future__ import annotations

from importlib import import_module

from app.catalog import STORES
from upload.models import StoreUploadConfig


def _load() -> dict[str, StoreUploadConfig]:
    result: dict[str, StoreUploadConfig] = {}
    for store_key in STORES:
        module = import_module(f"upload.{store_key}.config")
        config: StoreUploadConfig = module.CONFIG
        if config.store_key != store_key:
            raise RuntimeError(f"上传配置目录{store_key}与CONFIG.store_key不一致")
        result[store_key] = config
    return result


CONFIGS = _load()


def get_config(store_key: str) -> StoreUploadConfig:
    return CONFIGS[store_key]
