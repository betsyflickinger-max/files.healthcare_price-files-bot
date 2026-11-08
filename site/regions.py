"""Oct 31, 2026 (Betsy chose regional pages): a state whose Price Finder page is too big for one file is published as regional
pages instead. California's statewide page came out at 32.5 MB; the website host takes files up to 25 MB.

Each region is a list of whole counties. A provider belongs to the region of the county its practice ZIP lies mostly in (the
Census ZIP-to-county file behind data/medicare_areas_zip.csv, the same one the Medicare doctor-fee areas use). A hospital file
belongs to the region of its hospital's ZIP (CMS Hospital General Information, as recorded in the hospital plan). The state's
own address (/california/price-finder/) becomes a short page that links to its regional pages.

REGIONS: state page slug -> {region slug: (page name, Medicare locality shown by default, locality name, map box, counties)}.
The default locality is the one with the most providers in the region; every provider is still compared with Medicare for their
own area (site/med_areas.py)."""
import csv, os

HERE = os.path.dirname(os.path.abspath(__file__))

REGIONS = {
    'california': {
        'los-angeles': ('Los Angeles, Orange & Ventura', '18', 'Los Angeles', '-119.8,33.0,-117.1,35.0',
                        ['Los Angeles', 'Orange', 'Ventura']),
        'san-diego-inland-empire': ('San Diego & Inland Empire', '62', 'Riverside-San Bernardino', '-117.9,32.3,-114.0,35.9',
                                    ['San Diego', 'Imperial', 'Riverside', 'San Bernardino']),
        'bay-area': ('San Francisco Bay Area', '05', 'San Francisco', '-123.8,36.6,-121.0,39.0',
                     ['Alameda', 'Contra Costa', 'Marin', 'Napa', 'San Francisco', 'San Mateo', 'Santa Clara', 'Solano', 'Sonoma',
                      'Santa Cruz']),
        'sacramento-northern-california': ('Sacramento & Northern California', '63', 'Sacramento', '-124.6,38.0,-119.5,42.3',
                                           ['Sacramento', 'Placer', 'Yolo', 'El Dorado', 'Sutter', 'Yuba', 'Nevada', 'Butte', 'Shasta',
                                            'Tehama', 'Glenn', 'Colusa', 'Lake', 'Mendocino', 'Humboldt', 'Del Norte', 'Siskiyou',
                                            'Trinity', 'Lassen', 'Modoc', 'Plumas', 'Sierra', 'Amador', 'Alpine']),
        'central-california': ('Central California', '56', 'Fresno', '-122.2,34.2,-115.4,38.8',
                               ['Fresno', 'Kern', 'Kings', 'Tulare', 'Madera', 'Merced', 'Stanislaus', 'San Joaquin', 'Mariposa',
                                'Tuolumne', 'Calaveras', 'Mono', 'Inyo', 'Monterey', 'San Benito', 'San Luis Obispo', 'Santa Barbara']),
    },
    'new-york': {   # Oct 31, 2026 (Betsy): regions beside the statewide page (ALONGSIDE)
        'new-york-city': ('New York City', '01', 'Manhattan', '-74.4,40.3,-73.5,41.1',
            ['Bronx', 'Kings', 'New York', 'Queens', 'Richmond']),
        'long-island': ('Long Island', '02', 'NYC Suburbs/Long Island', '-74.0,40.4,-71.7,41.5',
            ['Nassau', 'Suffolk']),
        'hudson-valley': ('Hudson Valley', '03', 'Poughkeepsie/N NYC Suburbs', '-75.3,40.7,-73.3,42.4',
            ['Westchester', 'Rockland', 'Putnam', 'Orange', 'Dutchess', 'Ulster', 'Sullivan']),
        'western-new-york': ('Western New York & Finger Lakes', '99', 'Rest of New York', '-79.9,41.8,-76.4,43.5',
            ['Erie', 'Niagara', 'Chautauqua', 'Cattaraugus', 'Allegany', 'Wyoming', 'Genesee', 'Orleans', 'Monroe', 'Livingston', 'Ontario', 'Wayne', 'Seneca', 'Yates', 'Steuben', 'Schuyler', 'Chemung']),
        'upstate-new-york': ('Capital Region, Central & Northern New York', '99', 'Rest of New York', '-76.9,41.7,-73.1,45.2',
            ['Albany', 'Broome', 'Cayuga', 'Chenango', 'Clinton', 'Columbia', 'Cortland', 'Delaware', 'Essex', 'Franklin', 'Fulton', 'Greene', 'Hamilton', 'Herkimer', 'Jefferson', 'Lewis', 'Madison', 'Montgomery', 'Oneida', 'Onondaga', 'Oswego', 'Otsego', 'Rensselaer', 'Saratoga', 'Schenectady', 'Schoharie', 'St. Lawrence', 'Tioga', 'Tompkins', 'Warren', 'Washington']),
    },
    'florida': {   # Oct 31, 2026 (Betsy): regions beside the statewide page (ALONGSIDE)
        'south-florida': ('South Florida', '03', 'Fort Lauderdale', '-82.1,24.3,-79.8,28.0',
            ['Miami-Dade', 'Broward', 'Palm Beach', 'Monroe', 'Martin', 'St. Lucie', 'Indian River', 'Okeechobee']),
        'tampa-bay': ('Tampa Bay', '99', 'Rest of Florida', '-83.0,26.8,-81.0,29.2',
            ['Hillsborough', 'Pinellas', 'Pasco', 'Hernando', 'Citrus', 'Polk', 'Manatee', 'Sarasota']),
        'central-florida': ('Orlando & Central Florida', '99', 'Rest of Florida', '-82.7,27.6,-80.3,29.8',
            ['Orange', 'Osceola', 'Seminole', 'Lake', 'Sumter', 'Marion', 'Volusia', 'Flagler', 'Brevard']),
        'southwest-florida': ('Southwest Florida', '03', 'Fort Lauderdale', '-82.5,25.6,-80.7,27.8',
            ['Lee', 'Collier', 'Charlotte', 'Hendry', 'Glades', 'DeSoto', 'Highlands', 'Hardee']),
        'north-florida': ('North Florida & the Panhandle', '99', 'Rest of Florida', '-87.7,28.8,-81.1,31.2',
            ['Alachua', 'Baker', 'Bay', 'Bradford', 'Calhoun', 'Clay', 'Columbia', 'Dixie', 'Duval', 'Escambia', 'Franklin', 'Gadsden', 'Gilchrist', 'Gulf', 'Hamilton', 'Holmes', 'Jackson', 'Jefferson', 'Lafayette', 'Leon', 'Levy', 'Liberty', 'Madison', 'Nassau', 'Okaloosa', 'Putnam', 'Santa Rosa', 'St. Johns', 'Suwannee', 'Taylor', 'Union', 'Wakulla', 'Walton', 'Washington']),
    },
    'illinois': {   # Oct 31, 2026 (Betsy): regions beside the statewide page (ALONGSIDE)
        'chicago-area': ('Chicago Area', '16', 'Chicago', '-89.1,40.8,-87.4,42.7',
            ['Cook', 'DuPage', 'Kane', 'Lake', 'McHenry', 'Will', 'Kendall', 'Grundy', 'DeKalb', 'Kankakee']),
        'central-southern-illinois': ('Central & Southern Illinois', '99', 'Rest of Illinois', '-91.6,36.8,-87.4,42.7',
            ['Adams', 'Alexander', 'Bond', 'Boone', 'Brown', 'Bureau', 'Calhoun', 'Carroll', 'Cass', 'Champaign', 'Christian', 'Clark', 'Clay', 'Clinton', 'Coles', 'Crawford', 'Cumberland', 'De Witt', 'Douglas', 'Edgar', 'Edwards', 'Effingham', 'Fayette', 'Ford', 'Franklin', 'Fulton', 'Gallatin', 'Greene', 'Hamilton', 'Hancock', 'Hardin', 'Henderson', 'Henry', 'Iroquois', 'Jackson', 'Jasper', 'Jefferson', 'Jersey', 'Jo Daviess', 'Johnson', 'Knox', 'LaSalle', 'Lawrence', 'Lee', 'Livingston', 'Logan', 'Macon', 'Macoupin', 'Madison', 'Marion', 'Marshall', 'Mason', 'Massac', 'McDonough', 'McLean', 'Menard', 'Mercer', 'Monroe', 'Montgomery', 'Morgan', 'Moultrie', 'Ogle', 'Peoria', 'Perry', 'Piatt', 'Pike', 'Pope', 'Pulaski', 'Putnam', 'Randolph', 'Richland', 'Rock Island', 'Saline', 'Sangamon', 'Schuyler', 'Scott', 'Shelby', 'St. Clair', 'Stark', 'Stephenson', 'Tazewell', 'Union', 'Vermilion', 'Wabash', 'Warren', 'Washington', 'Wayne', 'White', 'Whiteside', 'Williamson', 'Winnebago', 'Woodford']),
    },
    'pennsylvania': {   # Oct 31, 2026 (Betsy): regions beside the statewide page (ALONGSIDE)
        'philadelphia-area': ('Philadelphia Area', '01', 'Metropolitan Philadelphia', '-76.3,39.6,-74.6,40.8',
            ['Philadelphia', 'Bucks', 'Chester', 'Delaware', 'Montgomery']),
        'western-pennsylvania': ('Pittsburgh & Western Pennsylvania', '99', 'Rest of Pennsylvania', '-80.7,39.5,-77.8,42.4',
            ['Allegheny', 'Armstrong', 'Beaver', 'Butler', 'Fayette', 'Greene', 'Washington', 'Westmoreland', 'Lawrence', 'Mercer', 'Erie', 'Crawford', 'Venango', 'Warren', 'Forest', 'Clarion', 'Indiana', 'Jefferson', 'Cambria', 'Somerset', 'Elk', 'McKean', 'Cameron', 'Clearfield', 'Blair', 'Bedford']),
        'central-eastern-pennsylvania': ('Central & Eastern Pennsylvania', '99', 'Rest of Pennsylvania', '-78.4,39.5,-74.5,42.2',
            ['Adams', 'Berks', 'Bradford', 'Carbon', 'Centre', 'Clinton', 'Columbia', 'Cumberland', 'Dauphin', 'Franklin', 'Fulton', 'Huntingdon', 'Juniata', 'Lackawanna', 'Lancaster', 'Lebanon', 'Lehigh', 'Luzerne', 'Lycoming', 'Mifflin', 'Monroe', 'Montour', 'Northampton', 'Northumberland', 'Perry', 'Pike', 'Potter', 'Schuylkill', 'Snyder', 'Sullivan', 'Susquehanna', 'Tioga', 'Union', 'Wayne', 'Wyoming', 'York']),
    },
    # Nov 1, 2026: Michigan's statewide page came out at 48.1 MiB (2,708 networks), so its address links to four regions,
    # like California. Lines follow Medicare's two Michigan areas (Detroit = Wayne, Oakland, Macomb, Washtenaw; Rest of
    # Michigan), with each area halved so no region holds more than about a third of the state's providers (NPI Registry
    # practice ZIPs: Oakland & Macomb 33%, Wayne & Washtenaw 24%, West Michigan 18%, the rest 25%), about 16 MiB at most.
    'michigan': {
        # Nov 2, 2026 (Betsy OK'd): the first Detroit-area regions came out at 22.6 MiB (Oakland & Macomb) and 20.6 MiB
        # (Wayne & Washtenaw), close to the limit: Detroit-area providers carry far more rates than the provider count
        # suggested. Now one county each (estimated Oakland ~18, Wayne ~15, Macomb ~5, Washtenaw ~6 MiB).
        'oakland-county': ('Oakland County', '01', 'Detroit', '-83.7,42.4,-83.0,42.9', ['Oakland']),
        'macomb-county': ('Macomb County', '01', 'Detroit', '-83.1,42.4,-82.7,42.9', ['Macomb']),
        'detroit-wayne-county': ('Detroit & Wayne County', '01', 'Detroit', '-83.6,42.0,-82.9,42.5', ['Wayne']),
        'ann-arbor-washtenaw': ('Ann Arbor & Washtenaw County', '01', 'Detroit', '-84.2,42.0,-83.5,42.5', ['Washtenaw']),
        'west-michigan': ('West Michigan', '99', 'Rest of Michigan', '-87.2,41.7,-84.6,44.2',
            ['Kent', 'Ottawa', 'Muskegon', 'Kalamazoo', 'Allegan', 'Berrien', 'Van Buren', 'Cass', 'St. Joseph', 'Barry', 'Ionia', 'Montcalm', 'Newaygo', 'Oceana', 'Mecosta', 'Calhoun', 'Branch', 'Mason', 'Lake', 'Osceola']),
        'mid-northern-michigan': ('Mid-Michigan, Northern Michigan & the U.P.', '99', 'Rest of Michigan', '-90.5,41.7,-82.1,47.5',
            ['Alcona', 'Alger', 'Alpena', 'Antrim', 'Arenac', 'Baraga', 'Bay', 'Benzie', 'Charlevoix', 'Cheboygan', 'Chippewa', 'Clare', 'Clinton', 'Crawford', 'Delta', 'Dickinson', 'Eaton', 'Emmet', 'Genesee', 'Gladwin', 'Gogebic', 'Grand Traverse', 'Gratiot', 'Hillsdale', 'Houghton', 'Huron', 'Ingham', 'Iosco', 'Iron', 'Isabella', 'Jackson', 'Kalkaska', 'Keweenaw', 'Lapeer', 'Leelanau', 'Lenawee', 'Livingston', 'Luce', 'Mackinac', 'Manistee', 'Marquette', 'Menominee', 'Midland', 'Missaukee', 'Monroe', 'Montmorency', 'Ogemaw', 'Ontonagon', 'Oscoda', 'Otsego', 'Presque Isle', 'Roscommon', 'Saginaw', 'Sanilac', 'Schoolcraft', 'Shiawassee', 'St. Clair', 'Tuscola', 'Wexford']),
    },
    # Nov 7, 2026 (Betsy OK'd): Missouri (25.0 MiB) and Colorado (27.3 MiB) came out over the host's 25 MiB limit once Anthem's
    # networks went on. Same method as the other states (Healthcare folder area-methods-comparison.md, Oct 15): whole counties,
    # grouped by Census metro area; Missouri's three regions are its three Medicare doctor-fee areas plus each metro's outer
    # counties. Colorado has one Medicare area; Boulder goes with Northern Colorado to keep the Denver page small.
    'missouri': {
        'st-louis-area': ('St. Louis Area', '01', 'Metropolitan St. Louis', '-91.5,37.9,-90.1,39.2', ['St. Louis', 'St. Louis city', 'St. Charles', 'Jefferson', 'Franklin', 'Lincoln', 'Warren']),
        'kansas-city-area': ('Kansas City Area (Missouri side)', '02', 'Metropolitan Kansas City', '-94.7,38.4,-93.4,39.8', ['Jackson', 'Clay', 'Platte', 'Cass', 'Ray', 'Clinton', 'Lafayette']),
        'rest-of-missouri': ('Springfield, Columbia & the Rest of Missouri', '99', 'Rest of Missouri', '-95.8,35.9,-89.1,40.7',
            ['Adair', 'Andrew', 'Atchison', 'Audrain', 'Barry', 'Barton', 'Bates', 'Benton', 'Bollinger', 'Boone', 'Buchanan', 'Butler', 'Caldwell', 'Callaway', 'Camden', 'Cape Girardeau', 'Carroll', 'Carter', 'Cedar', 'Chariton', 'Christian', 'Clark', 'Cole', 'Cooper', 'Crawford', 'Dade', 'Dallas', 'Daviess', 'DeKalb', 'Dent', 'Douglas', 'Dunklin', 'Gasconade', 'Gentry', 'Greene', 'Grundy', 'Harrison', 'Henry', 'Hickory', 'Holt', 'Howard', 'Howell', 'Iron', 'Jasper', 'Johnson', 'Knox', 'Laclede', 'Lawrence', 'Lewis', 'Linn', 'Livingston', 'Macon', 'Madison', 'Maries', 'Marion', 'McDonald', 'Mercer', 'Miller', 'Mississippi', 'Moniteau', 'Monroe', 'Montgomery', 'Morgan', 'New Madrid', 'Newton', 'Nodaway', 'Oregon', 'Osage', 'Ozark', 'Pemiscot', 'Perry', 'Pettis', 'Phelps', 'Pike', 'Polk', 'Pulaski', 'Putnam', 'Ralls', 'Randolph', 'Reynolds', 'Ripley', 'Saline', 'Schuyler', 'Scotland', 'Scott', 'Shannon', 'Shelby', 'St. Clair', 'St. Francois', 'Ste. Genevieve', 'Stoddard', 'Stone', 'Sullivan', 'Taney', 'Texas', 'Vernon', 'Washington', 'Wayne', 'Webster', 'Worth', 'Wright']),
    },
    'colorado': {
        'denver-metro': ('Denver Metro', '01', 'Colorado', '-105.9,39.1,-103.7,40.1', ['Denver', 'Adams', 'Arapahoe', 'Jefferson', 'Douglas', 'Broomfield', 'Elbert', 'Clear Creek', 'Gilpin', 'Park']),
        'boulder-northern-colorado': ('Boulder & Northern Colorado', '01', 'Colorado', '-106.2,39.9,-103.6,41.0', ['Boulder', 'Larimer', 'Weld']),
        'colorado-springs-pueblo': ('Colorado Springs, Pueblo & Southern Front Range', '01', 'Colorado', '-106.0,37.0,-103.9,39.2', ['El Paso', 'Teller', 'Pueblo', 'Fremont', 'Custer', 'Huerfano', 'Las Animas']),
        'western-mountains-plains-colorado': ('Western Slope, Mountains & Eastern Plains', '01', 'Colorado', '-109.1,36.9,-102.0,41.0',
            ['Alamosa', 'Archuleta', 'Baca', 'Bent', 'Chaffee', 'Cheyenne', 'Conejos', 'Costilla', 'Crowley', 'Delta', 'Dolores', 'Eagle', 'Garfield', 'Grand', 'Gunnison', 'Hinsdale', 'Jackson', 'Kiowa', 'Kit Carson', 'La Plata', 'Lake', 'Lincoln', 'Logan', 'Mesa', 'Mineral', 'Moffat', 'Montezuma', 'Montrose', 'Morgan', 'Otero', 'Ouray', 'Phillips', 'Pitkin', 'Prowers', 'Rio Blanco', 'Rio Grande', 'Routt', 'Saguache', 'San Juan', 'San Miguel', 'Sedgwick', 'Summit', 'Washington', 'Yuma']),
    },
    # Nov 8, 2026: Georgia came out at 27.4 MiB (over the host's 25). Same method (Census metro, whole counties). Atlanta's
    # 29-county metro would be ~19 MiB on its own (Detroit-area pages ran bigger than provider counts suggested), so it is three
    # pages; the rest of the state splits by its 3-digit ZIP areas (313-317 and 398-399 = South & Coastal).
    'georgia': {
        'atlanta': ('Atlanta (Fulton, DeKalb & Clayton)', '01', 'Atlanta', '-84.9,33.3,-84.0,34.2', ['Fulton', 'DeKalb', 'Clayton']),
        'atlanta-north-west-suburbs': ('Atlanta North & West Suburbs', '01', 'Atlanta', '-85.4,33.5,-83.7,34.6', ['Cobb', 'Gwinnett', 'Cherokee', 'Forsyth', 'Paulding', 'Douglas', 'Bartow', 'Barrow', 'Pickens', 'Dawson', 'Carroll', 'Haralson']),
        'atlanta-south-east-suburbs': ('Atlanta South & East Suburbs', '01', 'Atlanta', '-85.2,32.8,-83.3,34.0', ['Henry', 'Fayette', 'Coweta', 'Newton', 'Walton', 'Rockdale', 'Spalding', 'Butts', 'Lamar', 'Morgan', 'Meriwether', 'Pike', 'Jasper', 'Heard']),
        'north-middle-georgia': ('North, Middle & East Georgia (Athens, Augusta, Macon, Columbus)', '99', 'Rest of Georgia',
            '-85.7,31.7,-81.3,35.0', ['Baldwin', 'Banks', 'Bibb', 'Bleckley', 'Bulloch', 'Burke', 'Candler', 'Catoosa', 'Chattahoochee', 'Chattooga', 'Clarke', 'Columbia', 'Crawford', 'Crisp', 'Dade', 'Dodge', 'Dooly', 'Elbert', 'Emanuel', 'Evans', 'Fannin', 'Floyd', 'Franklin', 'Gilmer', 'Glascock', 'Gordon', 'Greene', 'Habersham', 'Hall', 'Hancock', 'Harris', 'Hart', 'Houston', 'Jackson', 'Jefferson', 'Jenkins', 'Johnson', 'Jones', 'Laurens', 'Lincoln', 'Lumpkin', 'Macon', 'Madison', 'Marion', 'McDuffie', 'Monroe', 'Montgomery', 'Murray', 'Muscogee', 'Oconee', 'Oglethorpe', 'Peach', 'Polk', 'Pulaski', 'Putnam', 'Rabun', 'Richmond', 'Schley', 'Screven', 'Stephens', 'Stewart', 'Talbot', 'Taliaferro', 'Tattnall', 'Taylor', 'Telfair', 'Toombs', 'Towns', 'Treutlen', 'Troup', 'Twiggs', 'Union', 'Upson', 'Walker', 'Warren', 'Washington', 'Webster', 'Wheeler', 'White', 'Whitfield', 'Wilcox', 'Wilkes', 'Wilkinson']),
        'south-coastal-georgia': ('South & Coastal Georgia (Savannah, Albany, Valdosta)', '99', 'Rest of Georgia', '-85.2,30.3,-80.8,32.6',
            ['Appling', 'Atkinson', 'Bacon', 'Baker', 'Ben Hill', 'Berrien', 'Brantley', 'Brooks', 'Bryan', 'Calhoun', 'Camden', 'Charlton', 'Chatham', 'Clay', 'Clinch', 'Coffee', 'Colquitt', 'Cook', 'Decatur', 'Dougherty', 'Early', 'Echols', 'Effingham', 'Glynn', 'Grady', 'Irwin', 'Jeff Davis', 'Lanier', 'Lee', 'Liberty', 'Long', 'Lowndes', 'McIntosh', 'Miller', 'Mitchell', 'Pierce', 'Quitman', 'Randolph', 'Seminole', 'Sumter', 'Terrell', 'Thomas', 'Tift', 'Turner', 'Ware', 'Wayne', 'Worth']),
    },
}
LIVE = True   # Oct 31, 2026: test split checked row by row (region-test.yml: 0 differences) and the LA page built at 12.1 MiB
HOSP_V = 2   # Oct 31: hospital placement; v2 adds ZIP-prefix and CMS Provider of Services ZIPs (raising it re-places hospitals)
SPLIT_V = 2   # Oct 31: v2 keeps every state code and the 'coming' list on regional pages; raising it splits again
STATE_CODE = {'california': 'CA', 'new-york': 'NY', 'florida': 'FL', 'illinois': 'IL', 'pennsylvania': 'PA', 'michigan': 'MI',
              'missouri': 'MO', 'colorado': 'CO', 'georgia': 'GA'}
