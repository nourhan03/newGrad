#!/bin/bash

# تعيين PORT إذا لم يكن موجوداً
if [ -z "$PORT" ]; then
    export PORT=5000
fi

echo "Starting Student Affairs System on port $PORT"
echo "Environment variables: PORT=$PORT"

# بدء التطبيق الأساسي
exec gunicorn --bind "0.0.0.0:$PORT" --worker-class eventlet --workers 1 --timeout 120 --log-level info app:app 
