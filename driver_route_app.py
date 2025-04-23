from models import MapboxOptimizer, Driver, Rider, RideManager, MapVisualizer, MAPBOX_ACCESS_TOKEN
import sys
import os
import folium
import io
import random
import logging
from contextlib import redirect_stdout
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QLabel, QPushButton, QMessageBox, QTextEdit
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, Qt
from PyQt5.QtGui import QFont, QIcon
from typing import List, Optional

# Set up logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

WORKPLACES = {
    "STIHL": [48.8315, 9.3095],
    "MERCEDES": [48.7833, 9.2250]
}

class DriverRouteApp(QMainWindow):
    def __init__(self, drivers: List[Driver], riders: List[Rider]):
        super().__init__()
        self.drivers = drivers
        self.riders = riders
        self.optimizer = MapboxOptimizer(MAPBOX_ACCESS_TOKEN)
        self.ride_manager = RideManager(self.optimizer)
        self.init_ui()
        self.current_map_file = None

    def init_ui(self):
        self.setWindowTitle("Driver Route Viewer")
        self.setGeometry(100, 100, 1000, 700)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f4f8;
            }
            QComboBox {
                padding: 8px;
                border: 1px solid #dcdcdc;
                border-radius: 5px;
                background-color: white;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: url(down_arrow.png);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                min-width: 250px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 5px;
                font-size: 13px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QLabel {
                font-size: 13px;
                color: #333;
            }
            QTextEdit {
                background-color: white;
                border: 1px solid #dcdcdc;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Roboto', sans-serif;
                font-size: 13px;
            }
            QWebEngineView {
                border: 1px solid #dcdcdc;
                border-radius: 5px;
                background-color: white;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        header_label = QLabel("Driver Route Planner")
        header_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        """)
        layout.addWidget(header_label)

        driver_row = QHBoxLayout()
        driver_label = QLabel("Driver:")
        driver_label.setFixedWidth(80)
        self.driver_combo = QComboBox()
        self.driver_combo.addItem("Select a driver", None)
        for driver in self.drivers:
            self.driver_combo.addItem(
                f"{driver.name} ({driver.workplace_name})", driver)
            self.driver_combo.setItemData(
                self.driver_combo.count() - 1,
                f"{driver.name} ({driver.workplace_name})",
                Qt.ToolTipRole
            )
        self.driver_combo.currentIndexChanged.connect(self.on_driver_selected)
        self.driver_combo.setMinimumWidth(250)
        self.driver_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.driver_info_label = QLabel("")
        self.driver_info_label.setStyleSheet("font-size: 13px; color: #555;")
        driver_row.addWidget(driver_label)
        driver_row.addWidget(self.driver_combo)
        driver_row.addWidget(self.driver_info_label)
        driver_row.addStretch(1)
        layout.addLayout(driver_row)

        rider_row = QHBoxLayout()
        rider_label = QLabel("Rider:")
        rider_label.setFixedWidth(80)
        self.rider_combo = QComboBox()
        self.rider_combo.addItem("Select a rider", None)
        for rider in self.riders:
            self.rider_combo.addItem(rider.name, rider)
            self.rider_combo.setItemData(
                self.rider_combo.count() - 1,
                rider.name,
                Qt.ToolTipRole
            )
        self.rider_combo.currentIndexChanged.connect(self.on_rider_selected)
        self.rider_combo.setMinimumWidth(250)
        self.rider_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.add_rider_button = QPushButton("Add Rider")
        self.add_rider_button.setIcon(QIcon("add_icon.png"))
        self.add_rider_button.clicked.connect(self.on_add_rider)
        self.add_rider_button.setEnabled(False)
        self.remove_rider_button = QPushButton("Remove Rider")
        self.remove_rider_button.setIcon(QIcon("remove_icon.png"))
        self.remove_rider_button.clicked.connect(self.on_remove_rider)
        self.remove_rider_button.setEnabled(False)
        rider_row.addWidget(rider_label)
        rider_row.addWidget(self.rider_combo)
        rider_row.addWidget(self.add_rider_button)
        rider_row.addWidget(self.remove_rider_button)
        rider_row.addStretch(1)
        layout.addLayout(rider_row)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)
        layout.setStretchFactor(self.web_view, 4)

        self.ride_info_text = QTextEdit()
        self.ride_info_text.setReadOnly(True)
        self.ride_info_text.setFixedHeight(200)
        layout.addWidget(self.ride_info_text)
        layout.setStretchFactor(self.ride_info_text, 1)

    def capture_ride_info(self, ride):
        if ride is None:
            logging.error("Attempted to capture ride info for None ride")
            return "Error: No ride available"
        try:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                self.ride_manager.display_ride_info(ride)
            return buffer.getvalue()
        except Exception as e:
            logging.error(f"Error capturing ride info: {e}")
            return f"Error displaying ride info: {str(e)}"

    def update_map(self, driver: Optional[Driver], rider: Optional[Rider]):
        if driver is None or driver.ride is None:
            logging.warning("No driver or ride available for map update")
            self.web_view.setHtml(
                "<h3>Please select a driver with a valid ride</h3>")
            return

        try:
            map_object = MapVisualizer.create_map(driver.ride, rider)
            temp_file = "temp_driver_route.html"
            map_object.save(temp_file)
            self.web_view.setUrl(QUrl.fromLocalFile(
                os.path.abspath(temp_file)))
            self.current_map_file = temp_file
        except Exception as e:
            logging.error(f"Error updating map: {e}")
            self.web_view.setHtml(f"<h3>Error rendering map: {str(e)}</h3>")

    def on_driver_selected(self, index):
        try:
            driver = self.driver_combo.itemData(index)
            logging.debug(
                f"Selected driver: {driver.name if driver else 'None'}")

            if driver is None:
                logging.debug("No driver selected")
                self.web_view.setHtml("<h3>Please select a driver</h3>")
                self.ride_info_text.setText("Please select a driver")
                self.driver_info_label.setText("")
                self.rider_combo.setCurrentIndex(0)
                self.add_rider_button.setEnabled(False)
                self.remove_rider_button.setEnabled(False)
                return

            if driver.ride is None:
                logging.warning(f"Driver {driver.name} has no valid ride")
                self.web_view.setHtml(
                    f"<h3>Error: No valid ride for {driver.name}</h3>")
                self.ride_info_text.setText(
                    f"Error: No valid ride for {driver.name}. Please try another driver.")
                self.driver_info_label.setText("No ride available")
                self.rider_combo.setCurrentIndex(0)
                self.add_rider_button.setEnabled(False)
                self.remove_rider_button.setEnabled(False)
                return

            has_riders = bool(driver.ride.riders)
            self.add_rider_button.setEnabled(True)
            self.remove_rider_button.setEnabled(has_riders)
            logging.debug(f"add_rider_button enabled: True, "
                          f"remove_rider_button enabled: {has_riders}")

            self.update_rider_dropdown(driver)
            self.update_map(driver, None)
            ride_info = self.capture_ride_info(driver.ride)
            self.ride_info_text.setText(ride_info)
            self.driver_info_label.setText(
                f"Duration: {driver.ride.duration:.2f} min | "
                f"Detour: {driver.ride.detour:.2f}/{driver.max_detour_minutes} min | "
                f"Riders: {len(driver.ride.riders)}/{driver.max_riders}"
            )
        except Exception as e:
            logging.error(f"Error in on_driver_selected: {e}")
            self.web_view.setHtml(f"<h3>Error: {str(e)}</h3>")
            self.ride_info_text.setText(f"Error selecting driver: {str(e)}")
            self.driver_info_label.setText("")
            self.rider_combo.setCurrentIndex(0)
            self.add_rider_button.setEnabled(False)
            self.remove_rider_button.setEnabled(False)

    def update_rider_dropdown(self, driver: Driver):
        try:
            current_rider = self.rider_combo.currentData()
            self.rider_combo.clear()
            self.rider_combo.addItem("Select a rider", None)

            eligible_riders = [
                rider for rider in self.riders
                if (rider.workplace == driver.workplace and
                    (rider.ride is None or rider in driver.ride.riders))
            ]
            rider_scores = []
            for rider in eligible_riders:
                score = self.ride_manager.calculate_matching_score(
                    driver, rider)
                rider_scores.append((rider, score))

            rider_scores.sort(key=lambda x: (-x[1], x[0].name))

            for rider, score in rider_scores:
                if rider in driver.ride.riders:
                    self.rider_combo.addItem(
                        f"{rider.name} (In Ride, Score: {score:.2f})", rider)
                else:
                    self.rider_combo.addItem(
                        f"{rider.name} (Score: {score:.2f})", rider)

            if current_rider:
                for i in range(self.rider_combo.count()):
                    if self.rider_combo.itemData(i) == current_rider:
                        self.rider_combo.setCurrentIndex(i)
                        break
        except Exception as e:
            logging.error(f"Error updating rider dropdown: {e}")
            self.rider_combo.clear()
            self.rider_combo.addItem("Select a rider", None)

    def on_rider_selected(self, index):
        try:
            driver = self.driver_combo.currentData()
            rider = self.rider_combo.itemData(index)
            if driver is None:
                self.rider_combo.setCurrentIndex(0)
                return

            self.update_map(
                driver, rider if rider and rider not in driver.ride.riders else None)
            has_rider_in_ride = bool(
                driver and rider and rider in driver.ride.riders)
            self.remove_rider_button.setEnabled(has_rider_in_ride)
            logging.debug(
                f"remove_rider_button enabled: {has_rider_in_ride} for rider: {rider.name if rider else 'None'}")
        except Exception as e:
            logging.error(f"Error in on_rider_selected: {e}")
            self.web_view.setHtml(f"<h3>Error: {str(e)}</h3>")

    def on_add_rider(self):
        try:
            driver_index = self.driver_combo.currentIndex()
            driver = self.driver_combo.itemData(driver_index)
            rider_index = self.rider_combo.currentIndex()
            rider = self.rider_combo.itemData(rider_index)

            if driver is None or rider is None:
                QMessageBox.warning(self, "Selection Error",
                                    "Please select both a driver and a rider.")
                return

            if rider in driver.ride.riders:
                QMessageBox.warning(
                    self, "Selection Error", f"{rider.name} is already in {driver.name}'s ride.")
                return

            success = self.ride_manager.add_rider_to_ride(driver.ride, rider)
            if success:
                QMessageBox.information(
                    self, "Success", f"Successfully added {rider.name} to {driver.name}'s ride.")
                self.update_map(driver, None)
                self.update_rider_dropdown(driver)
                ride_info = self.capture_ride_info(driver.ride)
                self.ride_info_text.setText(ride_info)
                self.driver_info_label.setText(
                    f"Duration: {driver.ride.duration:.2f} min | "
                    f"Detour: {driver.ride.detour:.2f}/{driver.max_detour_minutes} min | "
                    f"Riders: {len(driver.ride.riders)}/{driver.max_riders}"
                )
                has_rider_in_ride = rider in driver.ride.riders
                self.remove_rider_button.setEnabled(has_rider_in_ride)
                logging.debug(
                    f"remove_rider_button enabled after add: {has_rider_in_ride}")
            else:
                failed_message = self.ride_manager.failed_attempts[-1] if self.ride_manager.failed_attempts else "Unknown error"
                QMessageBox.critical(
                    self, "Failure", f"Failed to add {rider.name}: {failed_message}")
                ride_info = self.capture_ride_info(driver.ride)
                self.ride_info_text.setText(ride_info)
                self.ride_manager.failed_attempts.clear()
        except Exception as e:
            logging.error(f"Error in on_add_rider: {e}")
            QMessageBox.critical(
                self, "Error", f"Error adding rider: {str(e)}")

    def on_remove_rider(self):
        try:
            driver_index = self.driver_combo.currentIndex()
            driver = self.driver_combo.itemData(driver_index)
            rider_index = self.rider_combo.currentIndex()
            rider = self.rider_combo.itemData(rider_index)

            if driver is None or rider is None:
                QMessageBox.warning(self, "Selection Error",
                                    "Please select both a driver and a rider.")
                return

            if rider not in driver.ride.riders:
                QMessageBox.warning(
                    self, "Selection Error", f"{rider.name} is not in {driver.name}'s ride.")
                return

            success = self.ride_manager.remove_rider_from_ride(
                driver.ride, rider)
            if success:
                QMessageBox.information(
                    self, "Success", f"Successfully removed {rider.name} from {driver.name}'s ride.")
                self.update_map(driver, None)
                self.update_rider_dropdown(driver)
                ride_info = self.capture_ride_info(driver.ride)
                self.ride_info_text.setText(ride_info)
                self.driver_info_label.setText(
                    f"Duration: {driver.ride.duration:.2f} min | "
                    f"Detour: {driver.ride.detour:.2f}/{driver.max_detour_minutes} min | "
                    f"Riders: {len(driver.ride.riders)}/{driver.max_riders}"
                )
                self.remove_rider_button.setEnabled(False)
                logging.debug(
                    "remove_rider_button disabled after successful removal")
            else:
                QMessageBox.critical(
                    self, "Failure", f"Failed to remove {rider.name}: Unknown error")
                ride_info = self.capture_ride_info(driver.ride)
                self.ride_info_text.setText(ride_info)
        except Exception as e:
            logging.error(f"Error in on_remove_rider: {e}")
            QMessageBox.critical(
                self, "Error", f"Error removing rider: {str(e)}")

    def closeEvent(self, event):
        if self.current_map_file and os.path.exists(self.current_map_file):
            try:
                os.remove(self.current_map_file)
            except OSError:
                pass
        event.accept()

def generate_random_drivers_and_riders(optimizer, num_drivers=5, num_riders=8):
    lat_min, lat_max = 48.65, 48.95
    lon_min, lon_max = 8.95, 9.35

    first_names = [
        "Ahmed", "Mohamed", "Ali", "Hassan", "Mahmoud", "Youssef", "Omar", "Khaled",
        "Amine", "Kamel", "Fatma", "Aisha", "Zeineb", "Nour", "Sana", "Lina", "Hana",
        "Mariem", "Sami", "Mehdi", "Rami", "Nadia", "Sara", "Yasmin", "Hiba", "Mongi",
        "Fraj", "Kaisoun", "Tarek", "Imen", "Wassim", "Asma", "Bilel", "Souad",
        "Anis", "Rania", "Hamza", "Leila", "Firas", "Amal", "Zied", "Emna",
        "Karim", "Olfa", "Chaima", "Walid", "Ines", "Sofien"
    ]

    last_names = [
        "Ben Ali", "Trabelsi", "Jebali", "Mansouri", "Saidi", "Hammami",
        "Baccouche", "Chakroun", "Ghannouchi", "Zouari", "Tounsi", "Belhadj",
        "Karray", "Sfar", "Dridi", "Mejri", "Louati", "Saied",
        "Ayari", "Mathlouthi", "Marzouki", "Dhaouadi", "Belgacem",
        "Feriani", "Nafzaoui", "Mzali", "Sayyadi", "Stambouli",
        "Ayedi", "Ben Hassine", "Ben Romdhane", "Ben Yahia",
        "Bouazizi", "Arfaoui", "Bachiri"
    ]

    def generate_name():
        first = random.choice(first_names)
        last = random.choice(last_names)
        return f"{first} {last}"

    def snap_to_road(lat, lon):
        try:
            snapped_route = optimizer.match_route_to_roads([[lat, lon]])
            if snapped_route and snapped_route.get('geometry'):
                snapped_coords = snapped_route['geometry'][0]
                return [snapped_coords[1], snapped_coords[0]]
            else:
                logging.warning(f"Failed to snap [{lat}, {lon}] to road")
                return [lat, lon]
        except Exception as e:
            logging.error(f"Error snapping to road: {e}")
            return [lat, lon]

    drivers = []
    for i in range(num_drivers):
        name = generate_name()
        lat = random.uniform(lat_min, lat_max)
        lon = random.uniform(lon_min, lon_max)
        home = snap_to_road(lat, lon)
        workplace_name = random.choice(["STIHL", "MERCEDES"])
        workplace = WORKPLACES[workplace_name]
        max_detour = random.randint(20, 50)
        max_riders = random.randint(2, 4)
        try:
            driver = Driver(
                name=name,
                home=home,
                workplace=workplace,
                workplace_name=workplace_name,
                max_detour_minutes=max_detour,
                max_riders=max_riders,
                optimizer=optimizer
            )
            if driver.ride is not None:
                drivers.append(driver)
            else:
                logging.error(f"Skipping driver {name} due to invalid ride")
        except Exception as e:
            logging.error(f"Failed to create driver {name}: {e}")
            continue

    riders = []
    for i in range(num_riders):
        lat = random.uniform(lat_min, lat_max)
        lon = random.uniform(lon_min, lon_max)
        home = snap_to_road(lat, lon)
        workplace_name = random.choice(["STIHL", "MERCEDES"])
        workplace = WORKPLACES[workplace_name]
        name = generate_name()
        try:
            rider = Rider(
                name=name,
                home=home,
                workplace=workplace,
                workplace_name=workplace_name,
                optimizer=optimizer
            )
            if rider.direct_route is not None:
                riders.append(rider)
            else:
                logging.error(
                    f"Skipping rider {name} due to invalid direct route")
        except Exception as e:
            logging.error(f"Failed to create rider {name}: {e}")
            continue

    return drivers, riders

def main():
    optimizer = MapboxOptimizer(MAPBOX_ACCESS_TOKEN)
    try:
        drivers, riders = generate_random_drivers_and_riders(
            optimizer, num_drivers=10, num_riders=10)
        if not drivers:
            logging.error("No drivers generated successfully")
            QMessageBox.critical(
                None, "Error", "Failed to generate any drivers with valid rides. Check logs for details.")
            sys.exit(1)
        if not riders:
            logging.error("No riders generated successfully")
            QMessageBox.critical(
                None, "Error", "Failed to generate any riders with valid routes. Check logs for details.")
            sys.exit(1)
    except Exception as e:
        logging.error(f"Error generating drivers and riders: {e}")
        QMessageBox.critical(None, "Error", f"Failed to initialize: {str(e)}")
        sys.exit(1)

    app = QApplication(sys.argv)
    window = DriverRouteApp(drivers, riders)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()