# Oct 31, 2026 (Betsy): New York, Florida, Illinois and Pennsylvania fit on one page, so their statewide page stays live (its
# address and /costs/ pages never change) and the regions are added beside it. California's statewide page was too big, so its
# address became a page linking to the regions.
ALONGSIDE = {'new-york', 'florida', 'illinois', 'pennsylvania'}
# States whose regional pages are switched on (hosp_area.py splits them on its next hourly run). A state not listed here is
# built and published exactly as before. Pennsylvania: its first state build is split as soon as it is done (no rebuild).
ON = {'california', 'new-york', 'florida', 'illinois', 'pennsylvania', 'michigan', 'missouri', 'colorado', 'georgia'}   # Oct 31 evening: NY/FL/IL split test matched row for row (run 41220975545)
PARENT = {r: s for s, R in REGIONS.items() for r in R}
NEIGHBORS = {   # regions that share a border, linked from each regional page for people who live near one
    'los-angeles': ['san-diego-inland-empire', 'central-california'],
    'san-diego-inland-empire': ['los-angeles', 'central-california'],
    'bay-area': ['sacramento-northern-california', 'central-california'],
    'sacramento-northern-california': ['bay-area', 'central-california'],
    'central-california': ['los-angeles', 'bay-area', 'sacramento-northern-california', 'san-diego-inland-empire'],
    'new-york-city': ['long-island', 'hudson-valley'], 'long-island': ['new-york-city'],
    'hudson-valley': ['new-york-city', 'upstate-new-york'], 'western-new-york': ['upstate-new-york'],
    'upstate-new-york': ['hudson-valley', 'western-new-york'],
    'south-florida': ['southwest-florida', 'central-florida'], 'southwest-florida': ['south-florida', 'tampa-bay'],
    'tampa-bay': ['central-florida', 'southwest-florida', 'north-florida'], 'central-florida': ['tampa-bay', 'south-florida', 'north-florida'],
    'north-florida': ['central-florida', 'tampa-bay'],
    'chicago-area': ['central-southern-illinois'], 'central-southern-illinois': ['chicago-area'],
    'philadelphia-area': ['central-eastern-pennsylvania'], 'western-pennsylvania': ['central-eastern-pennsylvania'],
    'central-eastern-pennsylvania': ['philadelphia-area', 'western-pennsylvania'],
    'oakland-county': ['macomb-county', 'detroit-wayne-county', 'mid-northern-michigan'], 'macomb-county': ['oakland-county', 'detroit-wayne-county', 'mid-northern-michigan'],
    'detroit-wayne-county': ['oakland-county', 'macomb-county', 'ann-arbor-washtenaw'], 'ann-arbor-washtenaw': ['detroit-wayne-county', 'oakland-county', 'mid-northern-michigan'],
    'west-michigan': ['mid-northern-michigan'],
    'st-louis-area': ['rest-of-missouri'], 'kansas-city-area': ['rest-of-missouri'], 'rest-of-missouri': ['st-louis-area', 'kansas-city-area'],
    'denver-metro': ['boulder-northern-colorado', 'colorado-springs-pueblo', 'western-mountains-plains-colorado'],
    'boulder-northern-colorado': ['denver-metro', 'western-mountains-plains-colorado'],
    'colorado-springs-pueblo': ['denver-metro', 'western-mountains-plains-colorado'],
    'western-mountains-plains-colorado': ['denver-metro', 'boulder-northern-colorado', 'colorado-springs-pueblo'],
    'atlanta': ['atlanta-north-west-suburbs', 'atlanta-south-east-suburbs'],
    'atlanta-north-west-suburbs': ['atlanta', 'atlanta-south-east-suburbs', 'north-middle-georgia'],
    'atlanta-south-east-suburbs': ['atlanta', 'atlanta-north-west-suburbs', 'north-middle-georgia'],
    'north-middle-georgia': ['atlanta-north-west-suburbs', 'atlanta-south-east-suburbs', 'south-coastal-georgia'],
    'south-coastal-georgia': ['north-middle-georgia'], 'mid-northern-michigan': ['oakland-county', 'macomb-county', 'ann-arbor-washtenaw', 'west-michigan'],
}   # region slug -> state page slug
# Nov 2, 2026: regional pages replaced by smaller ones. When the state's address page is next published (city_page.py
# landing_page), each one's address becomes a short page pointing to the state's regions and it leaves the area lists.
RETIRED = {'oakland-macomb': 'michigan', 'detroit-ann-arbor': 'michigan'}


