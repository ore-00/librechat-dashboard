#!/usr/bin/env python3
"""
LibreChat Control Panel v3 - Dashboard Edition
A modern dashboard GUI for managing LibreChat services on CachyOS
with real-time monitoring, graphs, and enhanced UX
"""

import sys
import subprocess
import os
import psutil
import time
from pathlib import Path
from datetime import datetime
from collections import deque
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QScrollArea, QMessageBox,
    QTabWidget, QGridLayout, QFrame, QProgressBar, QGroupBox
)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QTextCursor, QPalette, QColor, QIcon
from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PyQt6.QtWebEngineWidgets import QWebEngineView


class PgAdminManager(QThread):
    """Manage pgAdmin4 process"""
    status_updated = pyqtSignal(bool, str)  # is_running, url
    output_ready = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.process = None
        self.running = False
        self.pgadmin_url = None
    
    def run(self):
        """Start pgAdmin4"""
        pgadmin_path = Path.home() / '.local' / 'src' / 'pgadmin'
        venv_python = pgadmin_path / 'bin' / 'python'
        pgadmin_script = pgadmin_path / 'bin' / 'pgadmin4'
        
        if not pgadmin_script.exists():
            self.output_ready.emit(f"Error: pgAdmin not found at {pgadmin_script}\n")
            self.output_ready.emit("Install with: cd ~/.local/src/pgadmin && source bin/activate && pip install pgadmin4\n")
            self.status_updated.emit(False, "")
            return
        
        try:
            self.process = subprocess.Popen(
                [str(pgadmin_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(pgadmin_path)
            )
            
            self.running = True
            
            # Wait for pgAdmin to start and find the URL
            for line in self.process.stdout:
                self.output_ready.emit(line)
                
                # Look for the server URL in output
                if 'http' in line.lower() and ('127.0.0.1' in line or 'localhost' in line):
                    # Extract URL from line
                    import re
                    url_match = re.search(r'http://[^\s]+', line)
                    if url_match:
                        self.pgadmin_url = url_match.group(0).rstrip('/')
                    else:
                        self.pgadmin_url = "http://127.0.0.1:5050"
                    self.status_updated.emit(True, self.pgadmin_url)
                
                if not self.running:
                    break
            
            self.process.wait()
            self.running = False
            self.status_updated.emit(False, "")
            
        except Exception as e:
            self.output_ready.emit(f"Error starting pgAdmin: {str(e)}\n")
            self.running = False
            self.status_updated.emit(False, "")
    
    def stop(self):
        """Stop pgAdmin4"""
        self.running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


class SystemMonitor(QThread):
    """Monitor system-wide resources"""
    stats_updated = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.history_size = 60  # Keep 60 data points (1 minute at 1s intervals)
        self.cpu_history = deque(maxlen=self.history_size)
        self.ram_history = deque(maxlen=self.history_size)
    
    def run(self):
        while self.running:
            cpu_percent = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            self.cpu_history.append(cpu_percent)
            self.ram_history.append(ram.percent)
            
            stats = {
                'cpu_percent': cpu_percent,
                'ram_percent': ram.percent,
                'ram_used_gb': ram.used / (1024**3),
                'ram_total_gb': ram.total / (1024**3),
                'disk_percent': disk.percent,
                'disk_used_gb': disk.used / (1024**3),
                'disk_total_gb': disk.total / (1024**3),
                'cpu_history': list(self.cpu_history),
                'ram_history': list(self.ram_history)
            }
            
            self.stats_updated.emit(stats)
    
    def stop(self):
        self.running = False


class ServiceMonitor(QThread):
    """Monitor services and processes"""
    status_updated = pyqtSignal(str, dict)  # service_name, status_dict
    logs_ready = pyqtSignal(str, str)  # service_name, logs
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.previous_status = {}
        self.service_stats = {}
    
    def run(self):
        while self.running:
            # Check systemd services
            for service in ['mongodb', 'postgresql', 'meilisearch', 'ollama']:
                status = self.check_systemd_service(service)
                pid = self.get_service_pid(service)
                
                stats = {
                    'status': status,
                    'is_running': (status == "active"),
                    'pid': pid,
                    'cpu_percent': 0,
                    'memory_mb': 0,
                    'uptime': self.get_service_uptime(service) if status == "active" else "N/A"
                }
                
                # If service just became active, fetch logs
                if status == "active" and self.previous_status.get(service) != "active":
                    logs = self.get_systemd_logs(service, 10)
                    self.logs_ready.emit(service, logs)
                
                self.previous_status[service] = status
                
                # Get process stats if running
                if pid:
                    try:
                        proc = psutil.Process(pid)
                        stats['cpu_percent'] = proc.cpu_percent(interval=0.1)
                        stats['memory_mb'] = proc.memory_info().rss / (1024**2)
                    except:
                        pass
                
                self.status_updated.emit(service, stats)
            
            # Check manual processes
            for name, port, cmd_filter in [('librechat', 3080, 'node'), ('rag_api', 8000, 'uvicorn')]:
                stats = self.check_process(name, port, cmd_filter)
                self.status_updated.emit(name, stats)
            
            self.msleep(2000)
    
    def check_systemd_service(self, service):
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service],
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip()
        except:
            return "unknown"
    
    def get_service_pid(self, service):
        try:
            result = subprocess.run(
                ['systemctl', 'show', service, '--property=MainPID'],
                capture_output=True, text=True, timeout=2
            )
            pid_str = result.stdout.strip().split('=')[1]
            pid = int(pid_str)
            return pid if pid > 0 else None
        except:
            return None
    
    def get_service_uptime(self, service):
        try:
            result = subprocess.run(
                ['systemctl', 'show', service, '--property=ActiveEnterTimestamp'],
                capture_output=True, text=True, timeout=2
            )
            timestamp_str = result.stdout.strip().split('=')[1]
            if timestamp_str:
                # Parse and calculate uptime
                start_time = datetime.strptime(timestamp_str.split('.')[0], '%a %Y-%m-%d %H:%M:%S %Z')
                uptime = datetime.now() - start_time
                days = uptime.days
                hours, remainder = divmod(uptime.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                if days > 0:
                    return f"{days}d {hours}h"
                elif hours > 0:
                    return f"{hours}h {minutes}m"
                else:
                    return f"{minutes}m"
            return "N/A"
        except:
            return "N/A"
    
    def check_process(self, name, port, command_filter):
        stats = {
            'status': 'inactive',
            'is_running': False,
            'pid': None,
            'cpu_percent': 0,
            'memory_mb': 0,
            'uptime': 'N/A'
        }
        
        try:
            for conn in psutil.net_connections():
                if conn.laddr.port == port and conn.status == 'LISTEN':
                    try:
                        proc = psutil.Process(conn.pid)
                        cmdline = ' '.join(proc.cmdline())
                        if command_filter.lower() in cmdline.lower():
                            stats['status'] = 'active'
                            stats['is_running'] = True
                            stats['pid'] = conn.pid
                            stats['cpu_percent'] = proc.cpu_percent(interval=0.1)
                            stats['memory_mb'] = proc.memory_info().rss / (1024**2)
                            
                            # Calculate uptime
                            create_time = datetime.fromtimestamp(proc.create_time())
                            uptime = datetime.now() - create_time
                            hours, remainder = divmod(uptime.seconds, 3600)
                            minutes, _ = divmod(remainder, 60)
                            if uptime.days > 0:
                                stats['uptime'] = f"{uptime.days}d {hours}h"
                            elif hours > 0:
                                stats['uptime'] = f"{hours}h {minutes}m"
                            else:
                                stats['uptime'] = f"{minutes}m"
                            break
                    except:
                        pass
        except:
            pass
        
        return stats
    
    def get_systemd_logs(self, service, lines=10):
        """Fetch recent logs from systemd journal"""
        try:
            result = subprocess.run(
                ['journalctl', '-u', service, '-n', str(lines), '--no-pager'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout
        except Exception as e:
            return f"Could not fetch logs: {str(e)}\n"
    
    def stop(self):
        self.running = False


class ProcessRunner(QThread):
    """Run processes and capture output"""
    output_ready = pyqtSignal(str)
    process_finished = pyqtSignal(int)
    process_started = pyqtSignal()
    
    def __init__(self, command, cwd=None):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self.process = None
    
    def run(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1
            )
            self.process_started.emit()
            
            for line in self.process.stdout:
                self.output_ready.emit(line)
            
            self.process.wait()
            self.process_finished.emit(self.process.returncode)
        except Exception as e:
            self.output_ready.emit(f"Error: {str(e)}\n")
            self.process_finished.emit(-1)
    
    def stop_process(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


class ServiceCard(QFrame):
    """Individual service card widget"""
    
    log_signal = pyqtSignal(str)  # Signal for log output
    
    def __init__(self, name, display_name, is_systemd=True):
        super().__init__()
        self.name = name
        self.display_name = display_name
        self.is_systemd = is_systemd
        self.process_thread = None
        self.is_running = False
        
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Header
        header = QHBoxLayout()
        title = QLabel(self.display_name)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()
        
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("font-size: 16px; color: #9E9E9E;")
        header.addWidget(self.status_indicator)
        
        layout.addLayout(header)
        
        # Stats
        self.stats_label = QLabel("Status: Stopped")
        self.stats_label.setStyleSheet("color: #888888; font-size: 9px;")
        layout.addWidget(self.stats_label)
        
        self.resource_label = QLabel("CPU: 0% | RAM: 0 MB")
        self.resource_label.setStyleSheet("color: #888888; font-size: 9px;")
        layout.addWidget(self.resource_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        if self.is_systemd:
            self.start_btn = QPushButton("Start")
            self.start_btn.clicked.connect(self.start_service)
            self.start_btn.setMaximumHeight(30)
            btn_layout.addWidget(self.start_btn)
            
            self.stop_btn = QPushButton("Stop")
            self.stop_btn.clicked.connect(self.stop_service)
            self.stop_btn.setMaximumHeight(30)
            btn_layout.addWidget(self.stop_btn)
        else:
            self.start_btn = QPushButton("Start")
            self.start_btn.clicked.connect(self.start_process)
            self.start_btn.setMaximumHeight(30)
            btn_layout.addWidget(self.start_btn)
            
            self.stop_btn = QPushButton("Stop")
            self.stop_btn.clicked.connect(self.stop_process)
            self.stop_btn.setMaximumHeight(30)
            self.stop_btn.setEnabled(False)
            btn_layout.addWidget(self.stop_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.setMinimumHeight(120)
    
    def update_stats(self, stats):
        """Update service statistics"""
        is_running = stats.get('is_running', False)
        status = stats.get('status', 'unknown')
        self.is_running = is_running
        
        # Update status indicator
        if is_running:
            self.status_indicator.setStyleSheet("color: #4CAF50; font-size: 16px;")
        elif status == "failed":
            self.status_indicator.setStyleSheet("color: #F44336; font-size: 16px;")
        else:
            self.status_indicator.setStyleSheet("color: #9E9E9E; font-size: 16px;")
        
        # Update stats text
        uptime = stats.get('uptime', 'N/A')
        pid = stats.get('pid', 'N/A')
        self.stats_label.setText(f"Uptime: {uptime} | PID: {pid}")
        
        # Update resource usage
        cpu = stats.get('cpu_percent', 0)
        mem = stats.get('memory_mb', 0)
        self.resource_label.setText(f"CPU: {cpu:.1f}% | RAM: {mem:.1f} MB")
        
        # Update button states
        if not self.is_systemd:
            self.start_btn.setEnabled(not is_running)
            self.stop_btn.setEnabled(is_running)
    
    def start_service(self):
        subprocess.run(['pkexec', 'systemctl', 'start', self.name], 
                      capture_output=True, timeout=10)
    
    def stop_service(self):
        subprocess.run(['pkexec', 'systemctl', 'stop', self.name], 
                      capture_output=True, timeout=10)
    
    def start_process(self):
        if self.name == 'librechat':
            librechat_path = Path.home() / '.local' / 'src' / 'LibreChat'
            if not librechat_path.exists():
                QMessageBox.warning(self, "Error", "LibreChat not found at ~/.local/src/LibreChat")
                return
            command = ['bash', '-c', 
                      f'source ~/.nvm/nvm.sh && cd {librechat_path} && npm run backend']
            self.process_thread = ProcessRunner(command)
            
        elif self.name == 'rag_api':
            rag_path = Path.home() / '.local' / 'src' / 'rag_api'
            if not rag_path.exists():
                QMessageBox.warning(self, "Error", "RAG API not found at ~/.local/src/rag_api")
                return
            command = ['bash', '-c',
                      f'cd {rag_path} && source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000']
            self.process_thread = ProcessRunner(command)
        
        if self.process_thread:
            self.process_thread.output_ready.connect(self.on_log_output)
            self.process_thread.process_started.connect(self.on_process_started)
            self.process_thread.process_finished.connect(self.on_process_finished)
            self.process_thread.start()
    
    def on_log_output(self, text):
        """Forward log output to parent dashboard"""
        log_text = f"[{self.display_name}] {text}"
        self.log_signal.emit(log_text)
    
    def on_process_started(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
    
    def stop_process(self):
        if self.process_thread and self.process_thread.isRunning():
            self.process_thread.stop_process()
            self.process_thread.wait()
        elif self.is_running:
            port = 3080 if self.name == 'librechat' else 8000
            try:
                for conn in psutil.net_connections():
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        proc = psutil.Process(conn.pid)
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            proc.kill()
                        break
            except:
                pass
    
    def on_process_finished(self, return_code):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)


class GraphWidget(QWidget):
    """Real-time line graph widget"""
    
    def __init__(self, title, color):
        super().__init__()
        self.title = title
        self.color = color
        self.max_points = 60
        self.data = deque(maxlen=self.max_points)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create chart
        self.series = QLineSeries()
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.chart.setTitle(self.title)
        self.chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self.chart.legend().hide()
        
        # Set axes
        self.axis_x = QValueAxis()
        self.axis_x.setRange(0, self.max_points)
        self.axis_x.setLabelFormat("%d")
        self.axis_x.setTitleText("Time (seconds)")
        
        self.axis_y = QValueAxis()
        self.axis_y.setRange(0, 100)
        self.axis_y.setLabelFormat("%.0f%%")
        
        self.chart.addAxis(self.axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(self.axis_y, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.axis_x)
        self.series.attachAxis(self.axis_y)
        
        # Create chart view
        from PyQt6.QtGui import QPainter
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setMinimumHeight(200)
        
        layout.addWidget(self.chart_view)
        self.setLayout(layout)
    
    def update_data(self, value):
        """Add new data point"""
        self.data.append(value)
        
        # Update series
        self.series.clear()
        for i, val in enumerate(self.data):
            self.series.append(i, val)


class DashboardTab(QWidget):
    """Main dashboard tab"""
    
    def __init__(self):
        super().__init__()
        self.service_cards = {}
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # System overview section
        system_group = QGroupBox("System Overview")
        system_layout = QGridLayout()
        
        # CPU usage
        cpu_label = QLabel("CPU Usage:")
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setMaximum(100)
        self.cpu_text = QLabel("0%")
        system_layout.addWidget(cpu_label, 0, 0)
        system_layout.addWidget(self.cpu_bar, 0, 1)
        system_layout.addWidget(self.cpu_text, 0, 2)
        
        # RAM usage
        ram_label = QLabel("RAM Usage:")
        self.ram_bar = QProgressBar()
        self.ram_bar.setMaximum(100)
        self.ram_text = QLabel("0 GB / 0 GB")
        system_layout.addWidget(ram_label, 1, 0)
        system_layout.addWidget(self.ram_bar, 1, 1)
        system_layout.addWidget(self.ram_text, 1, 2)
        
        # Disk usage
        disk_label = QLabel("Disk Usage:")
        self.disk_bar = QProgressBar()
        self.disk_bar.setMaximum(100)
        self.disk_text = QLabel("0 GB / 0 GB")
        system_layout.addWidget(disk_label, 2, 0)
        system_layout.addWidget(self.disk_bar, 2, 1)
        system_layout.addWidget(self.disk_text, 2, 2)
        
        system_group.setLayout(system_layout)
        layout.addWidget(system_group)
        
        # Services grid
        services_label = QLabel("Services")
        services_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(services_label)
        
        services_grid = QGridLayout()
        
        # Create service cards
        self.service_cards['mongodb'] = ServiceCard('mongodb', 'MongoDB', True)
        services_grid.addWidget(self.service_cards['mongodb'], 0, 0)
        
        self.service_cards['postgresql'] = ServiceCard('postgresql', 'PostgreSQL', True)
        services_grid.addWidget(self.service_cards['postgresql'], 0, 1)
        
        self.service_cards['meilisearch'] = ServiceCard('meilisearch', 'Meilisearch', True)
        services_grid.addWidget(self.service_cards['meilisearch'], 0, 2)
        
        self.service_cards['ollama'] = ServiceCard('ollama', 'Ollama', True)
        services_grid.addWidget(self.service_cards['ollama'], 1, 0)
        
        self.service_cards['rag_api'] = ServiceCard('rag_api', 'RAG API', False)
        services_grid.addWidget(self.service_cards['rag_api'], 1, 1)
        
        self.service_cards['librechat'] = ServiceCard('librechat', 'LibreChat', False)
        services_grid.addWidget(self.service_cards['librechat'], 1, 2)
        
        layout.addLayout(services_grid)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def update_system_stats(self, stats):
        """Update system statistics"""
        # CPU
        cpu = stats['cpu_percent']
        self.cpu_bar.setValue(int(cpu))
        self.cpu_text.setText(f"{cpu:.1f}%")
        
        # RAM
        ram_percent = stats['ram_percent']
        ram_used = stats['ram_used_gb']
        ram_total = stats['ram_total_gb']
        self.ram_bar.setValue(int(ram_percent))
        self.ram_text.setText(f"{ram_used:.1f} GB / {ram_total:.1f} GB")
        
        # Disk
        disk_percent = stats['disk_percent']
        disk_used = stats['disk_used_gb']
        disk_total = stats['disk_total_gb']
        self.disk_bar.setValue(int(disk_percent))
        self.disk_text.setText(f"{disk_used:.1f} GB / {disk_total:.1f} GB")
    
    def update_service_stats(self, service_name, stats):
        """Update service statistics"""
        if service_name in self.service_cards:
            self.service_cards[service_name].update_stats(stats)


class MonitoringTab(QWidget):
    """Monitoring tab with graphs"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create graphs
        self.cpu_graph = GraphWidget("CPU Usage Over Time", "#2196F3")
        self.ram_graph = GraphWidget("RAM Usage Over Time", "#4CAF50")
        
        layout.addWidget(self.cpu_graph)
        layout.addWidget(self.ram_graph)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def update_graphs(self, stats):
        """Update graph data"""
        if 'cpu_history' in stats and stats['cpu_history']:
            self.cpu_graph.update_data(stats['cpu_history'][-1])
        
        if 'ram_history' in stats and stats['ram_history']:
            self.ram_graph.update_data(stats['ram_history'][-1])


class LogsTab(QWidget):
    """Logs tab"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        label = QLabel("Service Logs")
        label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(label)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Courier New', monospace;
                font-size: 10px;
            }
        """)
        layout.addWidget(self.log_output)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self.log_output.clear)
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def append_log(self, text):
        """Append text to logs"""
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)
        self.log_output.insertPlainText(text)
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)


class PgAdminTab(QWidget):
    """pgAdmin database management tab"""
    
    def __init__(self):
        super().__init__()
        self.pgadmin_manager = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)  # Reduce margins
        layout.setSpacing(5)  # Reduce spacing
        
        # Header with controls
        header_layout = QHBoxLayout()
        
        label = QLabel("RAG Database Management (pgAdmin 4)")
        label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        header_layout.addWidget(label)
        
        header_layout.addStretch()
        
        self.start_btn = QPushButton("Start pgAdmin")
        self.start_btn.clicked.connect(self.start_pgadmin)
        header_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop pgAdmin")
        self.stop_btn.clicked.connect(self.stop_pgadmin)
        self.stop_btn.setEnabled(False)
        header_layout.addWidget(self.stop_btn)
        
        self.open_browser_btn = QPushButton("Open in Browser")
        self.open_browser_btn.clicked.connect(self.open_in_browser)
        self.open_browser_btn.setEnabled(False)
        header_layout.addWidget(self.open_browser_btn)
        
        layout.addLayout(header_layout)
        
        # Status row with connection info button
        status_row = QHBoxLayout()
        
        self.status_label = QLabel("Status: Not Running")
        self.status_label.setStyleSheet("color: #888888; font-weight: bold; font-size: 10px;")
        status_row.addWidget(self.status_label)
        
        status_row.addStretch()
        
        # Connection info button
        info_btn = QPushButton("Details")
        info_btn.setMaximumWidth(80)
        info_btn.clicked.connect(self.show_connection_info)
        status_row.addWidget(info_btn)
        
        layout.addLayout(status_row)
        
        # Web view for embedded pgAdmin (much larger)
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl("about:blank"))
        self.web_view.setMinimumHeight(600)  # Bigger minimum height
        layout.addWidget(self.web_view, stretch=10)  # Give it most of the space
        
        # Console output (smaller)
        console_label = QLabel("Console:")
        console_label.setStyleSheet("font-size: 9px;")
        layout.addWidget(console_label)
        
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMaximumHeight(100)  # Smaller console
        self.console_output.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Courier New', monospace;
                font-size: 8px;
            }
        """)
        layout.addWidget(self.console_output)
        
        self.setLayout(layout)
    
    def show_connection_info(self):
        """Show connection information popup"""
        info_text = """
<h3>pgAdmin Login</h3>
<p>Email: <b>admin@local.host</b><br>
Password: <b>admin@local.host</b></p>

<h3>PostgreSQL RAG Database</h3>
<p>Host: <b>localhost</b><br>
Port: <b>5432</b><br>
Database: <b>ragdb</b><br>
Username: <b>raguser</b><br>
Password: <b>ragpassword</b></p>
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("Connection Information")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(info_text)
        msg.exec()
    
    def start_pgadmin(self):
        """Start pgAdmin server"""
        if self.pgadmin_manager and self.pgadmin_manager.isRunning():
            QMessageBox.warning(self, "Already Running", "pgAdmin is already running")
            return
        
        self.pgadmin_manager = PgAdminManager()
        self.pgadmin_manager.status_updated.connect(self.on_status_updated)
        self.pgadmin_manager.output_ready.connect(self.append_console)
        self.pgadmin_manager.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.append_console("Starting pgAdmin 4...\n")
    
    def stop_pgadmin(self):
        """Stop pgAdmin server"""
        if self.pgadmin_manager:
            self.pgadmin_manager.stop()
            self.pgadmin_manager.wait()
            self.append_console("pgAdmin stopped\n")
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.open_browser_btn.setEnabled(False)
        self.status_label.setText("Status: Not Running")
        self.status_label.setStyleSheet("color: #888888; font-weight: bold;")
        self.web_view.setUrl(QUrl("about:blank"))
    
    def on_status_updated(self, is_running, url):
        """Handle pgAdmin status updates"""
        if is_running and url:
            self.status_label.setText(f"Status: Running at {url}")
            self.status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.open_browser_btn.setEnabled(True)
            
            # Load pgAdmin in web view
            QTimer.singleShot(3000, lambda: self.web_view.setUrl(QUrl(url)))
        else:
            self.status_label.setText("Status: Not Running")
            self.status_label.setStyleSheet("color: #888888; font-weight: bold;")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.open_browser_btn.setEnabled(False)
    
    def open_in_browser(self):
        """Open pgAdmin in external browser"""
        if self.pgadmin_manager and self.pgadmin_manager.pgadmin_url:
            try:
                subprocess.Popen(['xdg-open', self.pgadmin_manager.pgadmin_url])
            except:
                QMessageBox.warning(self, "Error", "Could not open browser")
    
    def append_console(self, text):
        """Append text to console output"""
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)
        self.console_output.insertPlainText(text)
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)


class LibreChatDashboard(QMainWindow):
    """Main dashboard window"""
    
    def __init__(self):
        super().__init__()
        self.system_monitor = None
        self.service_monitor = None
        self.init_ui()
        self.start_monitoring()
        self.connect_service_logs()
    
    def connect_service_logs(self):
        """Connect service card outputs to logs tab"""
        for service_name, card in self.dashboard_tab.service_cards.items():
            card.log_signal.connect(self.logs_tab.append_log)
            
            # Also add systemd service startup logs
            if card.is_systemd:
                pass  # Could fetch initial logs here if needed
    
    def init_ui(self):
        self.setWindowTitle("LibreChat Dashboard")
        self.setGeometry(100, 100, 1200, 900)
        
        # Set window icon
        icon = QIcon.fromTheme("network-server-database")
        if icon.isNull():
            for fallback in ["network-server", "server-database"]:
                icon = QIcon.fromTheme(fallback)
                if not icon.isNull():
                    break
        self.setWindowIcon(icon)
        
        self.set_dark_theme()
        
        # Menu bar
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        exit_action = file_menu.addAction("Exit")
        exit_action.triggered.connect(self.close)
        
        # Control menu
        control_menu = menubar.addMenu("Control")
        
        start_systemd_action = control_menu.addAction("Start Systemd Services")
        start_systemd_action.triggered.connect(self.start_systemd_services)
        
        start_all_action = control_menu.addAction("Start Everything")
        start_all_action.triggered.connect(self.start_everything)
        
        stop_all_action = control_menu.addAction("Stop All")
        stop_all_action.triggered.connect(self.stop_all)
        
        control_menu.addSeparator()
        
        open_librechat_action = control_menu.addAction("Open LibreChat")
        open_librechat_action.triggered.connect(self.open_librechat)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self.show_about)
        
        guide_action = help_menu.addAction("Button Guide")
        guide_action.triggered.connect(self.show_button_guide)
        
        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        
        # Title
        title = QLabel("LibreChat Dashboard")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)
        
        # Tabs
        self.tabs = QTabWidget()
        
        self.dashboard_tab = DashboardTab()
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        
        self.monitoring_tab = MonitoringTab()
        self.tabs.addTab(self.monitoring_tab, "Monitoring")
        
        self.logs_tab = LogsTab()
        self.tabs.addTab(self.logs_tab, "Logs")
        
        self.pgadmin_tab = PgAdminTab()
        self.tabs.addTab(self.pgadmin_tab, "RAG DB Management")
        
        main_layout.addWidget(self.tabs)
        
        # Quick action buttons
        actions_layout = QHBoxLayout()
        
        start_systemd_btn = QPushButton("Start Systemd Services")
        start_systemd_btn.clicked.connect(self.start_systemd_services)
        actions_layout.addWidget(start_systemd_btn)
        
        start_all_btn = QPushButton("Start Everything")
        start_all_btn.clicked.connect(self.start_everything)
        actions_layout.addWidget(start_all_btn)
        
        stop_all_btn = QPushButton("Stop All")
        stop_all_btn.clicked.connect(self.stop_all)
        actions_layout.addWidget(stop_all_btn)
        
        open_btn = QPushButton("Open LibreChat")
        open_btn.clicked.connect(self.open_librechat)
        actions_layout.addWidget(open_btn)
        
        main_layout.addLayout(actions_layout)
        
        central_widget.setLayout(main_layout)
    
    def set_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        self.setPalette(palette)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:pressed { background-color: #0a3d91; }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 3px;
                text-align: center;
                background-color: #2b2b2b;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
            }
            QGroupBox {
                border: 1px solid #555555;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
    
    def start_monitoring(self):
        # Start system monitor
        self.system_monitor = SystemMonitor()
        self.system_monitor.stats_updated.connect(self.update_system_stats)
        self.system_monitor.start()
        
        # Start service monitor
        self.service_monitor = ServiceMonitor()
        self.service_monitor.status_updated.connect(self.update_service_stats)
        self.service_monitor.logs_ready.connect(self.populate_systemd_logs)
        self.service_monitor.start()
    
    def populate_systemd_logs(self, service_name, logs):
        """Add systemd logs to logs tab"""
        formatted_logs = f"\n[{service_name.upper()}] --- Service Started ---\n{logs}\n"
        self.logs_tab.append_log(formatted_logs)
    
    def update_system_stats(self, stats):
        self.dashboard_tab.update_system_stats(stats)
        self.monitoring_tab.update_graphs(stats)
    
    def update_service_stats(self, service_name, stats):
        self.dashboard_tab.update_service_stats(service_name, stats)
    
    def start_systemd_services(self):
        services = ['mongodb', 'postgresql', 'meilisearch', 'ollama']
        try:
            command = ['pkexec', 'bash', '-c', 
                      ' && '.join([f'systemctl start {s}' for s in services])]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                QMessageBox.information(self, "Success", "Systemd services started!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start services: {str(e)}")
    
    def start_everything(self):
        self.start_systemd_services()
        QTimer.singleShot(2000, self._start_manual_processes)
    
    def _start_manual_processes(self):
        if 'rag_api' in self.dashboard_tab.service_cards:
            self.dashboard_tab.service_cards['rag_api'].start_process()
        QTimer.singleShot(3000, self._start_librechat)
    
    def _start_librechat(self):
        if 'librechat' in self.dashboard_tab.service_cards:
            self.dashboard_tab.service_cards['librechat'].start_process()
    
    def stop_all(self):
        reply = QMessageBox.question(
            self, "Stop All Services?",
            "This will gracefully stop all services.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for name in ['librechat', 'rag_api']:
                if name in self.dashboard_tab.service_cards:
                    widget = self.dashboard_tab.service_cards[name]
                    if widget.is_running:
                        widget.stop_process()
            
            services = ['ollama', 'meilisearch', 'postgresql', 'mongodb']
            try:
                command = ['pkexec', 'bash', '-c',
                          ' && '.join([f'systemctl stop {s}' for s in services])]
                subprocess.run(command, capture_output=True, text=True, timeout=30)
                QMessageBox.information(self, "Complete", "All services stopped!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed: {str(e)}")
    
    def open_librechat(self):
        try:
            subprocess.Popen(['xdg-open', 'http://localhost:3080'])
        except:
            QMessageBox.warning(self, "Error", "Could not open browser")
    
    def show_about(self):
        about_text = """
<h2>LibreChat Dashboard</h2>
<p>Version 3.0</p>

<p>A modern dashboard for managing LibreChat services with real-time monitoring.</p>

<p><b>Features:</b></p>
<ul>
<li>Real-time resource monitoring with graphs</li>
<li>Service cards with CPU/RAM usage</li>
<li>One-click service management</li>
<li>Live system statistics</li>
<li>Integrated log viewer</li>
</ul>

<p><b>GitHub:</b> <a href="https://github.com/XclusivVv/librechat-dashboard">github.com/XclusivVv/librechat-dashboard</a></p>
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("About")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(about_text)
        msg.exec()
    
    def show_button_guide(self):
        guide_text = """
<h2>Dashboard Guide</h2>

<h3>Tabs</h3>
<p><b>Dashboard:</b> Overview of all services and system resources<br>
<b>Monitoring:</b> Real-time CPU and RAM usage graphs<br>
<b>Logs:</b> Consolidated log output from services<br>
<b>RAG DB Management:</b> pgAdmin4 PostgreSQL Browser for RAG Database</p>

<h3>Quick Actions</h3>
<p><b>Start Systemd Services:</b> Start database and AI services<br>
<b>Start Everything:</b> Start all services in sequence<br>
<b>Stop All:</b> Gracefully stop all running services<br>
<b>Open LibreChat:</b> Launch in browser</p>

<h3>Service Cards</h3>
<p>Each card shows:
<ul>
<li>Current status (green=running, gray=stopped, red=failed)</li>
<li>Uptime and Process ID</li>
<li>CPU and RAM usage in real-time</li>
<li>Start/Stop controls</li>
</ul>
</p>
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("Guide")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(guide_text)
        msg.exec()
    
    def closeEvent(self, event):
        if self.system_monitor:
            self.system_monitor.stop()
            self.system_monitor.quit()
            self.system_monitor.wait()
        
        if self.service_monitor:
            self.service_monitor.stop()
            self.service_monitor.quit()
            self.service_monitor.wait()
        
        # Stop pgAdmin if running
        if hasattr(self, 'pgadmin_tab') and self.pgadmin_tab.pgadmin_manager:
            if self.pgadmin_tab.pgadmin_manager.isRunning():
                self.pgadmin_tab.pgadmin_manager.stop()
                self.pgadmin_tab.pgadmin_manager.wait()
        
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LibreChat Dashboard")
    window = LibreChatDashboard()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
