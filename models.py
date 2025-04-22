import requests
import uuid
from typing import List, Optional, Dict, Tuple
from IPython.display import display
import folium
import folium.plugins

MAPBOX_OPTIMIZATION_API_URL = "https://api.mapbox.com/optimized-trips/v1/mapbox/driving-traffic/"
MAPBOX_DIRECTIONS_API_URL = "https://api.mapbox.com/directions/v5/mapbox/driving-traffic/"
MAPBOX_ACCESS_TOKEN = "pk.eyJ1IjoicGVuZGxhIiwiYSI6ImNtOXNuNjV2NjAyNjYyanM5M2Fjb24xYTAifQ.7RqcSLC1TxVWdeZMj8QkTw"

class MapboxOptimizer:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.map_matching_url = "https://api.mapbox.com/matching/v5/mapbox/driving/"

    def calculate_direct_route(self, start: List[float], end: List[float]) -> Optional[Dict]:
        """Calculate direct route from start to end using Mapbox Directions API."""
        coords_str = f"{start[1]},{start[0]};{end[1]},{end[0]}"
        url = f"{MAPBOX_DIRECTIONS_API_URL}{coords_str}?geometries=geojson&access_token={self.access_token}"

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
            print("No valid route found in response.")
            return None
        except requests.RequestException as e:
            print(f"Error calculating direct route: {e}")
            return None

    def calculate_optimized_route(self, coordinates: List[List[float]]) -> Optional[Dict]:
        if len(coordinates) < 2 or len(coordinates) > 12:
            print(f"Invalid number of waypoints: {len(coordinates)}. Must be 2-12.")
            return None

        coords_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
        url = f"{MAPBOX_OPTIMIZATION_API_URL}{coords_str}?geometries=geojson&source=first&destination=last&roundtrip=false&access_token={self.access_token}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("trips"):
                trip = data["trips"][0]
                waypoint_indices = data.get("waypoints", [])
                if len(waypoint_indices) != len(coordinates):
                    print(f"Error: waypoint_indices length ({len(waypoint_indices)}) does not match coordinates ({len(coordinates)})")
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
            print("No valid trip found in response.")
            return None
        except requests.RequestException as e:
            print(f"Error calculating optimized route: {e}")
            return None

    def match_route_to_roads(self, coordinates: List[List[float]]) -> Optional[Dict]:
        """Use Mapbox Map Matching API to snap coordinates to the road network."""
        if not coordinates or len(coordinates) < 2:
            print("Invalid coordinates for map matching.")
            return None

        if len(coordinates) > 100:
            print(f"Too many coordinates ({len(coordinates)}). Reducing to 100.")
            coordinates = coordinates[::len(coordinates)//100 + 1][:100]

        coords_str = ";".join(f"{lon},{lat}" for lat, lon in coordinates)
        radiuses = ";".join(["50"] * len(coordinates))
        url = f"{self.map_matching_url}{coords_str}?geometries=geojson&access_token={self.access_token}&steps=true&radiuses={radiuses}"

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
            print(f"No valid matching found in response. Response: {data}")
            return None
        except requests.RequestException as e:
            print(f"Error in map matching: {e}. Response: {response.text if 'response' in locals() else 'No response'}")
            return None


class User:
    """Base class for users (drivers or riders)."""
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
        self.ride = self._create_solo_ride(optimizer)

    def _create_solo_ride(self, optimizer: 'MapboxOptimizer') -> 'Ride':
        """Create a solo ride for the driver during initialization."""
        direct_route = optimizer.calculate_direct_route(self.home, self.workplace)
        if not direct_route:
            raise ValueError(f"Failed to compute direct route for {self.name}")

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
    """Class for riders."""
    def __init__(self, name: str, home: List[float], workplace: List[float], workplace_name: str):
        super().__init__(name, home, workplace, workplace_name)
        self.role = 'rider'

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
        """Return ordered stops with names and coordinates."""
        names = [self.driver.name] + [rider.name for rider in self.riders] + [self.driver.workplace_name]
        coords = [self.start] + self.stops + [self.destination]
        if len(self.waypoint_order) != len(names):
            print(f"Warning: waypoint_order length ({len(self.waypoint_order)}) does not match stops ({len(names)})")
            # Fallback to default order if waypoint_order is invalid
            return [(names[i], coords[i]) for i in range(len(names))]
        return [(names[idx], coords[idx]) for idx in self.waypoint_order]

    def update_ride(self, riders: List[Rider], route: Dict, direct_duration: float, optimizer: MapboxOptimizer = None) -> None:
        """Update ride with new riders, route, and matched geometry."""
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
            ordered_coords = [[lat, lon] for lon, lat in route['geometry']]
            matched_route = optimizer.match_route_to_roads(ordered_coords)
            self.matched_geometry = matched_route['geometry'] if matched_route else route['geometry']
        else:
            self.matched_geometry = route.get('geometry', [])

class MapVisualizer:
    """Handles map creation using Folium."""
    @staticmethod
    def create_map(ride: Ride) -> folium.Map:
        """Create a map with driver, riders, and optimized road-snapped route."""
        all_coords = [ride.start] + ride.stops + [ride.destination]
        avg_lat = sum(coord[0] for coord in all_coords) / len(all_coords)
        avg_lon = sum(coord[1] for coord in all_coords) / len(all_coords)

        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=12)

        folium.Marker(
            location=ride.start,
            popup=f"Driver: {ride.driver.name}",
            icon=folium.Icon(color='blue')
        ).add_to(m)

        for rider, stop in zip(ride.riders, ride.stops):
            folium.Marker(
                location=stop,
                popup=f"Rider: {rider.name}",
                icon=folium.Icon(color='green')
            ).add_to(m)

        folium.Marker(
            location=ride.destination,
            popup=f"Workplace: {ride.driver.workplace_name}",
            icon=folium.Icon(color='red')
        ).add_to(m)

        if ride.matched_geometry:
            route_coords = [[lat, lon] for lon, lat in ride.matched_geometry]
            folium.plugins.AntPath(
                locations=route_coords,
                color="purple",
                weight=5,
                delay=1000,
                dash_array=[10, 20],
                pulse_color="yellow"
            ).add_to(m)

        return m

