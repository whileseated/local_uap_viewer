# Local UAP Video Index

This folder contains local MP4 downloads from `war.gov/UFO`, grouped by release, plus a generated `index.html` page for browsing them without pagination.

## Folder Structure

Keep videos in release-specific folders:

```text
uap052226/
  release_01/
    DOD_111688723.mp4
    DOD_111688762.mp4
    ...
  release_02/
    video_2605_DOD_111719709_DOD_111719709.mp4
    video_2605_DOD_111719715_DOD_111719715.mp4
    ...
  .dvids-cache/
    DOD_*.html
    details/
      *.html
  build_uap_index.py
  index.html
  uap-local-index.json
```

For future releases, create the next folder using the same naming pattern:

```text
release_03/
release_04/
```

Put the downloaded MP4s directly inside that release folder. The filename only needs to contain a `DOD_#########` id somewhere in it.

## Generated Files

`index.html` is the local browser page. Open it directly in a browser.

`uap-local-index.json` is the structured metadata used by the page. It includes the local file path, release, DOD id, title, DVIDS link, War.gov hash link, dates, location, duration, VIRIN, and description.

`.dvids-cache/` stores fetched DVIDS search/detail pages so the index can be regenerated without re-fetching every page each time.

## Regenerating

After adding videos to a release folder, run:

```sh
python3 build_uap_index.py
```

That scans every `release_*/` folder and rewrites `index.html` and `uap-local-index.json`.

If new videos do not yet have metadata, populate the DVIDS cache for their `DOD_...` ids, then rerun the generator.

## Metadata Workflow

The generator does not currently download metadata from War.gov. War.gov's CSV/data endpoint returned `403` during direct command-line attempts, so the index uses DVIDS as the practical metadata source.

For each local MP4, the script extracts the `DOD_#########` id from the filename. Example:

```text
release_02/video_2605_DOD_111719709_DOD_111719709.mp4
```

becomes:

```text
DOD_111719709
```

That id was searched on DVIDS:

```sh
curl -fsSL "https://www.dvidshub.net/search/?q=DOD_111719709" -o ".dvids-cache/DOD_111719709.html"
```

The search result page exposes the matching DVIDS video URL, title, and poster frame. Example:

```text
https://www.dvidshub.net/video/1007706/dow-uap-pr050-4-uap-formation-iran-26-aug-2022-over-water-callsign
```

Then the DVIDS detail page was cached:

```sh
curl -fsSL "https://www.dvidshub.net/video/1007706/dow-uap-pr050-4-uap-formation-iran-26-aug-2022-over-water-callsign" -o ".dvids-cache/details/1007706.html"
```

The detail page provides the richer metadata parsed into `uap-local-index.json`:

- title
- description
- poster image
- DVIDS video id
- source MP4 URL
- date taken
- date posted
- location
- VIRIN
- duration
- category

The War.gov record URL is reconstructed from the title as a hash link. For example:

```text
DOW-UAP-PR050, "4 UAP Formation Iran 26 Aug 2022 over water [CALLSIGN]"
```

becomes:

```text
https://www.war.gov/UFO/#DOW-UAP-PR050-4-UAP-Formation-Iran-26-Aug-2022-over-water-CALLSIGN
```

The generator also normalizes DOW PR numbers to three digits, so `PR19` becomes `PR019` for display and War.gov hash links.

## How The Page Works

The page embeds every local MP4 as a playable video card. It does not use pagination.

Controls:

- Search filters by title, DOD id, PR number, description, and filename.
- Release pills show all videos or only one release, with counts.
- Decade pills filter by `date_taken`, with counts.
- Sort changes ordering by title, file size, or DOD id.
- Clear resets search and filters.
- Pause all stops every currently loaded video.

When search or filters change, the page scrolls back to the top of the results.
