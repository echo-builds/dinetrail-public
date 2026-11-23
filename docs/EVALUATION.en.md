# Real-Menu Evaluation

`scripts/evaluate_real_menus.py` sends real menu images to the running service and checks pricing structure, dish fields, source-image coordinates, duplicate items, final decision guidance, and promotional filler.

Example:

```bash
python3 scripts/evaluate_real_menus.py \
  --expectations eval/acceptance-expectations.json \
  /tmp/menu-avocette.jpg \
  /tmp/menu-petit-cafe.jpg \
  /tmp/menu-pont.jpg \
  /tmp/menu-le-royal-1.jpg
```

`eval/menu-sources.json` records the Wikimedia Commons source pages and thumbnail URLs for the first evaluation set, so every sample remains traceable without copying the source images into the repository.

`eval/acceptance-expectations.json` defines the minimum dish count and expected pricing structure for samples that have already been reviewed by hand. This prevents a run from passing simply because it recognized two dishes successfully.

Passing the structural checks does not guarantee that every translation is correct. Dish names, set-menu rules, risk notes, and source-image locations still require human review.
