"""Platform-aware upload pipeline.

Every store has an isolated package below this directory.  Shared code may parse,
compare and stage rows, but store-specific customer rules and refresh paths must
never be guessed in the HTTP layer.
"""

from upload.service import UploadService, template_csv

__all__ = ["UploadService", "template_csv"]
