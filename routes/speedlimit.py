from fastapi import APIRouter, HTTPException, requests
from model import SpeedLimitRequest, RouteSpeedLimitRequest, SpeedLimitWarningRequest
from config import GOOGLE_ROADS_API_KEY
router = APIRouter()


async def get_road_type_estimation(lat: float, lng: float):
    """
    Get speed limit estimation based on road type (Malaysian standards)
    """
    try:
        # Query for road types without requiring speed limits
        lat_offset = 0.001  # roughly 100 meters
        lng_offset = 0.001
        
        bbox = f"{lat - lat_offset},{lng - lng_offset},{lat + lat_offset},{lng + lng_offset}"
        
        overpass_query = f"""
        [out:json][timeout:10];
        (
          way["highway"]({bbox});
        );
        out geom;
        """
        
        url = "https://overpass-api.de/api/interpreter"
        response = requests.post(url, data=overpass_query, timeout=10)
        
        if response.status_code != 200:
            print(f"Road type query failed: {response.status_code}")
            return {
                "speed_limit_kmh": "N/A",
                "speed_limit_mph": "N/A",
                "source": "api_error",
                "confidence": "none"
            }
        
        data = response.json()
        elements = data.get("elements", [])
        
        if not elements:
            print("No roads found for estimation")
            return {
                "speed_limit_kmh": "N/A",
                "speed_limit_mph": "N/A",
                "source": "no_roads",
                "confidence": "none"
            }
        
        # Find closest road by type
        closest_road = None
        min_distance = float('inf')
        
        for element in elements:
            if 'geometry' in element and 'tags' in element:
                highway_type = element['tags'].get('highway')
                if highway_type and element['geometry']:
                    # Calculate distance to road
                    road_lat = element['geometry'][0]['lat']
                    road_lng = element['geometry'][0]['lon']
                    distance = ((lat - road_lat) ** 2 + (lng - road_lng) ** 2) ** 0.5
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_road = element
        
        if not closest_road:
            return {
                "speed_limit_kmh": "N/A",
                "speed_limit_mph": "N/A",
                "source": "no_road_data",
                "confidence": "none"
            }
        
        # Estimate speed based on Malaysian road types
        highway_type = closest_road['tags'].get('highway', '').lower()
        
        # Malaysian speed limit standards
        speed_estimates = {
            'motorway': 110,        # Federal highways
            'trunk': 90,            # Main roads
            'primary': 80,          # Primary roads
            'secondary': 60,        # Secondary roads  
            'tertiary': 50,         # Local main roads
            'residential': 30,      # Housing areas
            'living_street': 25,    # Taman areas
            'unclassified': 40,     # Minor roads
            'service': 20,          # Service roads
            'track': 25,            # Rural tracks
        }
        
        # Get estimated speed
        estimated_speed = speed_estimates.get(highway_type, 50)  # Default to 50
        
        print(f"Road type: {highway_type}, Estimated speed: {estimated_speed} km/h")
        
        mph = round(estimated_speed * 0.621371, 1)
        
        return {
            "speed_limit_kmh": estimated_speed,
            "speed_limit_mph": mph,
            "source": f"estimated_{highway_type}",
            "confidence": "medium"
        }
        
    except Exception as e:
        print(f"Road type estimation error: {str(e)}")
        return {
            "speed_limit_kmh": "N/A",
            "speed_limit_mph": "N/A",
            "source": "estimation_error",
            "confidence": "none"
        }

