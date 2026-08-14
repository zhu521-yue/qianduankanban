"""Backward-compatible import path for the platform-aware upload package."""

from upload.service import UploadService, template_csv

__all__ = ["UploadService", "template_csv"]