class RideManager:
    """Manages ride assignments and updates."""
    def __init__(self, optimizer: MapboxOptimizer):
        self.optimizer = optimizer
        self.failed_attempts = []  # Store failed attempt messages

    def add_rider_to_ride(self, ride: Ride, new_rider: Rider) -> bool:
        """Attempt to add a rider to an existing ride, respecting max detour and max riders."""
        if new_rider.workplace != ride.driver.workplace:
            self.failed_attempts.append(f"Rider {new_rider.name} does not match workplace {ride.driver.workplace_name}")
            print(f"Rider {new_rider.name} does not match workplace {ride.driver.workplace_name}")
            return False

        if new_rider.ride:
            self.failed_attempts.append(f"Rider {new_rider.name} already has a ride")
            print(f"Rider {new_rider.name} already has a ride.")
            return False

        if len(ride.riders) >= ride.driver.max_riders:
            self.failed_attempts.append(f"Driver {ride.driver.name}'s ride is full (max {ride.driver.max_riders} riders)")
            print(f"Driver {ride.driver.name}'s ride is full (max {ride.driver.max_riders} riders).")
            return False

        max_allowed_duration = ride.direct_duration + ride.driver.max_detour_minutes
        new_riders = ride.riders + [new_rider]
        coordinates = [ride.start] + [rider.home for rider in new_riders] + [ride.destination]
        new_route = self.optimizer.calculate_optimized_route(coordinates)

        if not new_route or new_route['duration'] > max_allowed_duration:
            self.failed_attempts.append(f"Adding {new_rider.name} exceeds max detour of {ride.driver.max_detour_minutes} minutes")
            print(f"Adding {new_rider.name} exceeds max detour of {ride.driver.max_detour_minutes} minutes.")
            return False

        ride.update_ride(new_riders, new_route, ride.direct_duration, self.optimizer)
        new_rider.ride = ride
        for rider in ride.riders:
            rider.ride = ride
        ride.driver.ride = ride
        return True

    @staticmethod
    def _format_coords(coords: List[float]) -> str:
        """Format coordinates as (lat, lon) with 6 decimal places."""
        return f"({coords[0]:.6f}, {coords[1]:.6f})"

    def display_ride_info(self, ride: Ride) -> None:
        """Display detailed and formatted ride information."""
        print("\n" + "="*60)
        print(f"Ride Summary for {ride.driver.name}")
        print("="*60 + "\n")
        
        # General Information
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

        # Pickup Order
        print("Pickup Order:")
        ordered_stops = ride.get_ordered_stops()
        for i, (name, coords) in enumerate(ordered_stops, 1):
            role = "Driver" if name == ride.driver.name else "Workplace" if name == ride.driver.workplace_name else "Rider"
            print(f"{i}. {name} ({role}) at {self._format_coords(coords)}")
        print()

        # Segment Durations
        print("Segment Durations:")
        for i, duration in enumerate(ride.leg_durations):
            start_name = ordered_stops[i][0]
            end_name = ordered_stops[i+1][0]
            print(f"- {start_name} to {end_name}: {duration:.2f} minutes")
        print()

        # Failed Attempts (if any)
        if self.failed_attempts:
            print("Failed Assignment Attempts:")
            for attempt in self.failed_attempts:
                print(f"- {attempt}")
            self.failed_attempts = []  # Clear after displaying
            print()

        # Map Visualization
        print("Generating Route Map...")
        visualizer = MapVisualizer()
        map_object = visualizer.create_map(ride)
        display(map_object)