
import csv
import hashlib
import io
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# UNCOMMON MEASURES
# Index 001: Water into Wine
# Data: UK Office for National Statistics

BASE_MONTH = "2015-01"
OUTPUT = Path("data")

SERIES = {
    "water": "D7DR",
    "wine": "D7DH",
}

MONTHS = {
    name: number
    for number, name in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        start=1
    )
}


def download_series(name, series_id):
    url = (
        "https://www.ons.gov.uk/generator"
        "?format=csv&uri=/economy/inflationandpriceindices/"
        f"timeseries/{series_id.lower()}/mm23"
    )

    request = urllib.request.Request(
        url, headers={"User-Agent": "UncommonMeasures/1.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()

    if len(raw) < 100:
        raise ValueError(f"{name}: downloaded file is too small")

    text = raw.decode("utf-8-sig")

    if series_id.upper() not in text.upper():
        raise ValueError(f"{name}: expected ONS series ID not found")

    checksum = hashlib.sha256(raw).hexdigest()
    return text, raw, checksum


def parse_monthly(text):
    observations = {}

    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue

        period = row[0].strip().upper()
        match = re.fullmatch(r"(\d{4}) ([A-Z]{3})", period)

        if not match:
            continue

        year = int(match.group(1))
        month = MONTHS.get(match.group(2))

        if month is None:
            continue

        date = f"{year:04d}-{month:02d}"

        if date in observations:
            raise ValueError(f"Duplicate observation: {date}")

        value = float(row[1].strip())

        if value <= 0:
            raise ValueError(f"Invalid CPI value: {date}")

        observations[date] = value

    if BASE_MONTH not in observations:
        raise ValueError("Base month is missing")

    if len(observations) < 100:
        raise ValueError("Insufficient historical observations")

    return observations


def calculate(water, wine):
    if set(water) != set(wine):
        raise ValueError("Water and wine observation dates do not match")

    dates = sorted(water)

    # Check monthly continuity
    for previous, current in zip(dates, dates[1:]):
        y, m = map(int, previous.split("-"))
        expected = f"{y + (m == 12):04d}-{m % 12 + 1:02d}"
        if current != expected:
            raise ValueError(f"Missing month before {current}")

    base_ratio = water[BASE_MONTH] / wine[BASE_MONTH]

    return [
        (
            date,
            water[date],
            wine[date],
            100 * (water[date] / wine[date]) / base_ratio
        )
        for date in dates
        if date >= BASE_MONTH
    ]


def main():
    print("Uncommon Measures — Water into Wine")
    print("Downloading official ONS data...")

    source_data = {}

    # Download and validate everything before saving results
    for name, series_id in SERIES.items():
        text, raw, checksum = download_series(name, series_id)
        observations = parse_monthly(text)
        source_data[name] = (observations, raw, checksum)

    results = calculate(
        source_data["water"][0],
        source_data["wine"][0]
    )

    latest = results[-1]
    previous_year = (
        next((r for r in results if r[0] ==
              f"{int(latest[0][:4])-1}{latest[0][4:]}"), None)
    )

    annual_change = (
        100 * (latest[3] / previous_year[3] - 1)
        if previous_year else None
    )

    OUTPUT.mkdir(exist_ok=True)

    # Preserve the source files with a timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for name, (_, raw, checksum) in source_data.items():
        filename = OUTPUT / f"{name}_{timestamp}.csv"
        filename.write_bytes(raw)
        print(f"{name}: SHA-256 {checksum}")

    # Save calculated observations
    filename = OUTPUT / "water_into_wine.csv"

    with filename.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["month", "water_cpi", "wine_cpi", "index"])
        for row in results:
            writer.writerow([
                row[0],
                f"{row[1]:.4f}",
                f"{row[2]:.4f}",
                f"{row[3]:.4f}"
            ])

    print(f"\nLatest observation: {latest[0]}")
    print(f"Water into Wine Index: {latest[3]:.2f}")

    if annual_change is not None:
        print(f"Annual change: {annual_change:+.2f}%")

    print(f"Saved {len(results)} observations to {filename}")
    print("Candidate calculation complete — review before publishing.")


if __name__ == "__main__":
    main()