def zip_county(state_code):
    """{zip5: county} for one state (Census 2020 ZCTA -> county with the most land)"""
    for p in (os.path.join(HERE, '..', 'data', 'medicare_areas_zip.csv'), os.path.join(HERE, 'medicare_areas_zip.csv'),
              os.path.join(HERE, '..', 'data', 'zip_county_all.csv')):   # Nov 7, 2026: every state (Colorado has one Medicare area)
        if os.path.exists(p):
            m = {r['zip5']: r['county'] for r in csv.DictReader(open(p)) if r['state'] == state_code}
            if m: return m
    raise FileNotFoundError('medicare_areas_zip.csv')


def county_region(state):
    m = {c: r for r, v in REGIONS[state].items() for c in v[4]}
    return m


def check(state):
    """every county of the state in exactly one region"""
    counties = set(zip_county(STATE_CODE[state]).values())
    listed = [c for v in REGIONS[state].values() for c in v[4]]
    dup = {c for c in listed if listed.count(c) > 1}
    missing, extra = counties - set(listed), set(listed) - counties
    if dup or missing or extra: raise ValueError(f'{state} regions: twice {sorted(dup)}, missing {sorted(missing)}, unknown {sorted(extra)}')
    return True


def region_of_zip(state, z, _cache={}):
    """the region of a ZIP's county; a ZIP that isn't a Census ZIP area (a PO box or a hospital's own ZIP, e.g. 90509) by its
    first three digits, when every Census ZIP area starting with them is in the same region (else None)"""
    if state not in _cache:
        zc, cr = zip_county(STATE_CODE[state]), county_region(state)
        z3 = {}
        for k, c in zc.items(): z3.setdefault(k[:3], set()).add(cr.get(c))
        _cache[state] = (zc, cr, {k: next(iter(v)) for k, v in z3.items() if len(v) == 1})
    zc, cr, z3 = _cache[state]
    z = str(z or '')[:5]
    return cr.get(zc.get(z)) or (z3.get(z[:3]) if len(z) == 5 else None)


def hospital_zips(state_code, _cache={}):
    """{CMS number: ZIP} for hospitals missing from Medicare's Hospital General Information list (long-term care and rehab
    hospitals), from CMS's Provider of Services file (data/hospital_zip_extra.csv, written by site/hosp_zip_lookup.py)"""
    if state_code not in _cache:
        _cache[state_code] = {}
        for p in (os.path.join(HERE, '..', 'data', 'hospital_zip_extra.csv'), os.path.join(HERE, 'hospital_zip_extra.csv')):
            if os.path.exists(p):
                _cache[state_code] = {r['ccn']: r['zip'] for r in csv.DictReader(open(p)) if r['state'] == state_code and r['zip']}; break
    return _cache[state_code]


def by_county_text(counties):
    return 'in a ZIP code that lies mostly in ' + ', '.join(counties[:-1]) + ' or ' + counties[-1] + ' County'


if __name__ == '__main__':
    for s in REGIONS: print(s, check(s))
