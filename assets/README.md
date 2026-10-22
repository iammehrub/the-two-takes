# Two Takes Podcast studio artwork

The generated channel artwork is stored at:

`assets/two_takes_podcast_studio.avif`

The production script decodes it with FFmpeg, converts it to a 1280 × 720 JPEG for the YouTube thumbnail, and shows the same artwork full-screen during the first four seconds of the video. The opener is an overlay, so narration and subtitle timestamps do not shift.

If the asset is missing or cannot be decoded, the production script safely falls back to its existing thumbnail and video visuals.
