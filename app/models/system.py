from datetime import datetime
from app.extensions import db

class SystemMetric(db.Model):
    __tablename__ = 'system_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    cpu_usage = db.Column(db.Float)
    memory_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    network_rx = db.Column(db.BigInteger)
    network_tx = db.Column(db.BigInteger)
    active_connections = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'disk_usage': self.disk_usage,
            'network_rx': self.network_rx,
            'network_tx': self.network_tx,
            'active_connections': self.active_connections,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
