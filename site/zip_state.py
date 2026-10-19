"""State of a U.S. ZIP code, from its first three digits (USPS sectional centers; each 3-digit prefix belongs to one state).
Added Oct 19, 2026, for the out-of-state check on price pages: the NPI registry's practice state is typed by the provider and
is sometimes wrong. The Alabama pages listed "The Emory Clinic, Inc" (NPI 1467486373), whose registry address is
"59 Executive Park Dr, Atlanta, AL 30329": the state says Alabama, the city and ZIP say Georgia. The ZIP is the check.

  zip_state('30329') -> 'GA'     zip_state('') -> ''  (unknown, military or territory ZIPs give '')
"""
_RANGES = [  # (first prefix, last prefix, state)
    (5, 5, 'NY'), (10, 27, 'MA'), (28, 29, 'RI'), (30, 38, 'NH'), (39, 49, 'ME'), (50, 54, 'VT'), (55, 55, 'MA'), (56, 59, 'VT'),
    (60, 69, 'CT'), (70, 89, 'NJ'), (100, 149, 'NY'), (150, 196, 'PA'), (197, 199, 'DE'), (200, 200, 'DC'), (201, 201, 'VA'),
    (202, 205, 'DC'), (206, 219, 'MD'), (220, 246, 'VA'), (247, 268, 'WV'), (270, 289, 'NC'), (290, 299, 'SC'), (300, 319, 'GA'),
    (320, 339, 'FL'), (341, 349, 'FL'), (350, 369, 'AL'), (370, 385, 'TN'), (386, 397, 'MS'), (398, 399, 'GA'), (400, 427, 'KY'),
    (430, 459, 'OH'), (460, 479, 'IN'), (480, 499, 'MI'), (500, 528, 'IA'), (530, 549, 'WI'), (550, 567, 'MN'), (569, 569, 'DC'),
    (570, 577, 'SD'), (580, 588, 'ND'), (590, 599, 'MT'), (600, 629, 'IL'), (630, 658, 'MO'), (660, 679, 'KS'), (680, 693, 'NE'),
    (700, 714, 'LA'), (716, 729, 'AR'), (730, 732, 'OK'), (733, 733, 'TX'), (734, 749, 'OK'), (750, 799, 'TX'), (800, 816, 'CO'),
    (820, 831, 'WY'), (832, 838, 'ID'), (840, 847, 'UT'), (850, 865, 'AZ'), (870, 884, 'NM'), (885, 885, 'TX'), (889, 898, 'NV'),
    (900, 961, 'CA'), (967, 968, 'HI'), (970, 979, 'OR'), (980, 994, 'WA'), (995, 999, 'AK')]
_BY3 = {p: st for a, b, st in _RANGES for p in range(a, b + 1)}


def zip_state(z):
    """Two-letter state for a ZIP code (5 or 9 digits, any formatting), or '' when unknown."""
    d = ''.join(ch for ch in str(z or '') if ch.isdigit())
    if len(d) < 5:
        return ''
    return _BY3.get(int(d[:3]), '')
