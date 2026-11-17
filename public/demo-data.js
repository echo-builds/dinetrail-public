export const DEMO_GUIDE = {
  restaurant: "Le Petit Bouillon · Paris 2e",
  sourceLabel: "小红书攻略样例",
  sourceType: "xiaohongshu",
  image: "/assets/guide.svg",
  items: [
    { id: "guide-oeuf", nameZh: "蛋黄酱鸡蛋", nameOriginal: "Œuf mayonnaise", rating: 5, sentiment: "recommended", note: "经典前菜，酱汁浓郁，适合第一次尝试。", sourceQuote: "蛋黄酱鸡蛋看着普通，但酱汁很浓郁，第一口就很惊喜。" },
    { id: "guide-duck", nameZh: "油封鸭腿", nameOriginal: "Confit de canard", rating: 4, sentiment: "recommended", note: "攻略作者称外皮香脆，但整体偏咸。", sourceQuote: "油封鸭腿外皮特别脆，肉很嫩，不过口味会偏咸一点。" },
    { id: "guide-brulee", nameZh: "焦糖布蕾", nameOriginal: "Crème brûlée", rating: 0, sentiment: "mentioned", note: "作为收尾甜点被提到。", sourceQuote: "最后点了焦糖布蕾，焦糖壳很脆。" },
  ],
};

export const DEMO_PAGES = [
  {
    id: "starters", title: "前菜 · Entrées", asset: "/assets/menu-starters.svg",
    dishes: [
      { id: "oeuf-mayo", original: "Œuf mayonnaise maison", nameZh: "自制蛋黄酱鸡蛋", summary: "水煮蛋配蛋黄酱，口感绵密，味道浓郁", price: 8.5, tags: ["熟食", "鸡蛋", "蛋黄酱"], guideMatchIds: ["guide-oeuf"], box: { x: 86, y: 248, w: 828, h: 105 } },
      { id: "onion-soup", original: "Soupe à l’oignon gratinée", nameZh: "焗烤法式洋葱汤", summary: "焦化洋葱汤配面包和奶酪，咸香厚重", price: 12, tags: ["熟食", "奶酪", "偏浓郁"], guideMatchIds: [], box: { x: 86, y: 372, w: 828, h: 105 } },
      { id: "escargots", original: "Six escargots, beurre persillé", nameZh: "香蒜欧芹黄油蜗牛", summary: "蜗牛配蒜香欧芹黄油，弹韧油润", price: 14, tags: ["特殊食材", "黄油", "蒜香"], guideMatchIds: [], box: { x: 86, y: 496, w: 828, h: 105 } },
    ],
  },
  {
    id: "mains", title: "主菜 · Plats", asset: "/assets/menu-mains.svg",
    dishes: [
      { id: "duck-confit", original: "Confit de canard, pommes sarladaises", nameZh: "油封鸭腿配萨拉代兹土豆", summary: "盐渍慢煮鸭腿配蒜香土豆，外脆内嫩、咸香浓郁", price: 26, tags: ["全熟", "偏咸", "油脂丰富"], guideMatchIds: ["guide-duck"], box: { x: 86, y: 248, w: 828, h: 105 } },
      { id: "beef-bourguignon", original: "Bœuf bourguignon, purée maison", nameZh: "勃艮第红酒炖牛肉", summary: "牛肉以红酒慢炖配土豆泥，软烂醇厚", price: 28, tags: ["全熟", "含酒烹饪", "偏浓郁"], guideMatchIds: [], box: { x: 86, y: 372, w: 828, h: 105 } },
      { id: "steak-tartare", original: "Steak tartare préparé, frites", nameZh: "现拌生牛肉塔塔配薯条", summary: "生牛肉末现场调味，口感鲜嫩，配薯条", price: 25, tags: ["生食", "生牛肉", "需确认调味"], guideMatchIds: [], box: { x: 86, y: 496, w: 828, h: 105 } },
    ],
  },
  {
    id: "desserts", title: "甜点 · Desserts", asset: "/assets/menu-desserts.svg",
    dishes: [
      { id: "creme-brulee", original: "Crème brûlée à la vanille", nameZh: "香草焦糖布蕾", summary: "香草蛋奶布丁配脆焦糖层，冰凉细滑", price: 10, tags: ["奶制品", "鸡蛋", "甜"], guideMatchIds: ["guide-brulee"], box: { x: 86, y: 248, w: 828, h: 105 } },
      { id: "tarte-tatin", original: "Tarte Tatin, crème fraîche", nameZh: "法式倒置焦糖苹果塔", summary: "焦糖烤苹果配酥皮和酸奶油，酸甜温热", price: 12, tags: ["酸甜", "奶制品", "适合分享"], guideMatchIds: [], box: { x: 86, y: 372, w: 828, h: 105 } },
    ],
  },
];

export function allDemoDishes() {
  return DEMO_PAGES.flatMap((page) => page.dishes.map((dish) => ({ ...dish, pageId: page.id, pageTitle: page.title, pageAsset: page.asset })));
}