@router.post("/api/speed-limit")
async def get_speed_limit(request: SpeedLimitRequest):
    """
    Get speed limit with proper fallback system:
    1. Try OpenStreetMap Overpass API for real speed limit data (HIGH confidence)
    2. If that fails, fall back to road type estimation (MEDIUM confidence)
    3. If all fails, return N/A
    """
    
    # STEP 1: Try to get REAL speed limit data from OpenStreetMap Overpass API
    try:
        print(f"🔍 STEP 1: Trying to fetch REAL speed limit data...")
        print(f"📍 Coordinates: {request.lat}, {request.lng}")
        
        # Create a bounding box around the point (about 50m radius)
        lat_offset = 0.0005  # roughly 50 meters
        lng_offset = 0.0005
        
        bbox = f"{request.lat - lat_offset},{request.lng - lng_offset},{request.lat + lat_offset},{request.lng + lng_offset}"
        
        # Overpass API query for roads with speed limits
        overpass_query = f"""
        [out:json][timeout:5];
        (
          way["highway"]["maxspeed"]({bbox});
        );
        out geom;
        """
        
        url = "https://overpass-api.de/api/interpreter"
        
        response = requests.post(url, data=overpass_query, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            elements = data.get("elements", [])
            
            if elements:
                print(f"✅ Found {len(elements)} roads with speed limit data!")
                
                # Find the closest road with speed limit
                closest_road = None
                min_distance = float('inf')
                
                for element in elements:
                    if 'geometry' in element and 'tags' in element:
                        maxspeed = element['tags'].get('maxspeed')
                        if maxspeed:
                            # Calculate distance to road (simplified - use first point)
                            if element['geometry']:
                                road_lat = element['geometry'][0]['lat']
                                road_lng = element['geometry'][0]['lon']
                                
                                # Simple distance calculation
                                distance = ((request.lat - road_lat) ** 2 + (request.lng - road_lng) ** 2) ** 0.5
                                
                                if distance < min_distance:
                                    min_distance = distance
                                    closest_road = element
                
                if closest_road:
                    maxspeed = closest_road['tags']['maxspeed']
                    print(f"🎯 Found closest road with speed limit: {maxspeed}")
                    
                    # Parse speed limit
                    try:
                        if maxspeed.isdigit():
                            # Plain number (assume km/h)
                            kmh = int(maxspeed)
                        elif 'mph' in maxspeed.lower():
                            # Convert mph to km/h
                            mph_value = int(maxspeed.lower().replace('mph', '').strip())
                            kmh = round(mph_value * 1.60934)
                        elif 'km/h' in maxspeed.lower() or 'kmh' in maxspeed.lower():
                            # Extract km/h value
                            kmh = int(''.join(filter(str.isdigit, maxspeed)))
                        else:
                            # Try to extract any number
                            import re
                            numbers = re.findall(r'\d+', maxspeed)
                            if numbers:
                                kmh = int(numbers[0])
                            else:
                                raise ValueError("No valid speed found")
                        
                        mph = round(kmh * 0.621371, 1)
                        
                        print(f"🎉 SUCCESS: REAL speed limit found!")
                        print(f"✅ RESULT: {kmh} km/h (source: openstreetmap_real)")
                        print(f"🎯 Confidence: HIGH (real speed limit data)")
                        print(f"─" * 50)
                        
                        return {
                            "speed_limit_kmh": kmh,
                            "speed_limit_mph": mph,
                            "source": "openstreetmap_real",
                            "confidence": "high"
                        }
                        
                    except (ValueError, TypeError):
                        print(f"❌ Could not parse speed limit: {maxspeed}")
                        print(f"🔄 FALLBACK: No valid speed data, trying estimation...")
                else:
                    print(f"⚠️  Found roads but no valid speed limit data")
                    print(f"🔄 FALLBACK: Trying estimation...")
            else:
                print(f"⚠️  No roads with speed limits found in area")
                print(f"🔄 FALLBACK: Trying estimation...")
        else:
            print(f"❌ Overpass API error: {response.status_code}")
            print(f"🔄 FALLBACK: API failed, trying estimation...")
            
    except Exception as e:
        print(f"❌ Overpass API failed: {str(e)}")
        print(f"🔄 FALLBACK: Exception occurred, trying estimation...")
    
    # STEP 2: FALLBACK - Use road type estimation
    print(f"🔍 STEP 2: Using road type estimation as fallback...")
    
    try:
        # Use Nominatim (free) to identify the road/area type
        nominatim_url = f"https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": request.lat,
            "lon": request.lng,
            "format": "json",
            "zoom": 18,  # High detail for road-level info
            "addressdetails": 1,
            "extratags": 1
        }
        headers = {
            "User-Agent": "RoadPulse/1.0"
        }
        
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=5)
        
        if response.status_code != 200:
            print(f"❌ Nominatim API error: {response.status_code}")
            return get_location_based_estimate(request.lat, request.lng)
        
        data = response.json()
        
        # Extract road information
        address = data.get("address", {})
        display_name = data.get("display_name", "")
        
        # Analyze location for speed estimation
        road_name = (address.get("road") or "").lower()
        
        print(f"📍 Location: {display_name}")
        print(f"🛣️  Road name: '{road_name}'")
        
        if not road_name:
            print("⚠️  WARNING: No road name found in address data")
            print(f"❌ FINAL RESULT: N/A (no road data available)")
            print(f"─" * 50)
            return {
                "speed_limit_kmh": "N/A",
                "speed_limit_mph": "N/A", 
                "source": "no_road_found",
                "confidence": "none"
            }
        
        # Malaysian road classification patterns
        estimated_speed = 50  # Default
        source = "estimated_location"
        
        # Highway patterns
        if any(highway in road_name for highway in ['highway', 'lebuhraya', 'expressway', 'plus']):
            estimated_speed = 110
            source = "highway_estimation"
        
        # Federal roads (route numbers)
        elif any(federal in road_name for federal in ['federal', 'route']):
            estimated_speed = 90
            source = "federal_road_estimation"
        
        # Jalan patterns (main roads)
        elif road_name.startswith('jalan'):
            # Check for specific road types
            if any(main in road_name for main in ['utama', 'besar', 'raya']):
                estimated_speed = 60
                source = "main_road_estimation"
            else:
                estimated_speed = 50
                source = "local_road_estimation"
        
        # Residential areas
        elif any(residential in road_name for residential in ['taman', 'perumahan', 'housing']):
            estimated_speed = 30
            source = "residential_estimation"
        
        # Small roads
        elif any(small in road_name for small in ['lorong', 'lane']):
            estimated_speed = 25
            source = "small_road_estimation"
        
        # Check address components for additional context
        if address.get("suburb") and "taman" in address.get("suburb", "").lower():
            estimated_speed = min(estimated_speed, 30)  # Cap at 30 for residential areas
            source = "residential_area_estimation"
        
        mph = round(estimated_speed * 0.621371, 1)
        
        print(f"✅ ESTIMATION RESULT: {estimated_speed} km/h (source: {source})")
        print(f"🎯 Confidence: MEDIUM (estimated from road pattern)")
        print(f"─" * 50)
        
        return {
            "speed_limit_kmh": estimated_speed,
            "speed_limit_mph": mph,
            "source": source,
            "confidence": "medium"
        }
        
    except Exception as e:
        print(f"❌ ERROR: Estimation also failed: {str(e)}")
        print(f"🔄 FINAL FALLBACK: Using coordinate-based estimation")
        return get_location_based_estimate(request.lat, request.lng)

