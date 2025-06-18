#!/usr/bin/env python3
"""
WSGI configuration for Student Affairs System
"""

import os
import sys
import logging
from app import app, cleanup_resources
import atexit
import signal

# إعداد التسجيل للإنتاج
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/app.log') if os.path.exists('/tmp') else logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def signal_handler(sig, frame):
    """معالج إشارات النظام للتنظيف"""
    logger.info('تم استلام إشارة إنهاء WSGI. جاري تنظيف الموارد...')
    cleanup_resources()
    sys.exit(0)

# تسجيل معالجات الإشارات
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
atexit.register(cleanup_resources)

if __name__ == "__main__":
    app.run() 