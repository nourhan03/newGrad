from flask_socketio import SocketIO
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
socketio = SocketIO(async_mode='threading', daemon=False)
scheduler = APScheduler() 