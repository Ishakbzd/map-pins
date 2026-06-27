import os
import sys
import tempfile
import threading
import webbrowser
from typing import List, Optional

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button

from core.csv_exporter import export_routes
from core.deduplicator import deduplicate
from core.geocoder import geocode_routes
from core.map_generator import generate_map_html, save_map_html_file
from core.pdf_parser import parse_pdf
from models.route import Route

KV_DIR = os.path.join(os.path.dirname(__file__), "kv")


class GATIRouteApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._routes: List[Route] = []
        self._exported_routes: List[Route] = []
        self._route_checkboxes: List[tuple[Route, CheckBox]] = []
        self._map_html_path: Optional[str] = None
        self._output_dir: Optional[str] = None

    def build(self):
        self.title = "GATI Route Manager"
        kv_path = os.path.join(KV_DIR, "main.kv")
        if os.path.isfile(kv_path):
            return Builder.load_file(kv_path)
        from kivy.uix.label import Label
        return Label(text="KV file not found")

    def browse_file(self):
        try:
            from plyer import filechooser
            filechooser.open_file(
                filters=[("PDF files", "*.pdf")],
                on_selection=self._on_file_selected,
            )
        except ImportError:
            self._show_popup("Error", "plyer not available for file selection.")

    def _on_file_selected(self, selection):
        if not selection:
            return
        path = selection[0]
        Clock.schedule_once(lambda dt: self._load_pdf(path))

    def _load_pdf(self, path: str):
        self.root.ids.file_label.text = os.path.basename(path)
        self.root.ids.export_btn.disabled = True
        route_list_box = self.root.ids.route_list_box
        route_list_box.clear_widgets()
        self._routes = []
        self._route_checkboxes = []
        self.root.ids.results_label.text = ""

        try:
            routes = parse_pdf(path)
            if not routes:
                self._show_popup("No routes", "No GATI routes found in this file.")
                return

            self._routes = routes
            for route in routes:
                box = BoxLayout(size_hint_y=None, height=dp(40))
                cb = CheckBox(active=True, size_hint_x=None, width=dp(40))
                label = Label(
                    text=f"{route.code}  ({route.total_packages} pkgs)",
                    halign="left",
                    valign="middle",
                    text_size=(None, dp(36)),
                    color=(0, 0, 0, 1),
                )
                label.bind(size=lambda s, ws: setattr(s, 'text_size', (s.width, None)))
                box.add_widget(cb)
                box.add_widget(label)
                route_list_box.add_widget(box)
                self._route_checkboxes.append((route, cb))

            self.root.ids.export_btn.disabled = False

        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._show_popup("Parse error", f"Could not read this PDF.\n\n{exc}")

    def on_export(self):
        selected = [
            route for route, cb in self._route_checkboxes
            if cb.active
        ]
        if not selected:
            self._show_popup("No routes", "Select at least one route to export.")
            return

        try:
            from plyer import filechooser
            filechooser.choose_dir(on_selection=self._on_output_dir_selected)
        except ImportError:
            self._do_export_default_dir(selected)

    def _on_output_dir_selected(self, selection):
        if not selection:
            return
        output_dir = selection[0]
        selected = [
            route for route, cb in self._route_checkboxes
            if cb.active
        ]
        Clock.schedule_once(lambda dt: self._do_export(selected, output_dir))

    def _do_export_default_dir(self, selected):
        output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        self._do_export(selected, output_dir)

    def _do_export(self, routes: List[Route], output_dir: str):
        self._output_dir = output_dir
        self.root.ids.export_btn.disabled = True
        self.root.ids.results_label.text = "Exporting files..."
        self.root.ids.progress_bar.max = 100
        self.root.ids.progress_bar.value = 0

        try:
            export_routes(routes, output_dir)
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

            self.root.ids.results_label.text = "\n".join(report_lines)

            self.root.ids.progress_bar.value = 0
            self.root.ids.status_label.text = "Geocoding..."
            threading.Thread(
                target=self._geocode_worker,
                args=(routes,),
                daemon=True,
            ).start()

        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._show_popup("Export error", f"Failed to export routes:\n\n{exc}")
            self.root.ids.export_btn.disabled = False
            self.root.ids.results_label.text = ""

    def _geocode_worker(self, routes: List[Route]):
        def on_progress(current, total, label):
            Clock.schedule_once(lambda dt: self._update_progress(current, total, label))

        coords = geocode_routes(routes, on_progress=on_progress)
        Clock.schedule_once(lambda dt: self._on_geocode_done(coords))

    def _update_progress(self, current, total, label):
        self.root.ids.progress_bar.max = total
        self.root.ids.progress_bar.value = current
        self.root.ids.status_label.text = f"Geocoding {current}/{total}: {label}"

    def _on_geocode_done(self, coords: dict):
        try:
            if coords:
                map_html = generate_map_html(self._exported_routes, coords)
                html_path = os.path.join(
                    tempfile.gettempdir(),
                    "gati_route_map.html",
                )
                save_map_html_file(map_html, html_path)
                self._map_html_path = html_path
                self.root.ids.open_map_btn.disabled = False
                self.root.ids.open_map_btn.text = "Open map in browser"
            else:
                self.root.ids.results_label.text += (
                    "\n\nCould not geocode any addresses for map preview."
                )
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._show_popup("Map error", str(exc))
        finally:
            self.root.ids.progress_bar.value = 0
            self.root.ids.status_label.text = ""
            self.root.ids.export_btn.disabled = False

    def open_map(self):
        if self._map_html_path and os.path.isfile(self._map_html_path):
            webbrowser.open(f"file:///{os.path.abspath(self._map_html_path).replace(os.sep, '/')}")

    def _show_popup(self, title: str, message: str):
        Clock.schedule_once(lambda dt: self._do_show_popup(title, message))

    def _do_show_popup(self, title: str, message: str):
        from kivy.uix.popup import Popup
        from kivy.uix.label import Label
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        content.add_widget(Label(text=message))
        btn = Button(text="OK", size_hint_y=None, height=dp(40))
        content.add_widget(btn)
        popup = Popup(title=title, content=content, size_hint=(0.8, 0.4))
        btn.bind(on_release=popup.dismiss)
        popup.open()


if __name__ == "__main__":
    GATIRouteApp().run()
