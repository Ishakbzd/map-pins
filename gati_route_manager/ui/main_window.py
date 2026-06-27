import os
import subprocess
import traceback
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QFont
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.csv_exporter import export_routes
from core.deduplicator import deduplicate, MultiPackageStop
from core.geocoder import geocode_routes
from core.map_generator import generate_map_html
from core.pdf_parser import parse_pdf
from models.route import Route


class DropZone(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setStyleSheet("""
            DropZone {
                border: 3px dashed #888;
                border-radius: 12px;
                background-color: #f5f5f5;
            }
            DropZone:hover {
                border-color: #4a90d9;
                background-color: #e8f0fe;
            }
        """)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel("Drop PDF manifest here\nor click to browse")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #666; font-size: 16px; border: none;")
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.file_path: Optional[str] = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.file_path = path
                self.label.setText(os.path.basename(path))
                self.window()._on_pdf_dropped(path)
                return

    def mousePressEvent(self, event):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF manifest", "", "PDF files (*.pdf)"
        )
        if path:
            self.file_path = path
            self.label.setText(os.path.basename(path))
            self.window()._on_pdf_dropped(path)


class RouteCheckboxItem(QWidget):
    def __init__(self, route: Route, parent=None):
        super().__init__(parent)
        self.route = route
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        self.checkbox = QCheckBox(f"{route.code}  ({route.total_packages} pkgs)")
        self.checkbox.setChecked(True)
        self.checkbox.setStyleSheet("font-size: 14px; color: #000; background: transparent;")
        layout.addWidget(self.checkbox)
        layout.addStretch()
        self.setLayout(layout)
        self.setStyleSheet("background: #fff;")


class ResultsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: #fff;
            }
            QTabBar::tab {
                padding: 6px 16px;
                font-size: 13px;
                border: 1px solid #ddd;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                background: #f0f0f0;
                color: #000;
            }
            QTabBar::tab:selected {
                background: #fff;
                font-weight: bold;
            }
        """)

        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(4, 4, 4, 4)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                color: #000;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 13px;
            }
        """)
        summary_layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.open_folder_btn = QPushButton("Open output folder")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 16px;
                font-size: 13px;
                border: 1px solid #4a90d9;
                border-radius: 4px;
                background-color: #e8f0fe;
                color: #000;
            }
            QPushButton:hover {
                background-color: #d0e2fd;
            }
        """)
        btn_layout.addWidget(self.open_folder_btn)
        summary_layout.addLayout(btn_layout)

        self.tabs.addTab(summary_tab, "Summary")

        map_tab = QWidget()
        map_layout = QVBoxLayout(map_tab)
        map_layout.setContentsMargins(4, 4, 4, 4)
        self.map_view = QWebEngineView()
        self.map_view.setHtml(
            "<p style='color:#666;font-family:sans-serif;padding:20px;'>"
            "Export routes first to see map preview.</p>"
        )
        map_layout.addWidget(self.map_view)
        self.tabs.addTab(map_tab, "Map")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self._output_dir: Optional[str] = None

    def set_output_dir(self, path: str):
        self._output_dir = path
        self.open_folder_btn.setEnabled(True)

    def clear_results(self):
        self.text_edit.clear()
        self.map_view.setHtml(
            "<p style='color:#666;font-family:sans-serif;padding:20px;'>"
            "Export routes first to see map preview.</p>"
        )
        self._output_dir = None
        self.open_folder_btn.setEnabled(False)

    def set_map_html(self, html: str):
        self.map_view.setHtml(html)


class GeocodeWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(dict)  # coords_map

    def __init__(self, routes: List[Route], parent=None):
        super().__init__(parent)
        self.routes = routes

    def run(self):
        coords = geocode_routes(
            self.routes,
            on_progress=lambda c, t, l: self.progress.emit(c, t, l),
        )
        self.done.emit(coords)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GATI Route Manager")
        self.setMinimumSize(700, 520)
        self.resize(750, 600)

        self._routes: List[Route] = []
        self._route_widgets: List[RouteCheckboxItem] = []
        self._output_dir: Optional[str] = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("GATI Route Manager")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin-bottom: 4px;")
        main_layout.addWidget(title)

        self.drop_zone = DropZone(self)
        main_layout.addWidget(self.drop_zone)

        route_section = QVBoxLayout()
        route_label = QLabel("Routes found in this file:")
        route_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #555;")
        route_section.addWidget(route_label)

        self.route_list = QListWidget()
        self.route_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 4px;
                background-color: white;
            }
            QListWidget::item {
                border-bottom: 1px solid #eee;
                padding: 2px;
            }
        """)
        self.route_list.setMaximumHeight(150)
        route_section.addWidget(self.route_list)
        main_layout.addLayout(route_section)

        export_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export & preview on map")
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 28px;
                font-size: 15px;
                font-weight: bold;
                background-color: #4a90d9;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:disabled {
                background-color: #b0b0b0;
            }
        """)
        export_layout.addStretch()
        export_layout.addWidget(self.export_btn)
        export_layout.addStretch()
        main_layout.addLayout(export_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4a90d9;
                border-radius: 3px;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        results_label = QLabel("Results:")
        results_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #555;")
        main_layout.addWidget(results_label)

        self.results_panel = ResultsPanel()
        main_layout.addWidget(self.results_panel, stretch=1)

        self.results_panel.open_folder_btn.clicked.connect(self._open_output_folder)
        self.export_btn.clicked.connect(self._on_export)

        self._exported_routes: List[Route] = []

    def _on_pdf_dropped(self, path: str):
        self._routes = []
        self._route_widgets = []
        self.route_list.clear()
        self.results_panel.clear_results()
        self.export_btn.setEnabled(False)

        try:
            routes = parse_pdf(path)
            if not routes:
                QMessageBox.warning(self, "No routes", "No GATI routes found in this file.")
                return

            self._routes = routes
            for route in routes:
                widget = RouteCheckboxItem(route)
                item = QListWidgetItem()
                item.setSizeHint(widget.sizeHint())
                self.route_list.addItem(item)
                self.route_list.setItemWidget(item, widget)
                self._route_widgets.append(widget)

            self.export_btn.setEnabled(True)

        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Parse error",
                f"Could not read this PDF. Make sure it is an Intelcom manifest.\n\n{exc}",
            )

    def _on_export(self):
        selected = [
            w.route for w in self._route_widgets
            if w.checkbox.isChecked()
        ]

        if not selected:
            QMessageBox.information(self, "No routes", "Select at least one route to export.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not output_dir:
            return

        self._output_dir = output_dir
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFormat("Exporting files...")

        QTimer.singleShot(50, lambda: self._do_export_files(selected, output_dir))

    def _do_export_files(self, routes: List[Route], output_dir: str):
        try:
            export_routes(routes, output_dir)
            self.results_panel.set_output_dir(output_dir)
            self._exported_routes = routes

            report_lines = []
            for route in routes:
                result = deduplicate(route)
                report_lines.append(
                    f"{route.code} -- {result.total_packages} packages / "
                    f"{result.unique_stops} stops"
                )
                if result.multi_package_stops:
                    report_lines.append("  Multi-package stops:")
                    for stop in result.multi_package_stops:
                        seqs = ", ".join(str(s) for s in stop.seqs)
                        report_lines.append(
                            f"    {stop.street}, {stop.city} "
                            f"QC {stop.postal_code}  x{stop.package_count} "
                            f"(seq {seqs})"
                        )
                report_lines.append("")

            self.results_panel.text_edit.setText("\n".join(report_lines))
            self.results_panel.tabs.setCurrentIndex(0)
            self.results_panel.tabs.setTabEnabled(1, False)

            self.export_btn.setText("Geocoding...")
            self.progress_bar.setFormat("Geocoding...")
            self.progress_bar.setValue(0)

            self._geocode_worker = GeocodeWorker(routes, self)
            self._geocode_worker.progress.connect(self._on_geocode_progress)
            self._geocode_worker.done.connect(self._on_geocode_done)
            self._geocode_worker.start()

        except Exception as exc:
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Export error",
                f"Failed to export routes:\n\n{exc}",
            )
            self.progress_bar.setVisible(False)
            self.export_btn.setEnabled(True)

    def _on_geocode_progress(self, current: int, total: int, label: str):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Geocoding {current}/{total}: {label}")

    def _on_geocode_done(self, coords: dict):
        try:
            if coords:
                map_html = generate_map_html(self._exported_routes, coords)
                self.results_panel.set_map_html(map_html)
                self.results_panel.tabs.setTabEnabled(1, True)
                self.results_panel.tabs.setCurrentIndex(1)
            else:
                self.results_panel.set_map_html(
                    "<p style='color:#666;font-family:sans-serif;padding:20px;'>"
                    "Could not geocode any addresses for map preview.</p>"
                )
        except Exception as exc:
            traceback.print_exc()
            QMessageBox.warning(self, "Map error", str(exc))
        finally:
            self.progress_bar.setVisible(False)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setFormat("%p%")
            self.export_btn.setText("Export & preview on map")
            self.export_btn.setEnabled(True)

    def _open_output_folder(self):
        if self._output_dir and os.path.isdir(self._output_dir):
            subprocess.Popen(["explorer", self._output_dir])
