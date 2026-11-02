import os
import django

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"  # Sostituisci con il percorso reale
)

django.setup()

from core.notion_sync import fetch_notion_recipes

if __name__ == "__main__":
    import pprint
    l = fetch_notion_recipes()
    pprint.pprint(l)
    print(len(l))

