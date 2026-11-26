# -*- coding: utf-8 -*-
"""Waitress entry point used by systemd in production.

Environment:
    STUDYLOOP_HOST  default 127.0.0.1
    STUDYLOOP_PORT  default 8011
    STUDYLOOP_THREADS default 8
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studyplan.settings")

from waitress import serve  # noqa: E402
from studyplan.wsgi import application  # noqa: E402


def main():
    host = os.environ.get("STUDYLOOP_HOST", "127.0.0.1")
    port = int(os.environ.get("STUDYLOOP_PORT", "8011"))
    threads = int(os.environ.get("STUDYLOOP_THREADS", "8"))
    serve(application, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
