from __future__ import annotations

from datetime import datetime, timezone

from pythonjsonlogger import jsonlogger

from app.logging_context import get_logging_context


class RequestJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name

        context = get_logging_context()
        for key, value in context.items():
            if value is not None and log_record.get(key) in (None, ""):
                log_record[key] = value

        for key in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "request_id",
            "user_id",
            "client_ip",
        ):
            log_record.setdefault(key, None)


def configure_logging() -> None:
    import logging.config

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "app.logging_setup.RequestJsonFormatter",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": "INFO",
            },
            "loggers": {
                "uvicorn": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },
            },
        }
    )
