# Mapbox Optimizer

## Overview

A PyQt5-based desktop app for optimizing carpool routes using Mapbox APIs. Features driver/rider route visualization, rider matching scores (detour time, distance, closest distance to route), and dynamic ride management with minimal API calls.

## Requirements

- Python 3.8+
- Dependencies: `PyQt5`, `requests`, `folium`, `IPython`, `PyQtWebEngine`
- Valid Mapbox Access Token
- Icons: `add_icon.png`, `remove_icon.png`, `down_arrow.png` (or update paths in `driver_route_app.py`)

## Setup

1. **Clone Repo**:
   ```bash
   git clone https://github.com/skanderayoub/mapbox_optimizer.git
   cd mapbox_optimizer
   ```

2. **Create Anaconda Environment**:
   ```bash
   conda create -n mapbox_optimizer python=3.8
   conda activate mapbox_optimizer
   ```

3. **Install Dependencies**:
   ```bash
   conda install pyqt requests
   pip install folium IPython PyQtWebEngine
   ```

4. **Mapbox Token**:
   - Set `MAPBOX_ACCESS_TOKEN` in `models.py`:
     ```python
     MAPBOX_ACCESS_TOKEN = "your_token_here"
     ```
   - Get token from [Mapbox](https://www.mapbox.com/).

5. **Icons**:
   - Add icon files to project root or use PyQt5 standard icons.

## Usage

1. **Run**:
   ```bash
   python driver_route_app.py
   ```

2. **Functionality**:
   - **Driver/Rider Selection**: Choose via dropdowns; riders sorted by matching score.
   - **Add/Remove Riders**: Updates ride and scores dynamically.
   - **Map**: Shows driver route, rider pickups, and potential rider routes.
   - **Scores**: Based on detour time, detour distance, and closest distance to driver's route.

## Structure

- `driver_route_app.py`: PyQt5 GUI, driver/rider generation, UI logic.
- `models.py`: Core logic (`MapboxOptimizer`, `Driver`, `Rider`, `Ride`, `RideManager`, `MapVisualizer`), route calculations, and scoring.
- `README.md`: Developer guide.

## Config

- **Score Weights** (`models.py`):
  ```python
  w1, w2, w3 = 0.4, 0.3, 0.3  # Detour time, closest distance, detour distance
  ```
- **Normalization**:
  - `max_closest_distance`: 50 km (adjust in `calculate_matching_score`).
  - `max_detour_minutes`: 20-50 min (random per driver).
- **Test Data**:
  - Edit `num_drivers`, `num_riders` in `generate_random_drivers_and_riders`.

## Notes

- **API Efficiency**: Caches rider/driver routes; one `calculate_optimized_route` call per score, reused in ride updates.
- **Logging**: `logging.DEBUG` for route/API errors.
- **Performance**: Optimize score calculation for many riders by caching if needed.
- **Troubleshooting**:
  - Check token validity for API errors.
  - Ensure icons exist or update paths.
  - Verify `temp_driver_route.html` for map issues.

## License

MIT License. See [LICENSE](LICENSE).

## Contributions

Open issues/PRs for bugs or enhancements.