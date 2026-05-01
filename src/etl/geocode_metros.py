"""
Populate latitude/longitude for metro geographies.

Uses a built-in lookup of major US city coordinates to geocode metros
based on the first city name in the metro name.

Usage:
    python -m src.etl.geocode_metros
"""
from __future__ import annotations

from src.db.connection import connection, init_schema

# ~400 major US cities with coordinates
# This is enough to cover most metros since metro names start with the primary city
US_CITY_COORDS = {
    "Abilene, TX": (32.4487, -99.7331), "Akron, OH": (41.0814, -81.5190),
    "Albany, GA": (31.5785, -84.1557), "Albany, NY": (42.6526, -73.7562),
    "Albuquerque, NM": (35.0844, -106.6504), "Alexandria, LA": (31.3113, -92.4451),
    "Allentown, PA": (40.6084, -75.4902), "Amarillo, TX": (35.2220, -101.8313),
    "Ames, IA": (42.0347, -93.6200), "Anchorage, AK": (61.2181, -149.9003),
    "Ann Arbor, MI": (42.2808, -83.7430), "Anniston, AL": (33.6598, -85.8316),
    "Appleton, WI": (44.2619, -88.4154), "Asheville, NC": (35.5951, -82.5515),
    "Athens, GA": (33.9519, -83.3576), "Atlanta, GA": (33.7490, -84.3880),
    "Atlantic City, NJ": (39.3643, -74.4229), "Auburn, AL": (32.6099, -85.4808),
    "Augusta, GA": (33.4735, -81.9748), "Austin, MN": (43.6666, -92.9746),
    "Austin, TX": (30.2672, -97.7431), "Bakersfield, CA": (35.3733, -119.0187),
    "Baltimore, MD": (39.2904, -76.6122), "Bangor, ME": (44.8016, -68.7712),
    "Barnstable, MA": (41.7003, -70.3002), "Baton Rouge, LA": (30.4515, -91.1871),
    "Battle Creek, MI": (42.3212, -85.1797), "Bay City, MI": (43.5945, -83.8889),
    "Beaumont, TX": (30.0802, -94.1266), "Beckley, WV": (37.7782, -81.1882),
    "Bellingham, WA": (48.7519, -122.4787), "Bend, OR": (44.0582, -121.3153),
    "Billings, MT": (45.7833, -108.5007), "Biloxi, MS": (30.3960, -88.8853),
    "Binghamton, NY": (42.0987, -75.9180), "Birmingham, AL": (33.5207, -86.8025),
    "Bismarck, ND": (46.8083, -100.7837), "Blacksburg, VA": (37.2296, -80.4139),
    "Bloomington, IL": (40.4842, -88.9937), "Bloomington, IN": (39.1653, -86.5264),
    "Bloomsburg, PA": (41.0037, -76.4549), "Boise, ID": (43.6150, -116.2023),
    "Boulder, CO": (40.0150, -105.2705), "Bowling Green, KY": (36.9685, -86.4808),
    "Bremerton, WA": (47.5673, -122.6326), "Bridgeport, CT": (41.1865, -73.1952),
    "Brownsville, TX": (25.9017, -97.4975), "Brunswick, GA": (31.1499, -81.4915),
    "Buffalo, NY": (42.8864, -78.8784), "Burlington, NC": (36.0957, -79.4378),
    "Burlington, VT": (44.4759, -73.2121), "Canton, OH": (40.7989, -81.3784),
    "Cape Coral, FL": (26.5629, -81.9495), "Carbondale, IL": (37.7273, -89.2168),
    "Carson City, NV": (39.1638, -119.7674), "Casper, WY": (42.8501, -106.3252),
    "Cedar Rapids, IA": (41.9779, -91.6656), "Champaign, IL": (40.1164, -88.2434),
    "Charleston, SC": (32.7765, -79.9311), "Charleston, WV": (38.3498, -81.6326),
    "Charlotte, NC": (35.2271, -80.8431), "Charlottesville, VA": (38.0293, -78.4767),
    "Chattanooga, TN": (35.0456, -85.3097), "Cheyenne, WY": (41.1400, -104.8202),
    "Chicago, IL": (41.8781, -87.6298), "Chico, CA": (39.7285, -121.8375),
    "Cincinnati, OH": (39.1031, -84.5120), "Clarksville, TN": (36.5298, -87.3595),
    "Cleveland, OH": (41.4993, -81.6944), "Coeur d'Alene, ID": (47.6777, -116.7805),
    "College Station, TX": (30.6280, -96.3344), "Colorado Springs, CO": (38.8339, -104.8214),
    "Columbia, MO": (38.9517, -92.3341), "Columbia, SC": (34.0007, -81.0348),
    "Columbus, GA": (32.4610, -84.9877), "Columbus, IN": (39.2014, -85.9214),
    "Columbus, OH": (39.9612, -82.9988), "Corpus Christi, TX": (27.8006, -97.3964),
    "Corvallis, OR": (44.5646, -123.2620), "Cumberland, MD": (39.6529, -78.7625),
    "Dallas, TX": (32.7767, -96.7970), "Dalton, GA": (34.7698, -84.9702),
    "Danville, IL": (40.1245, -87.6300), "Davenport, IA": (41.5236, -90.5776),
    "Dayton, OH": (39.7589, -84.1916), "Decatur, AL": (34.6059, -86.9833),
    "Decatur, IL": (39.8403, -88.9548), "Deltona, FL": (28.9005, -81.2637),
    "Denver, CO": (39.7392, -104.9903), "Des Moines, IA": (41.5868, -93.6250),
    "Detroit, MI": (42.3314, -83.0458), "Dothan, AL": (31.2232, -85.3905),
    "Dover, DE": (39.1582, -75.5244), "Dubuque, IA": (42.5006, -90.6646),
    "Duluth, MN": (46.7867, -92.1005), "Durham, NC": (35.9940, -78.8986),
    "East Stroudsburg, PA": (41.0023, -75.1779), "Eau Claire, WI": (44.8113, -91.4985),
    "El Centro, CA": (32.7920, -115.5631), "El Paso, TX": (31.7619, -106.4850),
    "Elizabethtown, KY": (37.6940, -85.8591), "Elkhart, IN": (41.6820, -85.9767),
    "Elmira, NY": (42.0898, -76.8077), "Erie, PA": (42.1292, -80.0851),
    "Eugene, OR": (44.0521, -123.0868), "Evansville, IN": (37.9716, -87.5711),
    "Fairbanks, AK": (64.8378, -147.7164), "Fargo, ND": (46.8772, -96.7898),
    "Farmington, NM": (36.7281, -108.2187), "Fayetteville, AR": (36.0626, -94.1574),
    "Fayetteville, NC": (35.0527, -78.8784), "Flagstaff, AZ": (35.1983, -111.6513),
    "Flint, MI": (43.0125, -83.6875), "Florence, SC": (34.1954, -79.7626),
    "Fond du Lac, WI": (43.7730, -88.4471), "Fort Collins, CO": (40.5853, -105.0844),
    "Fort Smith, AR": (35.3859, -94.3985), "Fort Wayne, IN": (41.0793, -85.1394),
    "Fresno, CA": (36.7378, -119.7871), "Gadsden, AL": (34.0143, -86.0066),
    "Gainesville, FL": (29.6516, -82.3248), "Gainesville, GA": (34.2979, -83.8241),
    "Gettysburg, PA": (39.8309, -77.2311), "Glens Falls, NY": (43.3095, -73.6440),
    "Goldsboro, NC": (35.3849, -77.9928), "Grand Forks, ND": (47.9253, -97.0329),
    "Grand Junction, CO": (39.0639, -108.5506), "Grand Rapids, MI": (42.9634, -85.6681),
    "Great Falls, MT": (47.5002, -111.3008), "Greeley, CO": (40.4233, -104.7091),
    "Green Bay, WI": (44.5133, -88.0133), "Greensboro, NC": (36.0726, -79.7920),
    "Greenville, NC": (35.6127, -77.3664), "Greenville, SC": (34.8526, -82.3940),
    "Gulfport, MS": (30.3674, -89.0928), "Hagerstown, MD": (39.6418, -77.7200),
    "Hammond, LA": (30.5044, -90.4612), "Hanford, CA": (36.3274, -119.6457),
    "Harrisburg, PA": (40.2732, -76.8867), "Harrisonburg, VA": (38.4496, -78.8689),
    "Hartford, CT": (41.7658, -72.6734), "Hattiesburg, MS": (31.3271, -89.2903),
    "Hickory, NC": (35.7330, -81.3413), "Hilton Head, SC": (32.2163, -80.7526),
    "Hinesville, GA": (31.8468, -81.5959), "Holland, MI": (42.7876, -86.1089),
    "Homosassa Springs, FL": (28.8003, -82.5754), "Hot Springs, AR": (34.5037, -93.0552),
    "Houma, LA": (29.5958, -90.7195), "Houston, TX": (29.7604, -95.3698),
    "Huntington, WV": (38.4192, -82.4452), "Huntsville, AL": (34.7304, -86.5861),
    "Idaho Falls, ID": (43.4917, -112.0339), "Indianapolis, IN": (39.7684, -86.1581),
    "Iowa City, IA": (41.6611, -91.5302), "Ithaca, NY": (42.4440, -76.5019),
    "Jackson, MI": (42.2459, -84.4013), "Jackson, MS": (32.2988, -90.1848),
    "Jackson, TN": (35.6145, -88.8139), "Jacksonville, FL": (30.3322, -81.6557),
    "Jacksonville, NC": (34.7541, -77.4303), "Janesville, WI": (42.6828, -89.0187),
    "Jefferson City, MO": (38.5767, -92.1735), "Johnson City, TN": (36.3134, -82.3535),
    "Johnstown, PA": (40.3268, -78.9220), "Jonesboro, AR": (35.8423, -90.7043),
    "Joplin, MO": (37.0842, -94.5133), "Kalamazoo, MI": (42.2917, -85.5872),
    "Kankakee, IL": (41.1200, -87.8612), "Kansas City, MO": (39.0997, -94.5786),
    "Kennewick, WA": (46.2112, -119.1372), "Killeen, TX": (31.1171, -97.7278),
    "Kingsport, TN": (36.5484, -82.5618), "Kingston, NY": (41.9270, -73.9974),
    "Knoxville, TN": (35.9606, -83.9207), "Kokomo, IN": (40.4864, -86.1336),
    "La Crosse, WI": (43.8014, -91.2396), "Lafayette, IN": (40.4167, -86.8753),
    "Lafayette, LA": (30.2241, -92.0198), "Lake Charles, LA": (30.2266, -93.2174),
    "Lake Havasu City, AZ": (34.4839, -114.3225), "Lakeland, FL": (28.0395, -81.9498),
    "Lancaster, PA": (40.0379, -76.3055), "Lansing, MI": (42.7325, -84.5555),
    "Laredo, TX": (27.5036, -99.5076), "Las Cruces, NM": (32.3199, -106.7637),
    "Las Vegas, NV": (36.1699, -115.1398), "Lawrence, KS": (38.9717, -95.2353),
    "Lawton, OK": (34.6036, -98.3959), "Lebanon, PA": (40.3431, -76.4114),
    "Lewiston, ID": (46.4165, -117.0177), "Lewiston, ME": (44.1004, -70.2148),
    "Lexington, KY": (38.0406, -84.5037), "Lima, OH": (40.7429, -84.1052),
    "Lincoln, NE": (40.8136, -96.7026), "Little Rock, AR": (34.7465, -92.2896),
    "Logan, UT": (41.7370, -111.8338), "Longview, TX": (32.5007, -94.7405),
    "Longview, WA": (46.1382, -122.9382), "Los Angeles, CA": (34.0522, -118.2437),
    "Louisville, KY": (38.2527, -85.7585), "Lubbock, TX": (33.5779, -101.8552),
    "Lynchburg, VA": (37.4138, -79.1422), "Macon, GA": (32.8407, -83.6324),
    "Madera, CA": (36.9613, -120.0607), "Madison, WI": (43.0731, -89.4012),
    "Manchester, NH": (42.9956, -71.4548), "Manhattan, KS": (39.1836, -96.5717),
    "Mankato, MN": (44.1636, -94.0032), "Mansfield, OH": (40.7589, -82.5145),
    "McAllen, TX": (26.2034, -98.2300), "Medford, OR": (42.3265, -122.8756),
    "Memphis, TN": (35.1495, -90.0490), "Merced, CA": (37.3022, -120.4830),
    "Miami, FL": (25.7617, -80.1918), "Midland, TX": (31.9973, -102.0779),
    "Milwaukee, WI": (43.0389, -87.9065), "Minneapolis, MN": (44.9778, -93.2650),
    "Missoula, MT": (46.8721, -113.9940), "Mobile, AL": (30.6954, -88.0399),
    "Modesto, CA": (37.6391, -120.9969), "Monroe, LA": (32.5093, -92.1193),
    "Monroe, MI": (41.9164, -83.3977), "Montgomery, AL": (32.3668, -86.3000),
    "Morgantown, WV": (39.6295, -79.9559), "Morristown, TN": (36.2140, -83.2949),
    "Mount Vernon, WA": (48.4219, -122.3341), "Muncie, IN": (40.1934, -85.3864),
    "Muskegon, MI": (43.2342, -86.2484), "Myrtle Beach, SC": (33.6891, -78.8867),
    "Napa, CA": (38.2975, -122.2869), "Naples, FL": (26.1420, -81.7948),
    "Nashville, TN": (36.1627, -86.7816), "New Bern, NC": (35.1085, -77.0441),
    "New Haven, CT": (41.3083, -72.9279), "New Orleans, LA": (29.9511, -90.0715),
    "New York, NY": (40.7128, -74.0060), "Newark, NJ": (40.7357, -74.1724),
    "Niles, MI": (41.8295, -86.2542), "North Port, FL": (27.0442, -82.2362),
    "Norwich, CT": (41.5243, -72.0759), "Ocala, FL": (29.1872, -82.1401),
    "Ocean City, NJ": (39.2776, -74.5746), "Odessa, TX": (31.9457, -102.3676),
    "Ogden, UT": (41.2230, -111.9738), "Oklahoma City, OK": (35.4676, -97.5164),
    "Olympia, WA": (47.0379, -122.9007), "Omaha, NE": (41.2565, -95.9345),
    "Orlando, FL": (28.5383, -81.3792), "Oshkosh, WI": (44.0247, -88.5426),
    "Owensboro, KY": (37.7719, -87.1112), "Oxnard, CA": (34.1975, -119.1771),
    "Palm Bay, FL": (28.0345, -80.5887), "Panama City, FL": (30.1588, -85.6602),
    "Parkersburg, WV": (39.2667, -81.5615), "Pensacola, FL": (30.4213, -87.2169),
    "Peoria, IL": (40.6936, -89.5890), "Philadelphia, PA": (39.9526, -75.1652),
    "Phoenix, AZ": (33.4484, -112.0740), "Pine Bluff, AR": (34.2284, -92.0032),
    "Pittsburgh, PA": (40.4406, -79.9959), "Pittsfield, MA": (42.4500, -73.2454),
    "Pocatello, ID": (42.8713, -112.4455), "Portland, ME": (43.6591, -70.2568),
    "Portland, OR": (45.5152, -122.6784), "Prescott, AZ": (34.5400, -112.4685),
    "Providence, RI": (41.8240, -71.4128), "Provo, UT": (40.2338, -111.6585),
    "Pueblo, CO": (38.2545, -104.6091), "Punta Gorda, FL": (26.9298, -82.0454),
    "Racine, WI": (42.7261, -87.7829), "Raleigh, NC": (35.7796, -78.6382),
    "Rapid City, SD": (44.0805, -103.2310), "Reading, PA": (40.3356, -75.9269),
    "Redding, CA": (40.5865, -122.3917), "Reno, NV": (39.5296, -119.8138),
    "Richmond, VA": (37.5407, -77.4360), "Riverside, CA": (33.9534, -117.3962),
    "Roanoke, VA": (37.2710, -79.9414), "Rochester, MN": (44.0121, -92.4802),
    "Rochester, NY": (43.1566, -77.6088), "Rockford, IL": (42.2711, -89.0940),
    "Rocky Mount, NC": (35.9382, -77.7905), "Rome, GA": (34.2570, -85.1647),
    "Sacramento, CA": (38.5816, -121.4944), "Saginaw, MI": (43.4195, -83.9508),
    "Salem, OR": (44.9429, -123.0351), "Salinas, CA": (36.6777, -121.6555),
    "Salisbury, MD": (38.3607, -75.5994), "Salt Lake City, UT": (40.7608, -111.8910),
    "San Angelo, TX": (31.4638, -100.4370), "San Antonio, TX": (29.4241, -98.4936),
    "San Diego, CA": (32.7157, -117.1611), "San Francisco, CA": (37.7749, -122.4194),
    "San Jose, CA": (37.3382, -121.8863), "San Luis Obispo, CA": (35.2828, -120.6596),
    "Santa Cruz, CA": (36.9741, -122.0308), "Santa Fe, NM": (35.6870, -105.9378),
    "Santa Maria, CA": (34.9530, -120.4357), "Santa Rosa, CA": (38.4405, -122.7141),
    "Savannah, GA": (32.0809, -81.0912), "Scranton, PA": (41.4090, -75.6624),
    "Seattle, WA": (47.6062, -122.3321), "Sebastian, FL": (27.8164, -80.4706),
    "Sebring, FL": (27.4955, -81.4409), "Sherman, TX": (33.6357, -96.6089),
    "Shreveport, LA": (32.5252, -93.7502), "Sierra Vista, AZ": (31.5455, -110.3036),
    "Sioux City, IA": (42.4963, -96.4049), "Sioux Falls, SD": (43.5460, -96.7313),
    "South Bend, IN": (41.6764, -86.2520), "Spartanburg, SC": (34.9496, -81.9320),
    "Spokane, WA": (47.6588, -117.4260), "Springfield, IL": (39.7817, -89.6501),
    "Springfield, MA": (42.1015, -72.5898), "Springfield, MO": (37.2090, -93.2923),
    "Springfield, OH": (39.9242, -83.8088), "St. Cloud, MN": (45.5579, -94.1632),
    "St. George, UT": (37.0965, -113.5684), "St. Joseph, MO": (39.7687, -94.8466),
    "St. Louis, MO": (38.6270, -90.1994), "State College, PA": (40.7934, -77.8600),
    "Staunton, VA": (38.1496, -79.0717), "Stockton, CA": (37.9577, -121.2908),
    "Sumter, SC": (33.9204, -80.3415), "Syracuse, NY": (43.0481, -76.1474),
    "Tallahassee, FL": (30.4383, -84.2807), "Tampa, FL": (27.9506, -82.4572),
    "Terre Haute, IN": (39.4667, -87.4139), "Texarkana, TX": (33.4418, -94.0477),
    "The Villages, FL": (28.9009, -82.0101), "Toledo, OH": (41.6528, -83.5379),
    "Topeka, KS": (39.0473, -95.6752), "Trenton, NJ": (40.2206, -74.7597),
    "Tucson, AZ": (32.2226, -110.9747), "Tulsa, OK": (36.1540, -95.9928),
    "Tuscaloosa, AL": (33.2098, -87.5692), "Tyler, TX": (32.3513, -95.3011),
    "Urban Honolulu, HI": (21.3069, -157.8583), "Utica, NY": (43.1009, -75.2327),
    "Valdosta, GA": (30.8327, -83.2785), "Vallejo, CA": (38.1041, -122.2566),
    "Victoria, TX": (28.8053, -96.9850), "Vineland, NJ": (39.4863, -75.0260),
    "Virginia Beach, VA": (36.8529, -75.9780), "Visalia, CA": (36.3302, -119.2921),
    "Waco, TX": (31.5493, -97.1467), "Walla Walla, WA": (46.0646, -118.3430),
    "Warner Robins, GA": (32.6131, -83.6243), "Washington, DC": (38.9072, -77.0369),
    "Waterloo, IA": (42.4928, -92.3426), "Watertown, NY": (43.9748, -75.9107),
    "Wausau, WI": (44.9591, -89.6301), "Weirton, WV": (40.4190, -80.5890),
    "Wenatchee, WA": (47.4235, -120.3103), "Wheeling, WV": (40.0640, -80.7209),
    "Wichita, KS": (37.6872, -97.3301), "Wichita Falls, TX": (33.9137, -98.4934),
    "Williamsport, PA": (41.2412, -77.0011), "Wilmington, DE": (39.7391, -75.5398),
    "Wilmington, NC": (34.2257, -77.9447), "Winchester, VA": (39.1857, -78.1633),
    "Winston, NC": (36.0999, -80.2442), "Worcester, MA": (42.2626, -71.8023),
    "Yakima, WA": (46.6021, -120.5059), "York, PA": (39.9626, -76.7277),
    "Youngstown, OH": (41.0998, -80.6495), "Yuba City, CA": (39.1404, -121.6169),
    "Yuma, AZ": (32.6927, -114.6277),
    "Enid, OK": (36.3956, -97.8784), "Hanover, PA": (39.8007, -76.9830),
    "Chambersburg, PA": (39.9376, -77.6611), "Morgantown, WV": (39.6295, -79.9559),
}


def geocode_metros() -> int:
    """Update latitude/longitude for metro geographies using city name lookup."""
    updated = 0
    
    with connection() as conn:
        metros = conn.execute("""
            SELECT geography_id, geo_code FROM geographies 
            WHERE geo_type = 'metro' AND (latitude IS NULL OR longitude IS NULL)
        """).fetchall()
        
        for metro in metros:
            geo_code = metro["geo_code"]
            
            # Extract "City, ST" from the metro name
            parts = geo_code.split(",")
            if len(parts) < 2:
                continue
            
            city_part = parts[0].strip().split("-")[0].strip()
            state_part = parts[1].strip().split("-")[0].strip()
            key = f"{city_part}, {state_part}"
            
            if key in US_CITY_COORDS:
                lat, lon = US_CITY_COORDS[key]
                conn.execute(
                    "UPDATE geographies SET latitude = ?, longitude = ? WHERE geography_id = ?",
                    (lat, lon, metro["geography_id"]),
                )
                updated += 1
    
    print(f"  Geocoded {updated} metros")
    return updated


if __name__ == "__main__":
    init_schema()
    print("\nGeocoding metro areas...")
    geocode_metros()
    print("Done.")
