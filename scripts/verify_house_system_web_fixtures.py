"""Offline replay of captured professional-site output; does not query websites.

Astrodienst uses the same Swiss Ephemeris family, so this validates integration
and settings, not an independent derivation of the astronomy algorithms.
"""
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import swisseph as swe
from services.house_systems import calculate_houses
from services.location_resolver import coordinate_location_id, LocationResolver
from services.mcp_natal import calculate_natal_data

FIXTURES = ROOT / 'docs/validation/house-systems-2026-11-16'


def compare_astrocom():
    captured = json.loads((FIXTURES / 'astrocom-swetest.json').read_text())
    output = []
    for case in captured['cases']:
        day, month, year = map(int, case['date'].split('.'))
        hour, minute = map(int, case['ut'].split(':'))
        jd = swe.julday(year, month, day, hour + minute / 60)
        frame = calculate_houses(jd, case['lat'], case['lon'], case['system'])
        cusps = [float(v) for _, v in re.findall(r'^house\s+(\d+)\s+([\d.]+)', case['raw'], re.M)]
        assert len(cusps) == 12
        arcsec = lambda a, b: abs((a-b+180) % 360 - 180) * 3600
        cusp_error = max(arcsec(x, y) for x, y in zip(cusps, frame.cusps))
        axes = [float(re.search(r'^'+name+r'\s+([\d.]+)', case['raw'], re.M)[1]) for name in ['Ascendant','MC']]
        axis_error = max(arcsec(x, y) for x, y in zip(axes, frame.ascmc))
        # Verify the public MCP source too, with independently supplied UT and
        # exact coordinates, including the first DST occurrence in New York.
        location = coordinate_location_id(case['lat'], case['lon'])
        snap = LocationResolver().resolve(location_id=location)
        civil = datetime(year, month, day, hour, minute, tzinfo=timezone.utc).astimezone(ZoneInfo(snap.tz_iana))
        chart = calculate_natal_data(year=civil.year, month=civil.month, day=civil.day,
                                    hour=civil.hour, minute=civil.minute, fold=civil.fold,
                                    location_id=location, house_system=case['system'])
        assert chart['status'] == 'ok', chart
        public_cusp_error = max(arcsec(x, y['longitude']) for x, y in zip(cusps, chart['house_cusps']))
        planet_errors = []
        for planet in chart['planets']:
            row = re.search(r'^'+planet['key'].capitalize()+r'\s+([\d.]+)', case['raw'], re.M)
            if row:
                planet_errors.append(arcsec(float(row[1]), planet['longitude']))
        assert len(planet_errors) == 10
        assert max(cusp_error, axis_error, public_cusp_error) < .001
        assert max(planet_errors) < .2  # public planet positions round to 4 decimals
        output.append(dict(case=case['id'], system=case['system'],
                           max_cusp_error_arcsec=cusp_error, max_axis_error_arcsec=axis_error,
                           max_mcp_cusp_error_arcsec=public_cusp_error,
                           max_mcp_planet_error_arcsec=max(planet_errors)))
    return output


def compare_astrotheme():
    captured = json.loads((FIXTURES / 'astrotheme-tables.json').read_text())
    signs = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']
    planet_names = ['Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto']
    def angle(text, sign):
        degrees, minutes = map(int, re.findall(r'\d+', text))
        return signs.index(sign)*30 + degrees + minutes/60
    def coord(text):
        m = re.fullmatch(r'(\d+)\.(\d+)([EWNS])', text)
        return (int(m[1])+int(m[2])/60)*(-1 if m[3] in 'WS' else 1)
    output = []
    for case in captured['cases']:
        geo = re.match(r'(\S+) ; (\S+) / (\S+), (.+) UT', case['site_coordinates_time'])
        lon, lat = coord(geo[1]), coord(geo[2])
        ut = datetime.strptime(geo[4], '%I:%M %p')
        jd = swe.julday(case['year'],case['month'],case['day'],ut.hour+ut.minute/60)
        frame = calculate_houses(jd,lat,lon,case['system'])
        site_cusps = [angle(row[1],row[2]) for row in case['house_cusps']]
        assert len(site_cusps)==12
        arcsec = lambda a,b: abs((a-b+180)%360-180)*3600
        cusp_error = max(arcsec(x,y) for x,y in zip(site_cusps,frame.cusps))
        chart=calculate_natal_data(year=case['year'],month=case['month'],day=case['day'],
                                  hour=case['hour'],minute=0,
                                  location_id=coordinate_location_id(lat,lon),house_system=case['system'])
        assert chart['status']=='ok', chart
        assert case['next_house_shift']=='No Shift'
        actual = {p['key'].capitalize():p for p in chart['planets']}
        house_matches=0
        for row in case['planet_houses']:
            if row[0] in planet_names:
                expected = int(re.search(r'\d+',row[1])[0])
                assert actual[row[0]]['house']==expected,(case['id'],case['system'],row,actual[row[0]])
                house_matches+=1
        assert house_matches==10
        planet_error=max(arcsec(angle(row[1],row[-1]),actual[row[0]]['longitude'])
                         for row in case['planet_positions'] if row[0] in planet_names)
        axis_error=max(arcsec(angle(row[1],row[-1]),chart['axes'][{'AS':'asc','MC':'mc'}[row[0]]]['lon'])
                       for row in case['planet_positions'] if row[0] in ('AS','MC'))
        # Do not widen the display-rounding threshold to conceal Astrotheme's
        # small pre-existing Placidus discrepancy. New Equal/Koch systems must
        # agree; all discrepancies are recorded explicitly in the report.
        if case['system'] != 'placidus':
            assert max(cusp_error,planet_error,axis_error)<=30.1,(case['id'],case['system'],cusp_error,planet_error,axis_error)
        assert max(planet_error,axis_error)<=30.1
        within_precision = cusp_error <= 30.1
        output.append(dict(case=case['id'],system=case['system'],longitude=lon,latitude=lat,
                           max_cusp_error_arcsec=cusp_error,max_axis_error_arcsec=axis_error,
                           max_planet_error_arcsec=planet_error,planet_house_matches=house_matches,
                           display_precision='one arcminute; half-minute rounding threshold',
                           cusp_within_half_arcminute=within_precision,
                           status='consistent_at_display_precision' if within_precision else 'unresolved_preexisting_placidus_difference'))
    return output


if __name__ == '__main__':
    results = compare_astrocom()
    (FIXTURES / 'astrocom-comparison.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(dict(cases=len(results), house_cusps=len(results)*12,
                         max_cusp_error_arcsec=max(r['max_cusp_error_arcsec'] for r in results),
                         max_mcp_planet_error_arcsec=max(r['max_mcp_planet_error_arcsec'] for r in results)), indent=2))

    second = compare_astrotheme()
    (FIXTURES / 'astrotheme-comparison.json').write_text(json.dumps(second, indent=2)+'\n')
    print(json.dumps(dict(astrotheme_cases=len(second), house_cusps=len(second)*12, planet_house_matches=sum(r['planet_house_matches'] for r in second), max_cusp_error_arcsec=max(r['max_cusp_error_arcsec'] for r in second)), indent=2))
