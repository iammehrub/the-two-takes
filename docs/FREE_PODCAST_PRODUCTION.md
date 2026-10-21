# Free podcast production upgrades

This guide describes the local/free-first upgrades in the Two Takes podcast pipeline. It does not require a new paid service or a new API key.

## What the pipeline now does

- **Free-first script generation:** Gemini is the default. The potentially paid OpenAI API is used only if the repository variable USE_OPENAI_FOR_SCRIPT is explicitly set to true. Leave it unset for the free-first path.
- **Two-host delivery:** Himel and Niha use separate Kokoro voices, sentence-sized TTS chunks, delivery-aware pacing, and short conversational pauses.
- **Structured intro:** the script must start with a short hook, then a labeled welcome. The audio pipeline inserts a 5.5-second music-only sting between them.
- **Structured lesson:** real conversation, six useful phrases, guided shadowing/speaking practice, a quick tip, recap, and short sign-off are required by the script validator.
- **Original music:** a locally synthesized theme is generated at runtime, including a small original motif around the intro sting and outro.
- **Music ducking:** FFmpeg sidechain compression lowers the music under dialogue so speech stays in front.
- **Outro fade:** seven seconds of music-only audio follow the final spoken line; the soundtrack fades out at the end.
- **Timing alignment:** the video renderer adds frames for the music sting, natural pauses, and outro tail so the final video does not silently drop time or let captions drift.
- **Captions and chapters:** subtitles are timed from the actual TTS segment durations; chapter markers are derived from lesson sections.
- **Local production quality gate:** scripts/episode_qc.py checks video resolution/codec, stereo AAC audio, audio/video duration alignment, subtitle cues, chapter markers, script length, host turn balance, and approximate audio level. Hard media defects stop upload; editorial targets are reported as warnings.
- **Quality report artifacts:** the workflow uploads production_report.json, production_report.txt, and captions.srt with the growth pack.
- **No new automatic publishing trigger:** the new test workflow checks code on push but does not upload a video. Actual publishing remains controlled by the existing Daily Episode workflow.

## Run a safe code test

Open **Actions → Podcast Production Tests → Run workflow**. This tests Python syntax, locally synthesized music, chapter generation, and the media quality gate using a synthetic sample. It does not call Gemini, OpenAI, Pexels, or YouTube, and it does not publish anything.

## Run the full episode

Use **Actions → Two Takes — Daily Episode → Run workflow** only when you want to generate and publish a real episode. It still requires the repository's existing API credentials. Keep USE_OPENAI_FOR_SCRIPT unset for Gemini-first behavior.

## Important limitations

- “Free-first” means no additional paid service is required by these changes; provider free-tier limits and existing account billing settings still apply.
- Kokoro and local FFmpeg effects improve consistency but cannot guarantee fully human-like acting.
- The intro sting and outro fade are inserted by the production code; the spoken script should not contain lines such as “music plays.”
- The quality gate can catch technical problems, but listen to the final audio periodically to assess pronunciation, voice realism, music level, and whether the dialogue feels natural.
