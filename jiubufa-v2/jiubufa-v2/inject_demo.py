"""Inject demo_data.json into app.html as an inline JS variable."""
import json, sys
from pathlib import Path

DEMO_JSON = Path(__file__).parent / "front_test" / "demo_data.json"
APP_HTML = Path(__file__).parent / "front_test" / "app.html"
PLACEHOLDER = "<!-- DEMO_DATA_PLACEHOLDER -->"

def main():
    if not DEMO_JSON.exists():
        print(f"ERROR: {DEMO_JSON} not found. Run capture_demo.py first.")
        sys.exit(1)

    with open(DEMO_JSON, "r", encoding="utf-8") as f:
        demo = json.load(f)

    demo_js = json.dumps(demo, ensure_ascii=False)
    script_tag = f'<script>const DEMO_DATA = {demo_js};</script>'

    with open(APP_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    if script_tag in html:
        print("Demo data already injected. Updating...")
        # Remove old injection
        import re
        html = re.sub(r'<script>const DEMO_DATA = .*?</script>', '', html, flags=re.DOTALL)

    html = html.replace(PLACEHOLDER, script_tag)

    # Validate
    if PLACEHOLDER in html:
        print("ERROR: Placeholder still present after replacement")
        sys.exit(1)

    with open(APP_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Injected demo data into app.html ({len(demo_js)} chars of JSON)")
    print(f"Demo case: {demo.get('_meta',{}).get('description','')}")

if __name__ == "__main__":
    main()
