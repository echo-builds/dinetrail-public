# DineTrail

> 一个会记住整顿饭的旅行点餐助手。

拍下一页菜单，菜品会逐道出现；你可以边看、边问、边勾选。

DineTrail 会持续记住不同菜单页已经选了什么，把小红书里的推荐匹配到对应菜品，并在译名之外补充口味、口感和必要的踩雷提示。

最终得到的不是几张菜单译文，而是一份可以直接使用的点菜单。

## 产品演示

直接观看约 1 分钟的完整点餐流程：菜单逐道出现、勾选与追问、小红书推荐、追加菜单，以及给服务员看的点菜单。

https://github.com/user-attachments/assets/54187ea3-4499-4ec5-b2ce-d4222a4fd377

## Why DineTrail

我在欧洲旅行时发现，真实的点餐并不是拍完整本菜单，等待全部翻译完成，再从几十道菜里集中选择。

菜单往往有很多页。人们通常看一页、问几道、先选一两道，然后继续翻到下一页。之前已经选了什么，需要一直记住。

点餐也很少从零开始。出发前收藏的小红书推荐，到了餐厅后，还要重新在陌生语言的菜单里寻找对应菜品。

而即使看懂了译名，也仍然可能不知道一道菜是生食、内脏，还是味道和想象完全不同。

DineTrail 因此以“一次用餐”为单位组织产品：持续保存攻略、菜单页、追问和选择，直到用户完成这顿饭的点单。

## 启动

> 不要直接预览 `public/index.html`，那只是源码文件。服务启动后，请用浏览器打开运行地址。需要每次从空白状态测试时，直接打开：[全新点餐首页](http://127.0.0.1:4173/?fresh=1)。

```bash
python3 server.py
```

打开 `http://localhost:4173`。真实菜单体验需要配置 `DASHSCOPE_API_KEY`，自定义图片和对话默认通过阿里云百炼北京地域的 `qwen3.8-flash` 处理。没有 Key 时不会伪造识别结果。

复制 `.env.example` 为 `.env`，填入从阿里云百炼获取的 Key，然后重新启动服务：

```bash
cp .env.example .env
python3 server.py
```

`.env` 已被 Git 忽略，不会提交到仓库。也可以直接使用 `DASHSCOPE_API_KEY=your_key python3 server.py` 临时启动。

可用 `QWEN_MODEL` 覆盖默认模型。若配置业务空间专属域名，可通过 `QWEN_BASE_URL` 覆盖默认北京地域地址。旧的 Gemini 配置仍可通过 `MODEL_PROVIDER=gemini`、`GEMINI_API_KEY` 和 `GEMINI_MODEL` 使用。

仅开发调试时，可打开 `http://localhost:4173/?sample=1` 使用受控样例检查前端状态流；它不是对外 Demo 的默认入口。


## 公开部署

仓库包含 `Dockerfile` 和 `render.yaml`。推荐在 Render 中使用 Blueprint 创建服务：它会按配置创建 Frankfurt 区域的 Docker Web Service、`/healthz` 健康检查和挂载到 `/data` 的 1GB 持久化磁盘。创建时只需在 Render 后台填写不会入库的 `DASHSCOPE_API_KEY`。

Render 的免费 Web Service 不支持持久化磁盘，且空闲后会休眠，只适合临时验证；真实给用户使用应保留 `render.yaml` 中的付费计算实例和磁盘。平台当前限制见 [Render Free 文档](https://render.com/docs/free) 与 [Persistent Disks 文档](https://render.com/docs/disks)。

通用容器平台至少需要设置：

```text
DASHSCOPE_API_KEY=...
HOST=0.0.0.0
PORT=4173
SESSION_DATA_DIR=/data
```

把 `/data` 挂载到持久化磁盘，否则服务重启后点餐会话和原图会丢失。平台健康检查路径使用 `/healthz`；接口只有在 SQLite 可读写且模型 Key 已配置时才返回 200。当前版本没有用户账号，会话 URL 是匿名访问凭证。

部署完成后运行以下命令验证 HTTPS、模型配置、会话创建/恢复/删除以及原图保存/恢复：

```bash
python3 scripts/smoke_public.py https://YOUR-SERVICE.onrender.com
```

如需同时验证一次真实模型识别，可追加 `--menu-image /path/to/menu.jpg`。冒烟脚本只删除自己创建的测试会话，不会改动用户会话。

匿名接口默认限制为每个来源 IP 每小时 60 次模型请求、全站每小时 300 次模型请求，并限制会话写入、活跃会话数和服务端图片总量。对应环境变量可按真实流量调整；这些是 MVP 的成本保护，不替代正式账号体系和监控告警。

## 真实菜单验收

`scripts/evaluate_real_menus.py` 会把真实菜单依次送入当前服务，补齐最终决策提示后检查价格结构、菜品字段、坐标范围、重复项和广告式空话。示例：

```bash
python3 scripts/evaluate_real_menus.py \
  --expectations eval/acceptance-expectations.json \
  /tmp/menu-avocette.jpg \
  /tmp/menu-petit-cafe.jpg \
  /tmp/menu-pont.jpg \
  /tmp/menu-le-royal-1.jpg
```

`eval/menu-sources.json` 保存了首批 Wikimedia Commons 样本的文件页和缩略图地址，便于追溯来源；仓库不复制原图。`eval/acceptance-expectations.json` 为已人工看过的样本设置最低菜品数和价格结构，防止“只识别两道也算接口成功”。结构检查通过不等于翻译一定正确，最终仍需人工检查菜名、套餐规则、风险提示和原图位置。


## License

本项目基于 [MIT License](LICENSE) 开源，可以使用、修改和分发，但需保留原始版权及许可声明。