def get_location_based_estimate(lat: float, lng: float):
    """
    Fallback estimation based on coordinate patterns (Malaysia-specific)
    """
    print(f"🗺️  COORDINATE FALLBACK:")
    print(f"📍 Coordinates: {lat}, {lng}")
    
    # For Malaysian coordinates, make educated guesses
    # This is a simple fallback when all APIs fail
    
    # Urban centers (KL, Selangor) - more likely to be urban roads
    if (3.0 <= lat <= 3.3) and (101.5 <= lng <= 101.8):  # Klang Valley area
        print(f"🏙️  Detected: Klang Valley urban area")
        print(f"✅ FALLBACK RESULT: 50 km/h (urban area estimate)")
        print(f"─" * 50)
        return {
            "speed_limit_kmh": 50,
            "speed_limit_mph": 31,
            "source": "urban_area_estimate",
            "confidence": "low"
        }
    
    # Default for other areas
    print(f"🌾 Detected: General Malaysian area")
    print(f"✅ FALLBACK RESULT: 60 km/h (general estimate)")
    print(f"─" * 50)
    return {
        "speed_limit_kmh": 60,
        "speed_limit_mph": 37,
        "source": "general_estimate", 
        "confidence": "low"
    }

@router.post("/api/route-speed-limits")
async def get_route_speed_limits(request: RouteSpeedLimitRequest):
    """
    Get speed limits for multiple points along a route
    """
    try:
        if not request.coordinates:
            raise HTTPException(status_code=400, detail="No coordinates provided")
        
        # Limit to 100 points to avoid API rate limits
        coordinates = request.coordinates[:100]
        
        # Build path string for Google Roads API
        path_points = "|".join([f"{coord[0]},{coord[1]}" for coord in coordinates])
        
        url = "https://roads.googleapis.com/v1/speedLimits"
        params = {
            "path": path_points,
            "key": GOOGLE_ROADS_API_KEY
        }
        
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            # Return estimated speed limits for each point
            return {
                "speed_limits": [
                    {
                        "lat": coord[0],
                        "lng": coord[1],
                        "speed_limit_kmh": "N/A",
                        "speed_limit_mph": "N/A",
                        "source": "unavailable"
                    }
                    for coord in coordinates
                ],
                "total_points": len(coordinates),
                "source": "unavailable"
            }
        
        data = response.json()
        speed_limits = data.get("speedLimits", [])
        
        # Map speed limits to coordinates
        result_limits = []
        for i, coord in enumerate(coordinates):
            if i < len(speed_limits):
                speed_limit = speed_limits[i]
                kmh = speed_limit.get("speedLimit", 50)
                mph = round(kmh * 0.621371, 1)
                source = "google_roads"
            else:
                kmh = "N/A"
                mph = "N/A"
                source = "unavailable"
            
            result_limits.append({
                "lat": coord[0],
                "lng": coord[1],
                "speed_limit_kmh": kmh,
                "speed_limit_mph": mph,
                "source": source
            })
        
        return {
            "speed_limits": result_limits,
            "total_points": len(result_limits),
            "source": "mixed"
        }
        
    except Exception as e:
        print(f"Route speed limits API error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
# Speed Limit Warning Logic
async def check_speed_warning(lat: float, lng: float, current_speed: float):
    """
    Check if current speed exceeds the road speed limit and generate warning
    """
    try:
        print(f"🚨 SPEED WARNING CHECK:")
        print(f"📍 Location: {lat}, {lng}")
        print(f"🚗 Current Speed: {current_speed} km/h")
        
        # Get the road speed limit
        speed_limit_request = SpeedLimitRequest(lat=lat, lng=lng)
        speed_limit_data = await get_speed_limit(speed_limit_request)
        
        road_speed_limit = speed_limit_data.get("speed_limit_kmh")
        
        # Check if we got a valid speed limit
        if road_speed_limit == "N/A" or not isinstance(road_speed_limit, (int, float)):
            print(f"⚠️ No valid speed limit data available")
            return {
                "warning": False,
                "message": "Speed limit data unavailable",
                "current_speed": current_speed,
                "speed_limit": "N/A",
                "excess_speed": 0,
                "warning_level": "none",
                "source": speed_limit_data.get("source", "unknown"),
                "confidence": speed_limit_data.get("confidence", "none")
            }
        
        # Compare speeds
        excess_speed = current_speed - road_speed_limit
        warning_level = "none"
        message = "Speed within limit"
        
        if excess_speed > 0:
            message = f"Speed limit exceeded by {excess_speed} km/h"
        else:
            message = "Speed within limit"
        
        print(f"🛣️ Road Speed Limit: {road_speed_limit} km/h")
        print(f"📊 Excess Speed: {excess_speed} km/h")
        print(f"💬 Message: {message}")
        print(f"─" * 50)
        
        return {
            "warning": excess_speed > 0,
            "message": message,
            "current_speed": current_speed,
            "speed_limit": road_speed_limit,
            "excess_speed": excess_speed,
            "warning_level": "exceeded" if excess_speed > 0 else "none",
            "source": speed_limit_data.get("source", "unknown"),
            "confidence": speed_limit_data.get("confidence", "none"),
            "should_beep": excess_speed > 0
        }
        
    except Exception as e:
        print(f"❌ Speed warning check error: {str(e)}")
        return {
            "warning": False,
            "message": f"Error checking speed warning: {str(e)}",
            "current_speed": current_speed,
            "speed_limit": "N/A",
            "excess_speed": 0,
            "source": "error",
            "confidence": "none"
        }

# Speed Limit Warning API Endpoint
@router.post("/api/speed-warning")
async def get_speed_warning(request: SpeedLimitWarningRequest):
    """
    Check if current speed exceeds road speed limit and return warning
    """
    try:
        print(f"🚨 SPEED WARNING API CALLED:")
        print(f"📍 Coordinates: {request.lat}, {request.lng}")
        print(f"🚗 Current Speed: {request.current_speed} km/h")
        print(f"─" * 50)
        
        # Validate input
        if request.current_speed < 0:
            raise HTTPException(status_code=400, detail="Current speed cannot be negative")
        
        if request.current_speed > 200:
            raise HTTPException(status_code=400, detail="Current speed seems unrealistic (>200 km/h)")
        
        # Validate coordinates
        if not (-90 <= request.lat <= 90):
            raise HTTPException(status_code=400, detail="Invalid latitude: must be between -90 and 90")
        
        if not (-180 <= request.lng <= 180):
            raise HTTPException(status_code=400, detail="Invalid longitude: must be between -180 and 180")
        
        # Malaysia-specific coordinate validation (rough bounds)
        if not (1.0 <= request.lat <= 7.0) or not (100.0 <= request.lng <= 119.0):
            print(f"⚠️ WARNING: Coordinates outside typical Malaysia bounds: {request.lat}, {request.lng}")
        
        # Call the speed warning logic
        warning_result = await check_speed_warning(
            lat=request.lat,
            lng=request.lng,
            current_speed=request.current_speed
        )
        
        print(f"✅ SPEED WARNING API COMPLETED SUCCESSFULLY")
        print(f"─" * 50)
        
        return warning_result
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"❌ SPEED WARNING API ERROR: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal server error: {str(e)}"
        )