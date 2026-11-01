import os
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"  # Sostituisci con il percorso reale
)

django.setup()

from core.notion_sync import fetch_notion_recipes

if __name__ == "__main__":
    """    def _peek(raw, key):
        return str(raw.get(key) or '').strip() if isinstance(raw, dict) else ''


    final_list = []
    raw = {'Categoria': 'Pasta e Cereali',
           'Cereali': 'cous cous',
           'Condimenti': 'aglio, peperoncino, olio',
           'Nome': 'Cuscus con Verdure',
           'Proteine': ['XXX', "Salmone Affumicato", "Lardo"],
           'Verdure (g)': 'peperone rosso: 70\nzucchina: 70\ncipolla: 70',
           'id': '4079b4f7-b3cd-8103-9cc3-f091ac2395eb'}

    # Todo: dobbiamo ancora inserire i condimenti, poi per il resto ci siamo!
    #       ma i condimenti... saranno considerati dal software? O forse è meglio ignorarli?
    ingredients = [
                      {'name': _protein, 'grams': None} for _protein in raw.get('Proteine')
                  ] + [
                      {'name': _veget.strip().split(':')[0], 'grams': _veget.strip().split(':')[1]}
                      for _veget in raw.get('Verdure (g)').split('\n')
                  ] + [
                  ] + [
                      {'name': raw.get('Cereali'), 'grams': None}
                  ] + [
                      {'name': _cond, 'grams': None}
                      for _cond in raw.get('Condimenti').split(',')
                  ]
    final_list.append(
        {
            'external_id': str(raw['id']),
            'name': str(raw['Nome']),
            'genre': str(raw['Categoria']),
            'ingredients': ingredients
        }
    )"""
    import pprint
    l = fetch_notion_recipes()
    pprint.pprint(l)
    print(len(l))

