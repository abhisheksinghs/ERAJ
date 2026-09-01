"""Logging helpers: tag every record with the active tenant schema, and a
JSON formatter for production (log drains parse it; humans read `plain` in dev).
"""
import json
import logging

from django.db import connection


class SchemaFilter(logging.Filter):
    def filter(self, record):
        record.schema = getattr(connection, "schema_name", "-")
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        out = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "schema": getattr(record, "schema", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)
