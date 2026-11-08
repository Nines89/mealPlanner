import time
from pathlib import Path
from playwright.sync_api import Page, sync_playwright, expect

LIST_URL = "https://www.amazon.it/alexaquantum/sp/alexaShoppingList"
PROJECT_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_DIR / "tests" / "amazon_profile"
ERROR_SCREENSHOT = PROJECT_DIR / "tests" / "debug_error.png"

ADD_TIMEOUT_MS = 10_000


def is_login_page(page: Page) -> bool:
    return "/ap/signin" in page.url


def ensure_logged_in(page: Page) -> None:
    page.goto(LIST_URL, timeout=30_000, wait_until="domcontentloaded")
    page.wait_for_url(
        lambda url: "/ap/signin" in url or "alexaShoppingList" in url,
        timeout=30_000,
    )
    if not is_login_page(page):
        return

    print("Login richiesto: completalo nella finestra del browser (2FA incluso).")
    # Attende il redirect verso la lista, senza dipendere da Invio.
    page.wait_for_url("**/alexaShoppingList**", timeout=300_000)


def add_item(page: Page, item: str) -> None:
    item = item.strip()
    if not item:
        raise ValueError("item vuoto")

    items = page.get_by_text(item, exact=True)
    count_before = items.count()

    field = page.locator(".input-box input[type='text']")
    if not field.is_visible():
        page.get_by_role("button", name="Aggiungi articolo alla tua lista").click()
        expect(field).to_be_visible(timeout=ADD_TIMEOUT_MS)

    field.click()
    field.press_sequentially(item, delay=30)
    expect(field).to_have_value(item, timeout=ADD_TIMEOUT_MS)

    confirm = page.get_by_role("button", name="Aggiungi alla lista")
    expect(confirm).to_be_enabled(timeout=ADD_TIMEOUT_MS)
    confirm.click()

    expect(items).to_have_count(count_before + 1, timeout=ADD_TIMEOUT_MS)


def main(items: list[str]) -> None:
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR, channel="chrome", headless=True
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            ensure_logged_in(page)
            time.sleep(.5)
            for item in items:
                add_item(page, item)
        except Exception:
            page.screenshot(path=str(ERROR_SCREENSHOT), full_page=True)
            raise
        finally:
            context.close()
