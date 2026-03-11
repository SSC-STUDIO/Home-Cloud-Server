import psutil
import threading
import time
from app.models.system import SystemMetric
from app.models.system_setting import SystemSetting
from app.extensions import db
import os
import platform
import datetime

class SystemMonitor:
    def __init__(self, app=None, interval=300):
        """
        Initialize the system monitor
        
        Args:
            app: Flask application instance
            interval: Monitoring interval in seconds (default: 300 seconds / 5 minutes)
        """
        self.app = app
        self.interval = interval
        self.thread = None
        self.running = False
        self._first_request_processed = False
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """
        Initialize with Flask app
        """
        self.app = app
        
        # Start monitoring when app starts
        @app.before_request
        def check_start_monitoring():
            if not self._first_request_processed:
                self.start()
                self._first_request_processed = True
    
    def get_disk_usage(self):
        """
        Get total disk usage across all mounted partitions
        """
        total_size = 0
        total_used = 0
        total_free = 0
        
        # Get all mounted partitions
        partitions = psutil.disk_partitions(all=False)
        
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                total_size += usage.total
                total_used += usage.used
                total_free += usage.free
            except Exception:
                continue
        
        # Calculate percentage
        if total_size > 0:
            usage_percent = (total_used / total_size) * 100
        else:
            usage_percent = 0
        
        return {
            'total': total_size,
            'used': total_used,
            'free': total_free,
            'percent': usage_percent
        }
    
    def collect_metrics(self):
        """
        Collect system metrics and save to database
        """
        with self.app.app_context():
            # Get system stats
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # Get total disk usage
            disk = self.get_disk_usage()
            
            net_io_counters = psutil.net_io_counters()
            
            # Create new metric record
            new_metric = SystemMetric(
                cpu_usage=cpu_percent,
                memory_usage=memory.percent,
                disk_usage=disk['percent'],
                network_rx=net_io_counters.bytes_recv,
                network_tx=net_io_counters.bytes_sent,
                active_connections=len(psutil.net_connections())
            )
            
            db.session.add(new_metric)
            db.session.commit()
            
            # Clean up old metrics (keep only last 30 days)
            thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            old_metrics = SystemMetric.query.filter(SystemMetric.timestamp < thirty_days_ago).delete()
            db.session.commit()
            
            # Clean up expired trash items if enabled
            self.cleanup_trash()
    
    def cleanup_trash(self):
        """
        Clean up expired trash items
        """
        # Check if auto cleanup is enabled
        auto_clean = SystemSetting.query.filter_by(key='auto_clean_trash').first()
        if not auto_clean or not auto_clean.get_typed_value():
            return
        
        # Import here to avoid circular imports
        from app.models.file import File, Folder
        
        now = datetime.datetime.utcnow()
        
        # Get expired files
        expired_files = File.query.filter(
            File.is_deleted == True,
            File.expiry_date <= now
        ).all()
        
        # Delete expired files
        for file in expired_files:
            try:
                if os.path.exists(file.file_path):
                    os.remove(file.file_path)
            except Exception as e:
                print(f"Error deleting file {file.file_path}: {e}")
            db.session.delete(file)
        
        # Get expired folders
        expired_folders = Folder.query.filter(
            Folder.is_deleted == True,
            Folder.expiry_date <= now
        ).all()
        
        # Delete expired folders
        for folder in expired_folders:
            db.session.delete(folder)
        
        db.session.commit()
        
        # Log cleanup activity
        if expired_files or expired_folders:
            from app.models.activity import Activity
            from app.models.user import User
            admin_user = User.query.filter_by(role='admin').first()
            if admin_user:
                activity = Activity(
                    user_id=admin_user.id,
                    action='auto_cleanup',
                    details=f'Auto-cleaned {len(expired_files)} files and {len(expired_folders)} folders from trash'
                )
                db.session.add(activity)
                db.session.commit()
    
    def monitoring_thread(self):
        """
        Background thread for periodic monitoring
        """
        while self.running:
            try:
                self.collect_metrics()
            except Exception as e:
                print(f"Error collecting metrics: {e}")
            
            # Sleep for interval
            time.sleep(self.interval)
    
    def start(self):
        """
        Start the monitoring thread
        """
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.monitoring_thread)
            self.thread.daemon = True
            self.thread.start()
    
    def stop(self):
        """
        Stop the monitoring thread
        """
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
            self.thread = None

def get_system_info():
    """
    Get detailed system information
    
    Returns:
        dict: System information including CPU, memory, disk, network, and OS details
    """
    # CPU info
    cpu_info = {
        'physical_cores': psutil.cpu_count(logical=False),
        'total_cores': psutil.cpu_count(logical=True),
        'max_frequency': psutil.cpu_freq().max if psutil.cpu_freq() else None,
        'current_frequency': psutil.cpu_freq().current if psutil.cpu_freq() else None,
        'cpu_percent': psutil.cpu_percent(percpu=True)
    }
    
    # Memory info
    memory_info = dict(psutil.virtual_memory()._asdict())
    
    # Disk info
    disk_info = []
    for partition in psutil.disk_partitions():
        try:
            partition_usage = psutil.disk_usage(partition.mountpoint)
            disk_info.append({
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'filesystem_type': partition.fstype,
                'total_size': partition_usage.total,
                'used': partition_usage.used,
                'free': partition_usage.free,
                'percent': partition_usage.percent
            })
        except Exception:
            pass
    
    # Network info
    net_io = psutil.net_io_counters()
    net_connections = len(psutil.net_connections())
    
    # OS info
    os_info = {
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'hostname': platform.node(),
        'uptime': datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
    }
    
    return {
        'cpu': cpu_info,
        'memory': memory_info,
        'disk': disk_info,
        'network': {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv,
            'active_connections': net_connections
        },
        'os': os_info,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    } 
