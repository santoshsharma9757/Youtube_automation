import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('pipeline_main', Path('main.py').resolve())
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

scenes = json.loads(Path('output/script.json').read_text(encoding='utf-8'))
for path in Path('assets/videos').glob('video_*.mp4'):
    path.unlink(missing_ok=True)
for path in Path('assets/audio').glob('audio_*.mp3'):
    path.unlink(missing_ok=True)
for i, scene in enumerate(scenes):
    m.generate_audio(scene['line'], i)
video = m.create_final_video(scenes, 'mystery')
print(json.dumps({'video_path': str(video)}, ensure_ascii=False))
