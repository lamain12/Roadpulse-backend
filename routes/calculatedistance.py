from math import radians, sin, cos, sqrt, atan2

def calculate_distance(lat1, lng1, lat2, lng2):
    """
    Calculate the distance between two geographical points using the Haversine formula.
    Returns the distance in meters.
    """
    R = 6371000  # Radius of the Earth in meters
    dLat = radians(lat2 - lat1)
    dLng = radians(lng2 - lng1)
    a = sin(dLat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dLng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c