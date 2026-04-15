import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('pipeline_main', Path('main.py').resolve())
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

scenes = [
  {"line": "त्यो रात... दरबारभित्र साँच्चै के फुट्यो?", "keywords": ["dark palace corridor", "night mystery", "shadow hallway"], "emotion": "shock", "visual_type": "mystery"},
  {"line": "सबै कुरा सामान्य जस्तै थियो...", "keywords": ["royal dinner table", "quiet palace room", "calm before chaos"], "emotion": "suspense", "visual_type": "mystery"},
  {"line": "अनि अचानक... आवाज आयो...", "keywords": ["sudden gunshot reaction", "dark interior", "panic shadow"], "emotion": "shock", "visual_type": "mystery"},
  {"line": "एक आवाज... अनि फेरि अर्को...", "keywords": ["echoing hallway", "fearful face", "running footsteps"], "emotion": "suspense", "visual_type": "mystery"},
  {"line": "दरबारको हावा नै डरले जम्यो...", "keywords": ["dark palace room", "frozen silence", "night fear"], "emotion": "dark", "visual_type": "mystery"},
  {"line": "कोही भागे... कोही लुके...", "keywords": ["people running", "hiding in darkness", "chaos indoors"], "emotion": "suspense", "visual_type": "mystery"},
  {"line": "तर सत्य... त्यहीँ कतै थुनियो...", "keywords": ["hidden truth", "sealed door", "mystery file"], "emotion": "dark", "visual_type": "mystery"},
  {"line": "नाम बाहिर आए... तर कहानी आएन...", "keywords": ["newspaper headline", "investigation document", "secret report"], "emotion": "dark", "visual_type": "mystery"},
  {"line": "त्यो रात केवल हत्या थिएन भनिन्छ...", "keywords": ["conspiracy board", "dark silhouette", "palace secret"], "emotion": "suspense", "visual_type": "mystery"},
  {"line": "सायद... त्यो त अझ ठूलो खेल थियो...", "keywords": ["shadow conspiracy", "dim light face", "hidden agenda"], "emotion": "dark", "visual_type": "mystery"},
  {"line": "आजसम्म पनि धेरै कुरा मिल्दैनन्...", "keywords": ["unanswered questions", "mystery investigation", "confused witness"], "emotion": "suspense", "visual_type": "mystery"},
  {"line": "त्यो रात दरबारमा वास्तवमै के भयो... आखिर सत्य के हो?", "keywords": ["palace mystery night", "questioning face", "dark truth"], "emotion": "shock", "visual_type": "mystery"}
]
seo = {
    "title": "दरबार हत्याकाण्ड: त्यो रात के भयो?",
    "description": "दरबार हत्याकाण्डको त्यो रात आज पनि रहस्यले ढाकिएको छ। यो छोटो भिडियोमा घटनाको तनाव, डर, र अनुत्तरित प्रश्नलाई सिनेम्याटिक ढंगले देखाइएको छ.\n\nतपाईंको विचार के छ? comment मा भन्नुहोस् र यस्तै दमदार Nepali Shorts का लागि 360 Nepal Explained subscribe गर्नुहोस्.",
    "hashtags": ["#nepal", "#nepali", "#shorts", "#darbarhatyakanda", "#mystery", "#360NepalExplained"],
    "keywords": ["दरबार हत्याकाण्ड", "Nepal Royal Massacre", "Nepali mystery", "360 Nepal Explained"]
}

m.ensure_dirs()
m.dump_json(m.SCRIPT_JSON, scenes)
m.dump_json(m.SEO_JSON, seo)
for i, scene in enumerate(scenes):
    m.fetch_video(scene["keywords"], i, "mystery", scene["visual_type"])
    m.generate_audio(scene["line"], i)
video = m.create_final_video(scenes, "mystery")
summary = {"channel": m.CHANNEL_NAME, "topic": "दरबार हत्याकाण्ड: त्यो रात के भयो?", "category": "mystery", "script_path": str(m.SCRIPT_JSON), "seo_path": str(m.SEO_JSON), "video_path": str(video), "upload_response": None}
m.dump_json(m.SUMMARY_JSON, summary)
print(json.dumps(summary, ensure_ascii=False, indent=2))
