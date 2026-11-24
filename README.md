<p align="right">
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
</p>

# DineTrail

> 一个会记住整顿饭的旅行点餐助手。

**[在线体验 DineTrail →](https://dinetrail-demo.onrender.com)**

https://github.com/user-attachments/assets/54187ea3-4499-4ec5-b2ce-d4222a4fd377

## DineTrail 能做什么

菜单一页页拍，边看、边问、边选。

DineTrail 会记住整顿饭已经选了什么，把你带来的小红书攻略匹配到对应菜品，并在译名之外补充口味、口感和必要的踩雷提示。

最后得到的不是几页菜单译文，而是一份可以直接拿给服务员看的点菜单。

## Why DineTrail

我在欧洲旅行时发现，真实的点餐并不是拍完整本菜单，等待全部翻译完成，再从几十道菜里集中选择。菜单往往有很多页。人们通常看一页、问几道、先选一两道，然后继续翻到下一页。

点餐也很少从零开始。出发前收藏的小红书推荐，到了餐厅后，还要重新在陌生语言的菜单里寻找对应菜品。

而即使看懂了译名，也仍然可能不知道一道菜是生食、内脏，还是味道和想象完全不同。

DineTrail 因此以“一次用餐”为单位组织产品：持续保存攻略、菜单页、追问和选择，直到用户完成这顿饭的点单。

## 本地运行

克隆项目并复制环境变量文件：

```bash
git clone https://github.com/echo-builds/dinetrail-public.git
cd dinetrail-public
cp .env.example .env
```

在 `.env` 中配置一个支持图片理解和结构化输出的模型服务：

```text
MODEL_API_TYPE=openai_compatible
MODEL_BASE_URL=https://YOUR_PROVIDER.example/v1
MODEL_API_KEY=your_key
MODEL_NAME=your_vision_model
```

启动服务：

```bash
python3 server.py
```

打开 `http://localhost:4173`。可使用 OpenAI-compatible 多模态接口或 Gemini；不同模型的结构化输出和流式能力可能不同，详见[模型配置](docs/MODELS.md)。未配置模型时仍可打开界面，但不能识别真实菜单或进行真实对话。

## 开发者文档

- [模型配置](docs/MODELS.md)
- [部署指南](docs/DEPLOYMENT.md)
- [真实菜单评测](docs/EVALUATION.md)

## License

本项目基于 [MIT License](LICENSE) 开源，可以使用、修改和分发，但需保留原始版权及许可声明。
