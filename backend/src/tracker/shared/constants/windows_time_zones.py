"""Windows time-zone names and the standard names they stand for.

Windows names its zones in its own way (``W. Europe Standard Time``), while
Threadline, Python and GitHub use the standard names (``Europe/Berlin``). This
table covers the zones most people are in, after the "001" column of the
Unicode CLDR ``windowsZones`` table, every zone Windows 10 and 11 offer, with
each standard name in its current spelling. A zone Windows adds after this table
was made is not found, and the set-up then offers ``UTC`` for the person to
correct by typing their zone.
"""

from __future__ import annotations

from typing import Final

#: The command that prints the Windows zone's name, and its argument.
WINDOWS_ZONE_COMMAND: Final[tuple[str, ...]] = ("tzutil", "/g")

#: What Windows adds to a zone's name when daylight saving time is switched off.
WINDOWS_NO_DST_SUFFIX: Final[str] = "_dstoff"

#: Seconds ``tzutil`` may take.
WINDOWS_ZONE_TIMEOUT_SECONDS: Final[float] = 5.0

#: Windows zone name -> standard (IANA) zone name.
WINDOWS_TO_IANA: Final[dict[str, str]] = {
    # North and Central America
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Aleutian Standard Time": "America/Adak",
    "Alaskan Standard Time": "America/Anchorage",
    "Yukon Standard Time": "America/Whitehorse",
    "Pacific Standard Time": "America/Los_Angeles",
    "Pacific Standard Time (Mexico)": "America/Tijuana",
    "US Mountain Standard Time": "America/Phoenix",
    "Mountain Standard Time": "America/Denver",
    "Mountain Standard Time (Mexico)": "America/Mazatlan",
    "Central America Standard Time": "America/Guatemala",
    "Central Standard Time": "America/Chicago",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Canada Central Standard Time": "America/Regina",
    "Eastern Standard Time": "America/New_York",
    "Eastern Standard Time (Mexico)": "America/Cancun",
    "US Eastern Standard Time": "America/Indiana/Indianapolis",
    "Haiti Standard Time": "America/Port-au-Prince",
    "Cuba Standard Time": "America/Havana",
    "Turks And Caicos Standard Time": "America/Grand_Turk",
    "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns",
    "Greenland Standard Time": "America/Nuuk",
    "Saint Pierre Standard Time": "America/Miquelon",
    # South America
    "SA Pacific Standard Time": "America/Bogota",
    "Venezuela Standard Time": "America/Caracas",
    "SA Western Standard Time": "America/La_Paz",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "Pacific SA Standard Time": "America/Santiago",
    "Magallanes Standard Time": "America/Punta_Arenas",
    "Paraguay Standard Time": "America/Asuncion",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Bahia Standard Time": "America/Bahia",
    "Tocantins Standard Time": "America/Araguaina",
    "SA Eastern Standard Time": "America/Cayenne",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires",
    "Montevideo Standard Time": "America/Montevideo",
    "Easter Island Standard Time": "Pacific/Easter",
    # Atlantic, Africa and the Indian Ocean
    "UTC": "UTC",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Azores Standard Time": "Atlantic/Azores",
    "Cape Verde Standard Time": "Atlantic/Cape_Verde",
    "Morocco Standard Time": "Africa/Casablanca",
    "Sao Tome Standard Time": "Africa/Sao_Tome",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "Libya Standard Time": "Africa/Tripoli",
    "Egypt Standard Time": "Africa/Cairo",
    "Sudan Standard Time": "Africa/Khartoum",
    "South Sudan Standard Time": "Africa/Juba",
    "Namibia Standard Time": "Africa/Windhoek",
    "South Africa Standard Time": "Africa/Johannesburg",
    "E. Africa Standard Time": "Africa/Nairobi",
    "Mauritius Standard Time": "Indian/Mauritius",
    # Europe
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Romance Standard Time": "Europe/Paris",
    "Central European Standard Time": "Europe/Warsaw",
    "GTB Standard Time": "Europe/Bucharest",
    "E. Europe Standard Time": "Europe/Chisinau",
    "FLE Standard Time": "Europe/Kyiv",
    "Kaliningrad Standard Time": "Europe/Kaliningrad",
    "Belarus Standard Time": "Europe/Minsk",
    "Turkey Standard Time": "Europe/Istanbul",
    "Russian Standard Time": "Europe/Moscow",
    "Astrakhan Standard Time": "Europe/Astrakhan",
    "Saratov Standard Time": "Europe/Saratov",
    "Volgograd Standard Time": "Europe/Volgograd",
    "Russia Time Zone 3": "Europe/Samara",
    # The Middle East and Central Asia
    "Israel Standard Time": "Asia/Jerusalem",
    "West Bank Standard Time": "Asia/Hebron",
    "Jordan Standard Time": "Asia/Amman",
    "Middle East Standard Time": "Asia/Beirut",
    "Syria Standard Time": "Asia/Damascus",
    "Arabic Standard Time": "Asia/Baghdad",
    "Arab Standard Time": "Asia/Riyadh",
    "Iran Standard Time": "Asia/Tehran",
    "Arabian Standard Time": "Asia/Dubai",
    "Azerbaijan Standard Time": "Asia/Baku",
    "Georgian Standard Time": "Asia/Tbilisi",
    "Caucasus Standard Time": "Asia/Yerevan",
    "Afghanistan Standard Time": "Asia/Kabul",
    "West Asia Standard Time": "Asia/Tashkent",
    "Qyzylorda Standard Time": "Asia/Qyzylorda",
    "Pakistan Standard Time": "Asia/Karachi",
    "Ekaterinburg Standard Time": "Asia/Yekaterinburg",
    "Central Asia Standard Time": "Asia/Bishkek",
    # South and Southeast Asia
    "India Standard Time": "Asia/Kolkata",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Nepal Standard Time": "Asia/Kathmandu",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Myanmar Standard Time": "Asia/Yangon",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Singapore Standard Time": "Asia/Singapore",
    # Siberia and East Asia
    "Omsk Standard Time": "Asia/Omsk",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "Altai Standard Time": "Asia/Barnaul",
    "Tomsk Standard Time": "Asia/Tomsk",
    "North Asia Standard Time": "Asia/Krasnoyarsk",
    "W. Mongolia Standard Time": "Asia/Hovd",
    "North Asia East Standard Time": "Asia/Irkutsk",
    "Ulaanbaatar Standard Time": "Asia/Ulaanbaatar",
    "China Standard Time": "Asia/Shanghai",
    "Taipei Standard Time": "Asia/Taipei",
    "Transbaikal Standard Time": "Asia/Chita",
    "Yakutsk Standard Time": "Asia/Yakutsk",
    "Korea Standard Time": "Asia/Seoul",
    "North Korea Standard Time": "Asia/Pyongyang",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Vladivostok Standard Time": "Asia/Vladivostok",
    "Sakhalin Standard Time": "Asia/Sakhalin",
    "Magadan Standard Time": "Asia/Magadan",
    "Russia Time Zone 10": "Asia/Srednekolymsk",
    "Kamchatka Standard Time": "Asia/Kamchatka",
    "Russia Time Zone 11": "Asia/Kamchatka",
    # Australia and the Pacific
    "W. Australia Standard Time": "Australia/Perth",
    "Aus Central W. Standard Time": "Australia/Eucla",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "AUS Central Standard Time": "Australia/Darwin",
    "E. Australia Standard Time": "Australia/Brisbane",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "Tasmania Standard Time": "Australia/Hobart",
    "Lord Howe Standard Time": "Australia/Lord_Howe",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Bougainville Standard Time": "Pacific/Bougainville",
    "Norfolk Standard Time": "Pacific/Norfolk",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Chatham Islands Standard Time": "Pacific/Chatham",
    "Fiji Standard Time": "Pacific/Fiji",
    "Tonga Standard Time": "Pacific/Tongatapu",
    "Samoa Standard Time": "Pacific/Apia",
    "Line Islands Standard Time": "Pacific/Kiritimati",
    "Marquesas Standard Time": "Pacific/Marquesas",
    # Whole-hour offsets from UTC that belong to no country
    "Dateline Standard Time": "Etc/GMT+12",
    "UTC-11": "Etc/GMT+11",
    "UTC-09": "Etc/GMT+9",
    "UTC-08": "Etc/GMT+8",
    "UTC-02": "Etc/GMT+2",
    "UTC+12": "Etc/GMT-12",
    "UTC+13": "Etc/GMT-13",
}
