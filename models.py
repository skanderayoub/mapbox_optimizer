import requests
import uuid
import logging
import math
from typing import List, Optional, Dict, Tuple
from IPython.display import display
import folium
import folium.plugins

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

MAPBOX_OPTIMIZATION_API_URL = "https://api.mapbox.com/optimized-trips/v1/mapbox/driving-traffic/"
MAPBOX_DIRECTIONS_API_URL = "https://api.mapbox.com/directions/v5/mapbox/driving-traffic/"
MAPBOX_ACCESS_TOKEN = "pk.eyJ1IjoicGVuZGxhIiwiYSI6ImNtOXNuNjV2NjAyNjYyanM5M2Fjb24xYTAifQ.7RqcSLC1TxVWdeZMj8QkTw"

class MapboxOptimizer:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.map_matching_url = "https://api.mapbox.com/matching/v5/mapbox/driving/"

    def calculate_direct_route(self, start: List[float], end: List[float]) -> Optional[Dict]:
        coords_str = f"{start[1]},{start[0]};{end[1]},{end[0]}"
        url = f"{MAPBOX_DIRECTIONS_API_URL}{coords_str}?geometries=geojson&overview=full&access_token={self.access_token}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("routes"):
                route = data["routes"][0]
                return {
                    "distance": route["distance"] / 1000,
                    "duration": route["duration"] / 60,
                    "geometry": route["geometry"]["coordinates"],
                }
            logging.warning(f"No valid route found in response: {data}")
            return None
        except requests.RequestException as e:
            logging.error(f"Error calculating direct route from {start} to {end}: {e}")
            return None

    def calculate_optimized_route(self, coordinates: List[List[float]]) -> Optional[Dict]:
        if len(coordinates) < 2 or len(coordinates) > 12:
            logging.warning(f"Invalid number of waypoints: {len(coordinates)}. Must be 2-12.")
            return None

        coords_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
        url = f"{MAPBOX_OPTIMIZATION_API_URL}{coords_str}?geometries=geojson&overview=full&source=first&destination=last&roundtrip=false&access_token={self.access_token}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("trips"):
                trip = data["trips"][0]
                waypoint_indices = data.get("waypoints", [])
                if len(waypoint_indices) != len(coordinates):
                    logging.error(f"waypoint_indices length ({len(waypoint_indices)}) does not match coordinates ({len(coordinates)})")
                    return None
                legs = trip.get("legs", [])
                leg_durations = [leg["duration"] / 60 for leg in legs]
                result = {
                    "geometry": trip["geometry"]["coordinates"],
                    "distance": trip["distance"] / 1000,
                    "duration": trip["duration"] / 60,
                    "waypoint_indices": [wp["waypoint_index"] for wp in waypoint_indices],
                    "leg_durations": leg_durations
                }
                return result
            logging.warning(f"No valid trip found in response: {data}")
            return None
        except requests.RequestException as e:
            logging.error(f"Error calculating optimized route: {e}")
            return None

    def match_route_to_roads(self, coordinates: List[List[float]]) -> Optional[Dict]:
        if not coordinates or len(coordinates) < 2:
            logging.warning("Invalid coordinates for map matching.")
            return None

        if len(coordinates) > 100:
            logging.info(f"Too many coordinates ({len(coordinates)}). Reducing to 100.")
            coordinates = coordinates[::len(coordinates)//100 + 1][:100]

        coords_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
        radiuses = ";".join(["50"] * len(coordinates))
        url = f"{self.map_matching_url}{coords_str}?geometries=geojson&overview=full&access_token={self.access_token}&steps=true&radiuses={radiuses}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("matchings"):
                matching = data["matchings"][0]
                return {
                    "geometry": matching["geometry"]["coordinates"],
                    "distance": matching["distance"] / 1000,
                    "duration": matching["duration"] / 60,
                }
            logging.warning(f"No valid matching found in response: {data}")
            return None
        except requests.RequestException as e:
            logging.error(f"Error in map matching: {e}. Response: {response.text if 'response' in locals() else 'No response'}")
            return None


class User:
    def __init__(self, name: str, home: List[float], workplace: List[float], workplace_name: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.home = home
        self.workplace = workplace
        self.workplace_name = workplace_name
        self._ride = None

    @property
    def ride(self) -> Optional['Ride']:
        return self._ride

    @ride.setter
    def ride(self, ride: Optional['Ride']) -> None:
        self._ride = ride

class Driver(User):
    def __init__(self, name: str, home: List[float], workplace: List[float], workplace_name: str, max_detour_minutes: float, max_riders: int, optimizer: 'MapboxOptimizer'):
        super().__init__(name, home, workplace, workplace_name)
        self.role = 'driver'
        self.max_detour_minutes = max_detour_minutes
        self.max_riders = max_riders
        self.optimizer = optimizer
        try:
            self.ride = self._create_solo_ride(optimizer)
            if self.ride is None:
                logging.error(f"Failed to create solo ride for {name}: No route returned")
                raise ValueError("No valid route for solo ride")
        except Exception as e:
            logging.error(f"Failed to create solo ride for {name}: {e}")
            self.ride = None

    def _create_solo_ride(self, optimizer: 'MapboxOptimizer') -> 'Ride':
        direct_route = optimizer.calculate_direct_route(self.home, self.workplace)
        if not direct_route:
            logging.error(f"Failed to compute direct route for {self.name} from {self.home} to {self.workplace}")
            raise ValueError(f"Cannot compute direct route for {self.name}")

        geometry = direct_route['geometry']
        route = {
            'distance': direct_route['distance'],
            'duration': direct_route['duration'],
            'waypoint_indices': [0, 1],
            'leg_durations': [direct_route['duration']],
            'geometry': direct_route['geometry'],
            'matched_geometry': geometry
        }
        ride = Ride(self, [], route, direct_route['duration'])
        ride.matched_geometry = geometry
        return ride

class Rider(User):
    def __init__(self, name: str, home: List[float], workplace: List[float], workplace_name: str, optimizer: 'MapboxOptimizer'):
        super().__init__(name, home, workplace, workplace_name)
        self.role = 'rider'
        self.optimizer = optimizer
        self.direct_route = self._create_direct_route(optimizer)

    def _create_direct_route(self, optimizer: 'MapboxOptimizer') -> Optional[Dict]:
        try:
            direct_route = optimizer.calculate_direct_route(self.home, self.workplace)
            if not direct_route:
                logging.error(f"Failed to compute direct route for rider {self.name} from {self.home} to {self.workplace}")
                return None
            return direct_route
        except Exception as e:
            logging.error(f"Error creating direct route for rider {self.name}: {e}")
            return None

class Ride:
    def __init__(self, driver: Driver, riders: List[Rider], route: Dict, direct_duration: float):
        self.driver = driver
        self.riders = riders
        self.start = driver.home
        self.stops = [rider.home for rider in riders]
        self.destination = driver.workplace
        self.route = route
        self.matched_geometry = route.get('matched_geometry', route.get('geometry', []))
        self.distance = route.get('distance', 0.0)
        self.duration = route.get('duration', 0.0)
        self.direct_duration = direct_duration
        self.detour = self.duration - direct_duration if self.duration > direct_duration else 0.0
        self.waypoint_order = route.get('waypoint_indices', [])
        self.leg_durations = route.get('leg_durations', [])

    def get_ordered_stops(self) -> List[Tuple[str, List[float]]]:
        names = [self.driver.name] + [rider.name for rider in self.riders] + [self.driver.workplace_name]
        coords = [self.start] + self.stops + [self.destination]
        if len(self.waypoint_order) != len(names):
            logging.warning(f"waypoint_order length ({len(self.waypoint_order)}) does not match stops ({len(names)})")
            return [(names[i], coords[i]) for i in range(len(names))]
        return [(names[idx], coords[idx]) for idx in self.waypoint_order]

    def update_ride(self, riders: List[Rider], route: Dict, direct_duration: float, optimizer: MapboxOptimizer = None) -> None:
        self.riders = riders
        self.stops = [rider.home for rider in riders]
        self.route = route
        self.distance = route.get('distance', 0.0)
        self.duration = route.get('duration', 0.0)
        self.direct_duration = direct_duration
        self.detour = self.duration - direct_duration if self.duration > direct_duration else 0.0
        self.waypoint_order = route.get('waypoint_indices', [])
        self.leg_durations = route.get('leg_durations', [])

        if optimizer and route.get('geometry'):
            try:
                ordered_coords = [[lat, lon] for lon, lat in route['geometry']]
                matched_route = optimizer.match_route_to_roads(ordered_coords)
                self.matched_geometry = matched_route['geometry'] if matched_route else route['geometry']
            except Exception as e:
                logging.error(f"Error matching route to roads: {e}")
                self.matched_geometry = route.get('geometry', [])
        else:
            self.matched_geometry = route.get('geometry', [])

class MapVisualizer:
    @staticmethod
    def create_map(ride: Ride, rider: Optional[Rider] = None) -> folium.Map:
        try:
            all_coords = [ride.start] + ride.stops + [ride.destination]
            if rider:
                all_coords.extend([rider.home, rider.workplace])

            m = folium.Map(
                location=[sum(coord[0] for coord in all_coords) / len(all_coords),
                          sum(coord[1] for coord in all_coords) / len(all_coords)],
                zoom_start=12,
                tiles="CartoDB Positron",
                attr="CartoDB Positron",
                zoom_control=False
            )

            minimap = folium.plugins.MiniMap()
            m.add_child(minimap)

            folium.Marker(
                location=ride.start,
                popup=f"<b>Driver: {ride.driver.name}</b><br>Start Location",
                tooltip=ride.driver.name,
                icon=folium.Icon(color='blue', icon='car', prefix='fa')
            ).add_to(m)

            for rider_in_ride, stop in zip(ride.riders, ride.stops):
                folium.Marker(
                    location=stop,
                    popup=f"<b>Rider: {rider_in_ride.name}</b><br>Pickup Location",
                    tooltip=rider_in_ride.name,
                    icon=folium.Icon(color='green', icon='user', prefix='fa')
                ).add_to(m)

            folium.Marker(
                location=ride.destination,
                popup=f"<b>Workplace: {ride.driver.workplace_name}</b><br>Destination",
                tooltip=ride.driver.workplace_name,
                icon=folium.Icon(color='red', icon='building', prefix='fa')
            ).add_to(m)

            route_bounds = []
            if ride.matched_geometry:
                route_coords = [[lat, lon] for lon, lat in ride.matched_geometry]
                folium.plugins.AntPath(
                    locations=route_coords,
                    color="#6a1b9a",
                    weight=6,
                    opacity=0.8,
                    delay=800,
                    dash_array=[10, 20],
                    pulse_color="#f3e5f5",
                    tooltip="Driver's Optimized Route"
                ).add_to(m)
                route_bounds.extend(route_coords)

            if rider and rider.direct_route and rider.direct_route.get('geometry'):
                if rider.home not in ride.stops:
                    folium.Marker(
                        location=rider.home,
                        popup=f"<b>Rider: {rider.name}</b><br>Potential Pickup",
                        tooltip=f"{rider.name} (Potential)",
                        icon=folium.Icon(color='orange', icon='user-plus', prefix='fa')
                    ).add_to(m)
                rider_route_coords = [[lat, lon] for lon, lat in rider.direct_route['geometry']]
                folium.PolyLine(
                    locations=rider_route_coords,
                    color="#388e3c",
                    weight=5,
                    opacity=0.7,
                    dash_array="5, 10",
                    tooltip=f"{rider.name}'s Direct Route"
                ).add_to(m)
                route_bounds.extend(rider_route_coords)

            if route_bounds:
                bounds = [
                    [min(lat for lat, lon in route_bounds), min(lon for lat, lon in route_bounds)],
                    [max(lat for lat, lon in route_bounds), max(lon for lat, lon in route_bounds)]
                ]
                m.fit_bounds(bounds, padding=(30, 30))

            legend_html = """
            <div style="position: fixed; bottom: 50px; left: 50px; z-index: 1000; padding: 10px; background-color: white; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
                <h4 style="margin: 0 0 10px 0;">Map Legend</h4>
                <p style="margin: 5px 0;"><i class="fa fa-car" style="color: blue;"></i> Driver Start</p>
                <p style="margin: 5px 0;"><i class="fa fa-user" style="color: green;"></i> Rider Pickup</p>
                <p style="margin: 5px 0;"><i class="fa fa-user-plus" style="color: orange;"></i> Potential Rider</p>
                <p style="margin: 5px 0;"><i class="fa fa-building" style="color: red;"></i> Workplace</p>
                <p style="margin: 5px 0;"><span style="border: 2px solid #6a1b9a;"></span> Driver's Route</p>
                <p style="margin: 5px 0;"><span style="border: 2px dashed #388e3c;"></span> Rider's Direct Route</p>
            </div>
            """
            m.get_root().html.add_child(folium.Element(legend_html))

            return m
        except Exception as e:
            logging.error(f"Error creating map: {e}")
            raise

class RideManager:
    def __init__(self, optimizer: MapboxOptimizer):
        self.optimizer = optimizer
        self.failed_attempts = []

    def calculate_matching_score(self, driver: Driver, rider: Rider) -> float:
        try:
            if rider.workplace != driver.workplace or rider.ride:
                return 0.0  # Ineligible rider

            # Calculate closest distance to ride geometry
            rider_home = rider.home
            closest_distance = float('inf')
            if driver.ride.matched_geometry:
                for lon, lat in driver.ride.matched_geometry:
                    dist = math.sqrt((rider_home[0] - lat)**2 + (rider_home[1] - lon)**2) * 111  # Approx km
                    closest_distance = min(closest_distance, dist)
            max_closest_distance = 50.0  # Normalize to 50 km

            # Simulate adding rider to ride
            max_allowed_duration = driver.ride.direct_duration + driver.max_detour_minutes
            new_riders = driver.ride.riders + [rider]
            coordinates = [driver.ride.start] + [r.home for r in new_riders] + [driver.ride.destination]
            new_route = self.optimizer.calculate_optimized_route(coordinates)

            if not new_route or new_route['duration'] > max_allowed_duration:
                return 0.0  # Route invalid or exceeds detour

            detour_time = new_route['duration'] - driver.ride.direct_duration
            detour_distance = new_route['distance'] - driver.ride.route.get('distance', 0.0)

            # Normalize components
            time_score = max(0.0, 1.0 - detour_time / driver.max_detour_minutes) if driver.max_detour_minutes > 0 else 0.0
            distance_score = max(0.0, 1.0 - detour_distance / driver.ride.route.get('distance', 1.0)) if driver.ride.route.get('distance', 1.0) > 0 else 0.0
            closest_distance_score = max(0.0, 1.0 - closest_distance / max_closest_distance) if max_closest_distance > 0 else 0.0

            # Weighted score (weights sum to 1)
            w1, w2, w3 = 0.7, 0.2, 0.1
            score = w1 * time_score + w2 * closest_distance_score + w3 * distance_score

            return min(max(score, 0.0), 1.0)  # Clamp to [0, 1]
        except Exception as e:
            logging.error(f"Error calculating matching score for {driver.name} and {rider.name}: {e}")
            return 0.0

    def add_rider_to_ride(self, ride: Ride, new_rider: Rider) -> bool:
        try:
            if new_rider.workplace != ride.driver.workplace:
                self.failed_attempts.append(f"Rider {new_rider.name} does not match workplace {ride.driver.workplace_name}")
                logging.warning(f"Rider {new_rider.name} does not match workplace {ride.driver.workplace_name}")
                return False

            if new_rider.ride:
                self.failed_attempts.append(f"Rider {new_rider.name} already has a ride")
                logging.warning(f"Rider {new_rider.name} already has a ride.")
                return False

            if len(ride.riders) >= ride.driver.max_riders:
                self.failed_attempts.append(f"Driver {ride.driver.name}'s ride is full (max {ride.driver.max_riders} riders)")
                logging.warning(f"Driver {ride.driver.name}'s ride is full (max {ride.driver.max_riders} riders).")
                return False

            max_allowed_duration = ride.direct_duration + ride.driver.max_detour_minutes
            new_riders = ride.riders + [new_rider]
            coordinates = [ride.start] + [rider.home for rider in new_riders] + [ride.destination]
            new_route = self.optimizer.calculate_optimized_route(coordinates)

            if not new_route or new_route['duration'] > max_allowed_duration:
                self.failed_attempts.append(f"Adding {new_rider.name} exceeds max detour of {ride.driver.max_detour_minutes} minutes")
                logging.warning(f"Adding {new_rider.name} exceeds max detour of {ride.driver.max_detour_minutes} minutes.")
                return False

            ride.update_ride(new_riders, new_route, ride.direct_duration, self.optimizer)
            new_rider.ride = ride
            for rider in ride.riders:
                rider.ride = ride
            ride.driver.ride = ride
            return True
        except Exception as e:
            logging.error(f"Error adding rider {new_rider.name} to ride: {e}")
            self.failed_attempts.append(f"Error adding {new_rider.name}: {str(e)}")
            return False

    def remove_rider_from_ride(self, ride: Ride, rider: Rider) -> bool:
        try:
            if rider not in ride.riders:
                logging.warning(f"Rider {rider.name} is not in the ride.")
                return False

            new_riders = [r for r in ride.riders if r != rider]
            coordinates = [ride.start] + [r.home for r in new_riders] + [ride.destination]

            if len(coordinates) == 2:
                new_route = self.optimizer.calculate_direct_route(ride.start, ride.destination)
                if not new_route:
                    logging.error(f"Failed to compute direct route for {ride.driver.name} after removing {rider.name}")
                    return False
                new_route = {
                    'distance': new_route['distance'],
                    'duration': new_route['duration'],
                    'waypoint_indices': [0, 1],
                    'leg_durations': [new_route['duration']],
                    'geometry': new_route['geometry'],
                    'matched_geometry': new_route['geometry']
                }
            else:
                new_route = self.optimizer.calculate_optimized_route(coordinates)
                if not new_route:
                    logging.error(f"Failed to compute optimized route after removing {rider.name}")
                    return False

            ride.update_ride(new_riders, new_route, ride.direct_duration, self.optimizer)
            rider.ride = None
            for r in ride.riders:
                r.ride = ride
            ride.driver.ride = ride
            return True
        except Exception as e:
            logging.error(f"Error removing rider {rider.name} from ride: {e}")
            return False

    @staticmethod
    def _format_coords(coords: List[float]) -> str:
        return f"({coords[0]:.6f}, {coords[1]:.6f})"

    def display_ride_info(self, ride: Ride) -> None:
        try:
            print("\n" + "="*60)
            print(f"Ride Summary for {ride.driver.name}")
            print("="*60 + "\n")
            
            print("General Information:")
            print(f"- Driver: {ride.driver.name}")
            print(f"- Workplace: {ride.driver.workplace_name} {self._format_coords(ride.driver.workplace)}")
            print(f"- Max Riders: {ride.driver.max_riders}")
            print(f"- Max Detour: {ride.driver.max_detour_minutes:.2f} minutes")
            print(f"- Riders: {', '.join(rider.name for rider in ride.riders) if ride.riders else 'None'}")
            print(f"- Total Distance: {ride.distance:.2f} km")
            print(f"- Total Duration: {ride.duration:.2f} minutes")
            print(f"- Detour: {ride.detour:.2f} minutes")
            print(f"- Direct Duration (no riders): {ride.direct_duration:.2f} minutes\n")

            print("Pickup Order:")
            ordered_stops = ride.get_ordered_stops()
            for i, (name, coords) in enumerate(ordered_stops, 1):
                role = "Driver" if name == ride.driver.name else "Workplace" if name == ride.driver.workplace_name else "Rider"
                print(f"{i}. {name} ({role}) at {self._format_coords(coords)}")
            print()

            print("Segment Durations:")
            for i, duration in enumerate(ride.leg_durations):
                start_name = ordered_stops[i][0]
                end_name = ordered_stops[i+1][0]
                print(f"- {start_name} to {end_name}: {duration:.2f} minutes")
            print()

            if self.failed_attempts:
                print("Failed Assignment Attempts:")
                for attempt in self.failed_attempts:
                    print(f"- {attempt}")
                self.failed_attempts = []
                print()
        except Exception as e:
            logging.error(f"Error displaying ride info: {e}")
            print(f"Error displaying ride info: {str(e)}")