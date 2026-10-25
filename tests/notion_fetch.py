
import os
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"  # Sostituisci con il percorso reale
)

django.setup()

from core.notion_sync import fetch_notion_recipes

if __name__ == "__main__":
    fetch_notion_recipes()
