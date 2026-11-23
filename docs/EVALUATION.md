# 真实菜单评测

`scripts/evaluate_real_menus.py` 会把真实菜单依次送入当前服务，补齐最终决策提示后，检查价格结构、菜品字段、坐标范围、重复项和广告式空话。

示例：

```bash
python3 scripts/evaluate_real_menus.py \
  --expectations eval/acceptance-expectations.json \
  /tmp/menu-avocette.jpg \
  /tmp/menu-petit-cafe.jpg \
  /tmp/menu-pont.jpg \
  /tmp/menu-le-royal-1.jpg
```

`eval/menu-sources.json` 保存了首批 Wikimedia Commons 样本的文件页和缩略图地址，便于追溯来源；仓库不复制原图。

`eval/acceptance-expectations.json` 为已人工检查的样本设置最低菜品数和价格结构，防止“只识别两道也算接口成功”。

结构检查通过不等于翻译一定正确。最终仍需人工检查菜名、套餐规则、风险提示和原图位置。
