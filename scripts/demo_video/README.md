# Heimdall — 8-minute demo walkthrough video generator

`gen_frames.py` renders a branded, data-driven 8-minute (1920×1080) demo
walkthrough MP4 that follows the recommended demo flow:

| Segment | Minutes | Content |
|---------|---------|---------|
| Context | 0–2 | Title, Executive Overview KPIs, architecture flow |
| Live Scoring API | 2–4 | Real `POST /v1/score` request/response (legit + suspicious) |
| Decision Spectrum | 4–6 | Approve / SCA step-up / Decline scenarios |
| Dashboards & Compliance | 6–8 | Ops SLOs, Power BI EBA report, audit & governance |

## How it works

The video frames are rendered with **Pillow** (no browser needed). It uses
**real data** captured from:

- the live scoring API (`/v1/score` responses) → `api_real.json`
- the demo ops endpoint (`/api/ops`) → `ops.json`
- the local decision-logic scenarios (`scripts/demo_scenarios.py`) → `scenarios_real.json`

One PNG frame is emitted per second (with a global progress bar + caption),
then encoded to H.264 with ffmpeg.

## Regenerate

```bash
pip install pillow imageio-ffmpeg

# 1. start the demo console (for live ops data)
./scripts/demo-web.sh &

# 2. capture real data into the working dir (see gen_frames.py header for the
#    exact urllib snippets), producing: ops.json, api_real.json, scenarios_real.json

# 3. render frames + encode
python3 scripts/demo_video/gen_frames.py            # writes frames to /tmp/demovid/frames
FF=$(python3 -c "import imageio_ffmpeg as i; print(i.get_ffmpeg_exe())")
"$FF" -y -framerate 1 -i /tmp/demovid/frames/f%04d.png -r 30 \
      -c:v libx264 -pix_fmt yuv420p -movflags +faststart -crf 20 \
      Heimdall_Demo_8min.mp4
```

## Notes

- Brand palette and Segoe UI font match `docs/assets/heimdall-kpi-visual.html`.
- The suspicious-transaction API scene honestly notes that the **deployed**
  endpoint runs a placeholder stub model (always approves); the production
  ensemble's full decision spectrum is shown in the console section.
- The video has **no audio track** — captions are burned in. Add a voice-over
  in your editor of choice if desired.
