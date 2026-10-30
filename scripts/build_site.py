"""Build the public Law Career Atlas page using the template and public datasets."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
src=(root/'index.template.html').read_text(encoding='utf-8')
subs={
 '__FIRMS_JSON__':json.dumps(json.loads((root/'data/firms.json').read_text(encoding='utf-8')),ensure_ascii=False),
 '__OPPORTUNITIES_JSON__':json.dumps(json.loads((root/'data/opportunities.json').read_text(encoding='utf-8'))['opportunities'],ensure_ascii=False),
 '__LIVE_JSON__':json.dumps(json.loads((root/'data/live_jobs.json').read_text(encoding='utf-8')),ensure_ascii=False),
 '__APP_JS__':(root/'scripts/app.js').read_text(encoding='utf-8'),
}
for marker,value in subs.items():
 if marker not in src:raise ValueError('Missing template marker '+marker)
 src=src.replace(marker,value)
for forbidden in ('Enable automatic daily checks on GitHub','Upload the full ZIP contents','Create a new GitHub repository'):
 if forbidden in src:raise ValueError('Setup text found in public page: '+forbidden)
(root/'index.html').write_text(src,encoding='utf-8')
print(f'Built index.html ({len(src):,} characters)')
