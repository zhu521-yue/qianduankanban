from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from psycopg import Connection

from app.catalog import STORES, allowed_stores
from app.responses import ApiError
from app.schemas import UserContext
from upload.pipeline import analyse_upload, analysis_payload
from upload.registry import get_config


TASKS: dict[str, dict[str, Any]] = {}


def template_csv() -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("说明",))
    writer.writerow(("各平台必须上传对应平台导出的原始CSV/XLSX文件，不使用统一字段模板。",))
    return buffer.getvalue()


class UploadService:
    def __init__(self, conn: Connection, max_bytes: int):
        self.conn = conn
        self.max_bytes = max_bytes

    def process(self, user: UserContext, store_key: str, file_name: str, content: bytes, mode: str) -> dict[str, Any]:
        if store_key not in STORES:
            raise ApiError(400, "STORE_INVALID", "未知店铺。")
        if store_key not in set(allowed_stores(user.role)) or user.role == "manager":
            raise ApiError(403, "UPLOAD_FORBIDDEN", "当前账号无权向该店铺上传数据。")
        if mode not in {"preview", "commit"}:
            raise ApiError(400, "UPLOAD_MODE_INVALID", "上传模式必须为preview或commit。")
        if not content:
            raise ApiError(400, "FILE_EMPTY", "上传文件不能为空。")
        if len(content) > self.max_bytes:
            limit_mb = self.max_bytes // (1024 * 1024)
            raise ApiError(413, "FILE_TOO_LARGE", f"上传文件超过{limit_mb}MB限制。")

        config = get_config(store_key)
        self.conn.execute("SET LOCAL TIME ZONE 'Asia/Shanghai'")
        analysis = analyse_upload(
            self.conn,
            config,
            file_name,
            content,
            include_business_preview=mode == "preview",
        )
        preview = analysis_payload(analysis)
        write_result: dict[str, Any] | None = None
        if mode == "commit":
            if not config.commit_enabled:
                raise ApiError(
                    409,
                    "UPLOAD_REFRESH_NOT_READY",
                    f"{STORES[store_key].name}已完成真实数据库差异预览，但店铺、平台、业务组和渠道的原子刷新器尚未启用，禁止只写raw_data。",
                )
            try:
                if store_key == "doudian_kocotree":
                    from upload.doudian_kocotree.committer import commit_upload
                elif store_key == "doudian_children":
                    from upload.doudian_children.committer import commit_upload
                elif store_key == "weidian":
                    from upload.weidian.committer import commit_upload
                elif store_key == "kuaishou":
                    from upload.kuaishou.committer import commit_upload
                elif store_key == "alibaba":
                    from upload.alibaba.committer import commit_upload
                elif store_key == "jushuitan":
                    from upload.jushuitan.committer import commit_upload
                elif store_key == "kuaituantuan":
                    from upload.kuaituantuan.committer import commit_upload
                elif store_key == "youzan_qijian":
                    from upload.youzan_qijian.committer import commit_upload
                elif store_key == "youzan_muying":
                    from upload.youzan_muying.committer import commit_upload
                else:
                    raise ValueError("当前店铺尚未配置正式原子刷新器")

                write_result = commit_upload(self.conn, config, analysis)
                self.conn.commit()
            except ApiError:
                self.conn.rollback()
                raise
            except Exception as exc:
                self.conn.rollback()
                raise ApiError(
                    409,
                    "UPLOAD_REFRESH_FAILED",
                    f"整批上传未生效，数据库已回滚：{exc}",
                ) from exc

        now = datetime.now(timezone.utc).isoformat()
        task_id = f"upl_{uuid4().hex}"
        task = {
            "id": task_id,
            "user_id": user.id,
            "store_key": store_key,
            "file_name": Path(file_name).name,
            "file_size": len(content),
            "mode": mode,
            "status": "committed" if write_result else "validated",
            "commit_available": config.commit_enabled,
            "message": (
                "全部数据已在单个事务中写入并完成店铺、平台、业务组和渠道联动"
                if write_result
                else (
                    "已按商品明细业务键完成新增、更新、不变记录和客户名单预检，未写入数据库"
                    if preview["upload_strategy"] == "upsert_business_keys"
                    else (
                    "已根据真实raw_data完成新日期新增、已有日期整日覆盖预览和客户名单预检，未写入数据库"
                    if preview["upload_strategy"] == "replace_existing_dates"
                    else "已根据真实raw_data完成新日期新增、已有日期整日跳过预览和客户名单预检，未写入数据库"
                    )
                )
            ),
            "created_at": now,
            "completed_at": now,
            **preview,
        }
        if write_result:
            task["write_result"] = {
                key: value for key, value in write_result.items() if key != "table_changes"
            }
            task["table_changes"] = write_result["table_changes"]
        TASKS[task_id] = task
        return task

    def task(self, task_id: str, include_errors: bool = False) -> dict[str, Any]:
        task = TASKS.get(task_id)
        if not task:
            raise ApiError(404, "UPLOAD_NOT_FOUND", "未找到当前进程内的上传预览任务。")
        result = dict(task)
        if not include_errors:
            result.pop("changed_row_sample", None)
            result.pop("new_customer_sample", None)
        return result

    def list_tasks(self, user: UserContext, limit: int = 100) -> list[dict[str, Any]]:
        permitted = set(allowed_stores(user.role))
        rows = [task for task in TASKS.values() if user.role == "manager" or task["store_key"] in permitted]
        return sorted(rows, key=lambda item: item["created_at"], reverse=True)[:limit]
