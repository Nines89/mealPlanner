# Repository Guidelines

## Project Structure

This is a Django meal-planning application. `config/` contains project settings and root URLs; `core/` contains models, views, planning logic, forms, migrations, and management commands. HTML templates are in `core/templates/` and `templates/`; browser assets are in `static/`. Ingredient data and catalog setup live in `core/data/` and `core/catalog.py`. Tests are mainly in `core/tests.py` and `core/test_recipes.py`, with additional integration checks under `tests/`.

## Development Commands

Run commands from the repository root:

- `python manage.py runserver` starts the local development server.
- `python manage.py migrate` applies database migrations.
- `python manage.py test` runs the Django test suite.
- `python manage.py check` checks project configuration.
- `python manage.py seed_catalog` synchronizes the ingredient and meal catalog; use it when catalog data needs alignment.

## Coding Style

Use Python with four-space indentation, descriptive `snake_case` names for functions and variables, and `PascalCase` for classes. Keep views focused on HTTP handling and put reusable domain logic in modules such as `core/planning.py` and `core/week.py`. Follow nearby Django conventions, add type hints where practical, handle missing or invalid values explicitly, and avoid dependencies unless needed. No formatter or linter is configured in the repository.

## Commits and Pull Requests

Recent commit subjects are short and descriptive, but no formal commit convention is established. Use a concise imperative subject that explains the change. Pull requests should describe user-visible behavior, note relevant migrations or configuration changes, link related issues when available, and include screenshots for UI changes. Report the tests and checks that were actually run.

## Configuration and Data Safety

Keep secrets and local environment files out of version control. Review `config/settings.py` for required environment configuration before deployment. Treat catalog CSV data and Django migrations as application data: make intentional, reviewable changes and do not rewrite applied migrations.
