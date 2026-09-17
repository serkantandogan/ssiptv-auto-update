# SS IPTV Auto Update

This repo generates an SS IPTV-compatible M3U playlist from authorized IPTV sources and keeps it fresh with GitHub Actions.

## What it does

- Reads source playlists from `sources.yml`
- Keeps only channels whose stream URLs respond successfully
- Groups channels by category
- Writes `public/ssiptv.m3u`
- Runs automatically on a schedule

## Legal note

Use only streams that you own, operate, or have permission to redistribute. This project is intentionally built as a validator and playlist generator; it does not scrape paid, protected, or unauthorized channel links.

## Setup

1. Create a GitHub repository.
2. Upload these files to the repository.
3. Edit `sources.yml` and add your authorized M3U URLs or local playlist files.
4. Enable GitHub Actions.
5. After the first run, use this raw playlist URL in SS IPTV:

```text
https://raw.githubusercontent.com/USERNAME/REPOSITORY/main/public/ssiptv.m3u
```

Replace `USERNAME` and `REPOSITORY` with your GitHub values.

## Update Frequency

The workflow runs every 6 hours by default. You can change this in `.github/workflows/update-playlist.yml`.

## Manual Run

In GitHub:

1. Open the repository.
2. Go to `Actions`.
3. Select `Update SS IPTV playlist`.
4. Click `Run workflow`.

## Local Run

```bash
python -m pip install -r requirements.txt
python scripts/update_playlist.py
```

The generated playlist will be saved at:

```text
public/ssiptv.m3u
```

